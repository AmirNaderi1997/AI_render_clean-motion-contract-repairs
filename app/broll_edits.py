"""B-roll edits: the user's choice of picture for a slot of the upper panel (styles 2 and 3).

Kept beside the AI's decisions, keyed by the slot's sentence index, and applied to ``decisions["broll"]`` before
``resolve_pictures`` runs, so the renderer's own logic (upload, library, AI image, cache) does the rest and each style
keeps its look. A slot has exactly one source:

* ``upload``  - a picture the user added to the project
* ``library`` - a picture from the asset library
* ``ai``      - an image generated from a prompt (only made at render time, after the plan is approved)
* ``hidden``  - no picture for this slot (the speaker stays on screen)

Removing an edit restores the AI's choice. Slots are never created here: only slots the AI planned can be changed.
"""
from __future__ import annotations

import copy
import re

SOURCES = {"upload", "library", "ai", "hidden"}
MAX_PROMPT = 600
MAX_EDITS = 30
FILE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
LIBRARY_PATH = re.compile(r"^assets/[A-Za-z0-9_./ -]{1,200}$")
SLOT = re.compile(r"^\d{1,4}$")


class EditError(ValueError):
    pass


def clean(raw) -> dict:
    """Shape-check stored/received edits: {"<slot>": {"source": ..., + that source's field}}."""
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict):
        raise EditError("ویرایش تصویرها معتبر نیست.")
    out: dict[str, dict] = {}
    for slot, edit in raw.items():
        if not isinstance(slot, str) or not SLOT.match(slot):
            raise EditError("شناسهٔ تصویر معتبر نیست.")
        if not isinstance(edit, dict) or edit.get("source") not in SOURCES:
            raise EditError("منبع تصویر باید فایل شما، کتابخانه، هوش مصنوعی یا حذف باشد.")
        source, item = edit["source"], {"source": edit["source"]}
        if source == "upload":
            name = str(edit.get("media") or "")
            if not FILE_NAME.match(name) or ".." in name:
                raise EditError("نام فایل تصویر معتبر نیست.")
            item["media"] = name
        elif source == "library":
            path = str(edit.get("library") or "")
            if not LIBRARY_PATH.match(path) or ".." in path:
                raise EditError("مسیر تصویر کتابخانه معتبر نیست.")
            item["library"] = path
        elif source == "ai":
            prompt = " ".join(str(edit.get("visual") or "").split())
            if len(prompt) < 3 or len(prompt) > MAX_PROMPT:
                raise EditError(f"توضیح تصویر باید بین ۳ تا {MAX_PROMPT} نویسه باشد.")
            item["visual"] = prompt
        label = " ".join(str(edit.get("label") or "").split())[:80]
        if label:
            item["label"] = label
        out[slot] = item
    if len(out) > MAX_EDITS:
        raise EditError("تعداد ویرایش تصویرها از حد مجاز بیشتر است.")
    return out


def validate(decisions: dict, edits: dict, *, uploads: set[str], library: set[str]) -> None:
    """Edits may only change slots the AI planned, and may only use files that really exist."""
    slots = {str(item["i"]) for item in decisions.get("broll") or []}
    for slot, edit in edits.items():
        if slot not in slots:
            raise EditError(f"برای جملهٔ {int(slot) + 1} تصویری برنامه‌ریزی نشده است.")
        if edit["source"] == "upload" and edit["media"] not in uploads:
            raise EditError("فایل تصویر در پروژه پیدا نشد؛ دوباره آپلود کنید.")
        if edit["source"] == "library" and edit["library"] not in library:
            raise EditError("این تصویر در کتابخانه وجود ندارد.")


def apply(decisions: dict, edits: dict | None) -> dict:
    """A copy of ``decisions`` with the user's picture choices applied. Edits for slots no longer planned are ignored."""
    if not edits:
        return decisions
    sanitize = _sanitizer()
    result = copy.deepcopy(decisions)
    slots = []
    for item in result.get("broll") or []:
        edit = edits.get(str(item["i"]))
        if edit is None:
            slots.append(item)
            continue
        if edit["source"] == "hidden":
            continue
        item.update(media="", library="", visual="" if edit["source"] != "ai" else sanitize(edit["visual"]))
        if edit["source"] == "upload":
            item["media"] = edit["media"]
        elif edit["source"] == "library":
            item["library"] = edit["library"]
        if edit.get("label"):
            item["label"] = edit["label"]
        slots.append(item)
    result["broll"] = slots
    return result


def _sanitizer():
    """The same prompt cleanup the planner applies to its own prompts (brain.talking_reel_2)."""
    from brain.talking_reel_2 import _sanitize
    return _sanitize
