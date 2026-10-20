"""Text decisions for the deliberately minimal fourth talking-reel style."""
from __future__ import annotations

from . import talking_reel_2 as split


SYSTEM_PROMPT = split.SYSTEM_PROMPT.replace(
    '- "broll": pick only 25-35% of the sentences: the strongest concrete ideas, spaced apart by at least\n'
    '  one sentence. Fewer excellent visuals are better than constant decoration. Use each uploaded file\n'
    '  at most once, where it fits best.',
    '- "broll": always return an empty list. This style intentionally uses no generated imagery.\n'
    '- "chips": always return an empty list. Keep the screen quiet and focused on the speaker.',
)


def decide(sentences: list[dict], media_names: list[str] | None = None, guidance: str = "") -> dict:
    out = split.decide(sentences, media_names, system=SYSTEM_PROMPT, guidance=guidance)
    out["broll"] = []
    out["chips"] = []
    out["titles"] = []
    return out
