"""LLM edit decisions for the "صحبتی ۳" (cinematic split) talking-reel style.

Same shape as ``brain.talking_reel_2`` (captions, picture slots, chips,
hook, cold open) plus up to three chapter titles; pictures are cinematic
photographs rather than clean editorial renders.
"""
from __future__ import annotations

from . import talking_reel_2 as split

SYSTEM_PROMPT = split.SYSTEM_PROMPT.replace(
    "one clear visual metaphor made from 2-4 recognizable\n"
    "                        everyday objects interacting, premium Swiss editorial vector illustration,\n"
    "                        flat shapes, off-white background, no meaningless abstract geometry, people,\n"
    "                        faces, hands, 3D render, text, or letters",
    "one concrete object as a premium minimalist still-life photograph, restrained charcoal and warm\n"
    "                        ivory palette, soft directional light, generous negative space, real material\n"
    "                        texture, no people, faces, hands, screens, text, letters, surrealism, or 3D render",
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
