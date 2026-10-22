"""Timeline edits: the user's changes to individual elements, kept beside the AI's decisions.

An edit is keyed by the element's stable id (see ``project_document``) and is applied to the render plan
after it is built (``talking_reel.plan_render``), so the render and the timeline show the same thing and each
style keeps its own look. Nothing here edits the AI's decisions: removing an edit restores the original.

Supported today: caption text, caption timing, and hiding a caption. Speaker cuts come from the speech and
pictures from the plan; they are not editable on the timeline yet.
"""
from __future__ import annotations

import re

CAPTION_ID = re.compile(r"^caption(?::cold)?:s(?:\d{1,4}|x):\d{1,3}$")
MAX_EDITS = 300
MIN_LENGTH = 0.3      # shortest readable caption (seconds)
MAX_TEXT = 200
OVERLAP = 0.05        # tolerated overlap between neighbouring captions


class EditError(ValueError):
    pass


class Clock:
    """Maps output time to the transcript sentence it shows, through the plan's shots."""

    def __init__(self, shots, sentences: list[dict]):
        self.shots, self.sentences = shots, sentences

    def source(self, t: float) -> float | None:
        for shot in self.shots:
            if shot.out_start - 1e-6 <= t < shot.out_start + shot.length:
                return shot.src_in + (t - shot.out_start)
        return None

    def sentence(self, t: float) -> int | None:
        src = self.source(t + 0.02)
        if src is None:
            return None
        for k, s in enumerate(self.sentences):
            if s["start"] - 0.05 <= src <= s["end"] + 0.05:
                return k
        return min(range(len(self.sentences)), key=lambda k: abs(self.sentences[k]["start"] - src)) if self.sentences else None


def caption_ids(plan, sentences: list[dict]) -> list[str]:
    """Stable ids for ``plan.captions``, in order: ``caption:s<sentence>:<n>`` (``caption:cold:`` in the teaser)."""
    shots = plan.shots[1:] if plan.cold_open else plan.shots
    clock, cold_clock = Clock(shots, sentences), Clock(plan.shots[:1], sentences)
    seen: dict[str, int] = {}
    ids = []
    for caption in plan.captions:
        teaser = caption["start"] < plan.cold_open
        sentence = (cold_clock if teaser else clock).sentence(caption["start"])
        key = f"caption{':cold' if teaser else ''}:s{sentence if sentence is not None else 'x'}"
        ids.append(f"{key}:{seen.get(key, 0)}")
        seen[key] = seen.get(key, 0) + 1
    return ids


def caption_text(caption: dict) -> str:
    return caption.get("text") or " ".join(p for p in (caption.get("lead"), caption.get("key")) if p)


def clean(raw) -> dict:
    """Shape-check stored/received edits: {id: {"text"?, "start"?, "end"?, "deleted"?}}. Unknown fields are dropped."""
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict):
        raise EditError("ویرایش‌های تایم‌لاین معتبر نیست.")
    out: dict[str, dict] = {}
    for element_id, edit in raw.items():
        if not isinstance(element_id, str) or not CAPTION_ID.match(element_id):
            raise EditError(f"این عنصر قابل ویرایش نیست: {str(element_id)[:40]}")
        if not isinstance(edit, dict):
            raise EditError("ویرایش عنصر معتبر نیست.")
        item: dict = {}
        if "text" in edit:
            text = " ".join(str(edit["text"] or "").split())
            if not text or len(text) > MAX_TEXT:
                raise EditError(f"متن زیرنویس باید بین ۱ تا {MAX_TEXT} نویسه باشد.")
            item["text"] = text
        for field in ("start", "end"):
            if field in edit and edit[field] is not None:
                try:
                    value = float(edit[field])
                except (TypeError, ValueError):
                    raise EditError("زمان زیرنویس باید عدد باشد.")
                if not 0 <= value <= 3600 or value != value:
                    raise EditError("زمان زیرنویس خارج از محدوده است.")
                item[field] = round(value, 2)
        if edit.get("deleted"):
            item["deleted"] = True
        if item:
            out[element_id] = item
    if len(out) > MAX_EDITS:
        raise EditError("تعداد ویرایش‌ها از حد مجاز بیشتر است.")
    return out


def merge_caption(caption: dict, edit: dict | None) -> dict | None:
    """The caption as rendered with the user's edit, or None when it is hidden."""
    if not edit:
        return caption
    if edit.get("deleted"):
        return None
    merged = dict(caption)
    if "start" in edit:
        merged["start"] = edit["start"]
    if "end" in edit:
        merged["end"] = edit["end"]
    if "text" in edit:
        if "text" in caption:                       # style 1: one line per phrase
            merged["text"] = edit["text"]
        else:                                       # split styles: a small lead and one large keyword
            words = edit["text"].split()
            merged["lead"], merged["key"] = " ".join(words[:-1]), words[-1]
    return merged


def validate(plan, sentences: list[dict], edits: dict, duration: float) -> None:
    """Every edit must name a real caption and leave readable, non-overlapping timing."""
    ids = caption_ids(plan, sentences)
    unknown = [key for key in edits if key not in ids]
    if unknown:
        raise EditError("این زیرنویس در برنامهٔ فعلی وجود ندارد: " + unknown[0])
    rows = []
    for element_id, caption in zip(ids, plan.captions):
        edit = edits.get(element_id)
        merged = merge_caption(caption, edit)
        if merged is not None:
            rows.append((element_id, merged, bool(edit)))
    for element_id, merged, edited in rows:
        if not edited:
            continue
        if merged["start"] < 0 or merged["end"] > duration + 1e-6:
            raise EditError("زمان زیرنویس باید داخل مدت ویدیو باشد.")
        if merged["end"] - merged["start"] < MIN_LENGTH:
            raise EditError(f"هر زیرنویس دست‌کم {MIN_LENGTH} ثانیه باید نمایش داده شود.")
    rows.sort(key=lambda row: row[1]["start"])
    for (a_id, a, a_edited), (b_id, b, b_edited) in zip(rows, rows[1:]):
        if (a_edited or b_edited) and a["end"] > b["start"] + OVERLAP:
            raise EditError("این زمان‌بندی با زیرنویس مجاور هم‌پوشانی دارد؛ زمان را کمی جابه‌جا کنید.")


def apply(plan, sentences: list[dict], edits: dict | None) -> None:
    """Replace ``plan.captions`` with the edited captions. Edits for ids the plan no longer has are ignored."""
    edits = edits or {}
    if not edits:
        return
    ids = caption_ids(plan, sentences)
    merged = [merge_caption(caption, edits.get(element_id)) for element_id, caption in zip(ids, plan.captions)]
    plan.captions = sorted((c for c in merged if c is not None), key=lambda c: c["start"])
