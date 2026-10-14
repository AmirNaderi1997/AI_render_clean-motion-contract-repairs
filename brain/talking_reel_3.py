"""LLM edit decisions for the "صحبتی ۳" (cinematic split) talking-reel style.

Same shape as ``brain.talking_reel_2`` (captions, picture slots, chips,
hook, cold open) plus up to three chapter titles; pictures are cinematic
photographs rather than clean editorial renders.
"""
from __future__ import annotations

from . import talking_reel_2 as split

SYSTEM_PROMPT = split.SYSTEM_PROMPT.replace(
    "concrete\n                        subject, clean modern editorial or 3D style, no text or letters in the image",
    "concrete\n                        subject, cinematic photograph, moody low-key lighting, shallow depth of field,\n"
    "                        35mm film look, rich shadows, no text or letters in the image",
).replace(
    '  "chips": [{"i": <sentence index>, "items": ["<1-3 word Persian label>", ...]}]\n}',
    '  "chips": [{"i": <sentence index>, "items": ["<1-3 word Persian label>", ...]}],\n'
    '  "titles": [{"i": <sentence index where a new idea starts>, "text": "<2-4 word elegant Persian\n'
    '              chapter title for it, e.g. آینده‌ی یادگیری>"}]\n}',
).replace(
    "- \"chips\": at most 2 lists",
    "- \"titles\": 2-3 of them at the sentences where the talk turns to a new idea (one may be the first).\n"
    "- \"chips\": at most 1 list",
)


def decide(sentences: list[dict], media_names: list[str] | None = None) -> dict:
    out = split.decide(sentences, media_names, system=SYSTEM_PROMPT)
    out["chips"] = out["chips"][:1]
    return out
