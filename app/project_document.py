"""Project Document: the engine-neutral timeline of a Studio project.

One document per project describes everything in the video as tracks of elements with stable ids:
the speaker clips, the upper picture panel, titles, captions, graphics, audio and the outro. Engines
produce it through adapters; the Talking adapter builds it from the exact render plan the renderer uses
(``talking_reel.plan_render``), so the timeline always matches what is (or will be) rendered.

Ids are derived from the source, not from positions, so they survive text edits: a caption is
``caption:s<sentence>:<n>`` (n-th caption of that transcript sentence), a picture is ``picture:s<slot>``.

Each element says how it can be changed today (``edit.via``: "plan", "chat", "timeline"); only captions are
editable on the timeline so far, through the edits layer (``timeline_edits``), and nothing claims an edit the
renderer cannot apply.
"""
from __future__ import annotations

from pathlib import Path

from app import timeline_edits as edits_layer

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


def _element(id_: str, type_: str, start: float, end: float, label: str, *, text: str = "", source: dict | None = None,
             props: dict | None = None, via: list[str] | None = None, note: str = "") -> dict:
    return {"id": id_, "type": type_, "start": _r(start), "end": _r(max(end, start)), "label": label, "text": text,
            "source": source or {}, "props": props or {}, "edit": {"via": via or [], "note": note}}


def talking_document(job_dir: Path, video: Path) -> dict:
    from app import talking_reel
    from engine.talking_styles.talking_1 import CTA_SECONDS, LOGO, LOGO_SECONDS

    planned = talking_reel.plan_render(job_dir, video, prepare_media=False, apply_edits=False)
    plan, style, state = planned.plan, planned.style, talking_reel.load(job_dir)
    sentences = planned.transcript["sentences"]
    clock = edits_layer.Clock(plan.shots[1:] if plan.cold_open else plan.shots, sentences)
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

    # Captions, with ids from their transcript sentence and the user's edits laid over the AI's version.
    edits = state.get("timeline_edits") or {}
    caption_ids = edits_layer.caption_ids(plan, sentences)
    for element_id, caption in zip(caption_ids, plan.captions):
        edit = edits.get(element_id)
        shown = edits_layer.merge_caption(caption, edit) or caption
        teaser = element_id.startswith("caption:cold")
        sentence = None if element_id.split(":")[-2] == "sx" else int(element_id.split(":")[-2][1:])
        original = {"text": edits_layer.caption_text(caption), "start": _r(caption["start"]), "end": _r(caption["end"])}
        tracks["captions"].append(_element(
            element_id, "caption", shown["start"], shown["end"],
            ("پیش‌نمایش ابتدایی · " if teaser else "") + (f"جملهٔ {sentence + 1}" if sentence is not None else ""),
            text=edits_layer.caption_text(shown),
            props={"sentence": sentence, "key": shown.get("key"), "edited": bool(edit), "deleted": bool(edit and edit.get("deleted")),
                   "original": original},
            via=["timeline", "chat"], note="متن و زمان این زیرنویس را همین‌جا عوض کنید یا آن را پنهان کنید."))
    stale = sorted(set(edits) - set(caption_ids))

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
        "stale_edits": stale, "edit_count": len(edits) - len(stale),
        "tracks": [{"id": key, "kind": TRACKS[key][0], "label": TRACKS[key][1], "elements": sorted(items, key=lambda e: e["start"])}
                   for key, items in tracks.items() if items],
    }
