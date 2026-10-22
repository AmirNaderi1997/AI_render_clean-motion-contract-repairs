"""Project Document: the engine-neutral timeline of a Studio project.

One document per project describes everything in the video as tracks of elements with stable ids:
the speaker clips, the upper picture panel, titles, captions, graphics, audio and the outro. Engines
produce it through adapters; the Talking adapter builds it from the exact render plan the renderer uses
(``talking_reel.plan_render``), so the timeline always matches what is (or will be) rendered.

Ids are derived from the source, not from positions, so they survive text edits: a caption is
``caption:s<sentence>:<n>`` (n-th caption of that transcript sentence), a picture is ``picture:s<slot>``.

This phase is read-only. Each element says how it can be changed today (``edit.via``: "plan", "chat")
and nothing claims a manual timeline edit that the renderer cannot apply yet.
"""
from __future__ import annotations

from pathlib import Path

SCHEMA = 1

TRACKS = {   # id -> (kind, Persian label), in display order
    "video": ("video", "گوینده"),
    "panel": ("broll", "تصویر بالا"),
    "titles": ("title", "هوک و عنوان‌ها"),
    "captions": ("caption", "زیرنویس"),
    "graphics": ("motion", "گرافیک و تأکید"),
    "voice": ("audio", "صدای گوینده"),
    "music": ("music", "موسیقی"),
    "outro": ("video", "پایان (CTA و لوگو)"),
}

PICTURE_SOURCES = {
    "upload": "فایل شما", "library": "کتابخانه", "ai": "ساخته‌شده با هوش مصنوعی",
    "ai_planned": "با هوش مصنوعی ساخته می‌شود (هنوز ساخته نشده)", "motion_so": "موشن Motion.so", "motion": "موشن HyperFrames",
    "card": "کارت متنی",
}


def _r(value: float) -> float:
    return round(float(value), 3)


class _Clock:
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


def _element(id_: str, type_: str, start: float, end: float, label: str, *, text: str = "", source: dict | None = None,
             props: dict | None = None, via: list[str] | None = None, note: str = "") -> dict:
    return {"id": id_, "type": type_, "start": _r(start), "end": _r(max(end, start)), "label": label, "text": text,
            "source": source or {}, "props": props or {}, "edit": {"via": via or [], "note": note}}


def _numbered(elements: list[dict], prefix: str, sentence: int | None) -> str:
    """``prefix:s<sentence>:<n>``, n counting earlier elements of the same sentence."""
    key = f"{prefix}:s{sentence if sentence is not None else 'x'}"
    n = sum(1 for e in elements if e["id"].startswith(key + ":"))
    return f"{key}:{n}"


def talking_document(job_dir: Path, video: Path) -> dict:
    from app import talking_reel
    from engine.talking_styles.talking_1 import CTA_SECONDS, LOGO, LOGO_SECONDS

    planned = talking_reel.plan_render(job_dir, video, prepare_media=False)
    plan, style, state = planned.plan, planned.style, talking_reel.load(job_dir)
    sentences = planned.transcript["sentences"]
    clock = _Clock(plan.shots[1:] if plan.cold_open else plan.shots, sentences)
    cold_clock = _Clock(plan.shots[:1], sentences)   # the opening teaser is taken from later in the talk
    tracks: dict[str, list[dict]] = {key: [] for key in TRACKS}
    split_style = style != "talking_1"

    # Speaker clips. Cuts come from the speech (pauses and fillers are removed), not from a hand edit.
    for index, shot in enumerate(plan.shots):
        cold = bool(plan.cold_open) and index == 0
        framing = ("پایین قاب (تصویر بالا)" if getattr(shot, "split", False) else
                   "نمای بسته" if shot.close else "نمای باز")
        if getattr(shot, "bw", False):
            framing += " · سیاه‌وسفید"
        tracks["video"].append(_element(
            f"clip:{int(round(shot.src_in * 1000))}", "clip", shot.out_start, shot.out_start + shot.length,
            ("پیش‌نمایش ابتدایی · " if cold else "") + framing,
            source={"kind": "upload", "label": video.name, "in": _r(shot.src_in), "out": _r(shot.src_out)},
            props={"close": bool(shot.close), "split": bool(getattr(shot, "split", False)),
                   "bw": bool(getattr(shot, "bw", False)), "push": bool(getattr(shot, "push", False)), "cold_open": cold},
            via=["chat"], note="برش‌ها از گفتار ساخته می‌شوند (مکث و کلمه‌های اضافه حذف می‌شوند)؛ برش دستی در مرحلهٔ بعد اضافه می‌شود."))

    # The upper picture panel of the split styles: one element per contiguous run of the same slot.
    if split_style:
        slots = {int(s["i"]): s for s in planned.slots}
        full = getattr(plan, "full_pictures", set())
        cards = getattr(plan, "card_pictures", set())
        run: list = []

        def close_run():
            if not run:
                return
            slot = run[0].slot
            info = slots.get(slot, {})
            kind = info.get("source") or ("motion" if planned.hyperframes else "card")
            picture = run[0].picture
            layout = ("تمام‌قاب" if any(id(s) in full for s in run) else
                      "کارت کج" if picture in cards else "بالای قاب")
            tracks["panel"].append(_element(
                f"picture:s{slot}", "picture", run[0].out_start, run[-1].out_start + run[-1].length,
                info.get("label") or (sentences[slot]["text"][:40] if slot is not None and slot < len(sentences) else "تصویر"),
                source={"kind": kind, "label": PICTURE_SOURCES.get(kind, kind),
                        "file": Path(picture).name if picture else None},
                props={"layout": layout, "sentence": slot},
                via=["chat"] if style in {"talking_2", "talking_3"} else [],
                note="برای عوض یا حذف کردن این تصویر در چت بگویید، مثلاً «تصویر جملهٔ ۳ را عوض کن»."))
            run.clear()

        for shot in plan.shots:
            if getattr(shot, "split", False) and shot.slot is not None and (shot.picture or shot.slot in slots):
                if run and run[-1].slot != shot.slot:
                    close_run()
                run.append(shot)
            else:
                close_run()
        close_run()

    # Hook and titles.
    hook_text = state.get("hook") if style == "talking_1" else (state.get("hook2") or state.get("hook"))
    if style == "talking_1" and hook_text:
        tracks["titles"].append(_element("hook", "title", 0, plan.duration, "هوک ثابت", text=hook_text,
                                         props={"highlight": state.get("hook_highlight") or [], "persistent": True},
                                         via=["plan", "chat"], note="متن و کلمهٔ رنگی هوک را در برنامه یا چت عوض کنید."))
    elif getattr(plan, "hook", None):
        tracks["titles"].append(_element("hook", "title", plan.hook["start"], plan.hook["end"], "هوک", text=plan.hook["text"],
                                         via=["plan", "chat"], note="متن هوک را در برنامه یا چت عوض کنید."))
    for title in getattr(plan, "titles", []) or []:
        sentence = clock.sentence(title["start"])
        tracks["titles"].append(_element(f"title:s{sentence}", "title", title["start"], title["end"], "عنوان فصل",
                                         text=title["text"], via=["chat"]))
    for card in getattr(plan, "cards", []) or []:
        sentence = clock.sentence(card["start"])
        tracks["graphics"].append(_element(f"card:s{sentence}", "card", card["start"], card["end"], "کارت متنی",
                                           text=card["text"], via=["chat"]))

    # Captions, with ids from their transcript sentence.
    for caption in plan.captions:
        text = caption.get("text") or " ".join(p for p in (caption.get("lead"), caption.get("key")) if p)
        teaser = caption["start"] < plan.cold_open
        sentence = (cold_clock if teaser else clock).sentence(caption["start"])
        element_id = _numbered(tracks["captions"], "caption:cold" if teaser else "caption", sentence)
        tracks["captions"].append(_element(element_id, "caption", caption["start"], caption["end"],
                                           ("پیش‌نمایش ابتدایی · " if teaser else "") +
                                           (f"جملهٔ {sentence + 1}" if sentence is not None else ""),
                                           text=text, props={"sentence": sentence, "key": caption.get("key")},
                                           via=["chat"], note="برای اصلاح متن در چت بگویید، مثلاً «زیرنویس جملهٔ ۲ را … کن»."))

    # Graphics: chips (lists), key moments (style 1) and authored motion scenes (style 2 with HyperFrames).
    for chip in getattr(plan, "chips", []) or []:
        sentence = clock.sentence(chip["start"])
        tracks["graphics"].append(_element(f"chips:s{sentence}", "chips", chip["start"], chip["end"], "فهرست",
                                           text=" · ".join(chip["items"]), via=["chat"]))
    for note in getattr(plan, "notes", []) or []:
        sentence = clock.sentence(note["start"])
        tracks["graphics"].append(_element(f"moment:s{sentence}", "moment", note["start"], note["end"], "لحظهٔ کلیدی",
                                           text=note.get("text", ""), props={"effect": (planned.settings or {}).get("key_moment_effect")},
                                           via=["plan"], note="لحظه‌های کلیدی را در برنامه روشن یا خاموش کنید."))
    for k, t in enumerate(getattr(plan, "flashes", []) or []):
        tracks["graphics"].append(_element(f"flash:{k}", "flash", max(0.0, t - 0.1), t + 0.28, "فلش نور", via=[]))
    for beat in state.get("visual_beats") or []:
        if "start" in beat and "end" in beat:
            tracks["graphics"].append(_element(f"motion:{beat.get('id') or beat['start']}", "motion", beat["start"], beat["end"],
                                               beat.get("title") or "صحنهٔ موشن",
                                               source={"kind": "motion", "label": "طراحی‌شده" if beat.get("authored") else "قالب"},
                                               via=["chat"]))

    # Audio.
    tracks["voice"].append(_element("voice", "audio", 0, plan.duration, "صدای اصلی",
                                    source={"kind": "upload", "label": video.name},
                                    note="صدا همراه هر برش تصویر بریده می‌شود و بلندی آن یکسان‌سازی می‌شود."))
    music = talking_reel.resolve_music(state.get("music"))
    outro_logo = (planned.settings or {}).get("outro_logo") or {}
    logo_on = bool(outro_logo.get("enabled", True)) and (bool(talking_reel.custom_logo(job_dir)) or LOGO.is_file())
    cta = (state.get("cta") or "").strip()
    outro_seconds = (CTA_SECONDS if cta else 0.0) + (LOGO_SECONDS if logo_on else 0.0)
    total = plan.duration + outro_seconds
    if music:
        tracks["music"].append(_element("music", "music", 0, total, music.stem.replace("_", " "),
                                        source={"kind": "library", "label": music.name},
                                        note="موسیقی زیر صدا با کاهش خودکار هنگام صحبت پخش می‌شود."))

    # Outro.
    if cta:
        tracks["outro"].append(_element("cta", "cta", plan.duration, plan.duration + CTA_SECONDS, "دعوت به اقدام", text=cta,
                                        via=["plan", "chat"]))
    if logo_on:
        start = plan.duration + (CTA_SECONDS if cta else 0.0)
        tracks["outro"].append(_element("logo", "logo", start, start + LOGO_SECONDS, "لوگوی متحرک",
                                        props={"motion": outro_logo.get("motion", "pop")}, via=["plan"]))

    return {
        "schema": SCHEMA, "engine": "talking", "style": style,
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "duration": _r(total), "content_duration": _r(plan.duration),
        "tracks": [{"id": key, "kind": TRACKS[key][0], "label": TRACKS[key][1], "elements": sorted(items, key=lambda e: e["start"])}
                   for key, items in tracks.items() if items],
    }
