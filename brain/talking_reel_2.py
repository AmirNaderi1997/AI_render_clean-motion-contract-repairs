"""LLM edit decisions for the "صحبتی ۲" (educational split) talking-reel style.

On top of the shared decisions (corrected captions, dropped sentences, a
cold-open line; see ``brain.talking_reel``) the model picks which sentences
get a picture on the top half of a split screen (with an English image
prompt, a short Persian label and, when the user uploaded media, a file),
which get a stacked list of "chips" (tool names or steps), and a short hook
for the opening seconds.
"""
from __future__ import annotations

import re

from . import talking_reel as base

SYSTEM_PROMPT = """You edit fast educational vertical reels cut from Persian talks (a speaker explains a
topic; the top half of the screen shows a matching picture while he talks). You receive the
transcript as numbered sentences (colloquial Tehrani Persian, speech-to-text) and maybe a list of
media files the creator uploaded. Return ONLY a JSON object:

{
  "hook": "<2-4 word Persian hook for the first 3 seconds, punchy, faithful to the talk>",
  "captions": [{"i": <sentence index>, "text": "<corrected caption>"}],
  "drop": [<indices of filler sentences to cut, e.g. an off-topic "yes" at the end>],
  "cold_open": {"i": <index>, "text": "<the most provocative 2-4 second line, word for word>"},
  "broll": [{"i": <sentence index>,
             "visual": "<English prompt for one clear visual metaphor made from 2-4 recognizable
                        everyday objects interacting, premium Swiss editorial vector illustration,
                        flat shapes, off-white background, no meaningless abstract geometry, people,
                        faces, hands, 3D render, text, or letters>",
             "label": "<2-4 word Persian title for a text card if no image can be made>",
             "media": "<one of the uploaded file names that fits this sentence, or empty>"}],
  "chips": [{"i": <sentence index>, "items": ["<1-3 word Persian label>", ...]}]
}

Rules:
- One caption entry for EVERY sentence that is not dropped. Fix every speech-to-text mistake from
  context, keep the colloquial wording, remove hesitation sounds and repeats, keep English terms
  in Latin script, Persian digits for numbers, never add or summarise.
- "broll": REQUIRED. Pick 3-5 of the strongest concrete ideas (roughly 25-35% of the sentences),
  spaced apart by at least one sentence. Never return an empty broll list. Fewer excellent visuals
  are better than constant decoration. Use each uploaded file at most once, where it fits best.
- "chips": at most 2 lists, only where the speaker lists things (tools, steps, options, costs);
  2-4 items each, Persian, no Latin script unless a product name.
"""


def _sanitize(text: str) -> str:
    # Requests containing this country name are dropped on the user's network.
    return re.sub(r"\bIran(?:ian)?s?\b", "Persian", text, flags=re.IGNORECASE)


def decide(sentences: list[dict], media_names: list[str] | None = None, *, system: str = SYSTEM_PROMPT) -> dict:
    """Decisions for "صحبتی ۲"; other split styles pass their own ``system`` prompt."""
    if not sentences:
        raise ValueError("no speech in the transcript")
    user = base._sentences_prompt(sentences)
    if media_names:
        user += "\n\nUploaded media files:\n" + "\n".join(f"- {name}" for name in media_names)
    data = base._chat(system, user)
    out = normalize(data, len(sentences), media_names or [])
    out["titles"] = [{"i": int(t["i"]), "text": str(t.get("text") or "").strip()}
                     for t in data.get("titles") or []
                     if isinstance(t, dict) and str(t.get("i", "")).isdigit() and 0 <= int(t["i"]) < len(sentences)
                     and int(t["i"]) not in out["drop"] and str(t.get("text") or "").strip()][:3]
    return out


def normalize(data: dict, count: int, media_names: list[str]) -> dict:
    shared = base.normalize({**data, "hook": data.get("hook") or "…"}, count)

    def index(value) -> int | None:
        try:
            k = int(value)
        except (TypeError, ValueError):
            return None
        return k if 0 <= k < count and k not in shared["drop"] else None

    broll, used = [], set()
    for item in data.get("broll") or []:
        k = index((item or {}).get("i"))
        if k is None or any(b["i"] == k for b in broll):
            continue
        # Avoid the machine-made slideshow feeling: never place generated
        # visuals on adjacent sentences and cap a reel at six visual beats.
        if (broll and k - broll[-1]["i"] < 2) or len(broll) >= 6:
            continue
        media = str(item.get("media") or "").strip()
        media = media if media in media_names and media not in used else ""
        used.add(media)
        broll.append({"i": k, "visual": _sanitize(str(item.get("visual") or "").strip()),
                      "label": str(item.get("label") or "").strip(), "media": media})
    chips = []
    for item in data.get("chips") or []:
        k = index((item or {}).get("i"))
        items = [str(v).strip() for v in (item or {}).get("items") or [] if str(v).strip()][:4]
        if k is not None and len(items) >= 2:
            chips.append({"i": k, "items": items})
    # If a model ignores the required visual list, select a few spaced ideas
    # instead of rendering a repetitive wall of text.
    if len(broll) < min(3, max(1, count // 2)):
        blocked = {item["i"] for item in broll} | {item["i"] for item in chips}
        candidates = [k for k in range(count) if k not in shared["drop"] and k not in blocked]
        target = min(count, max(3, (count + 2) // 3))
        for k in candidates:
            if len(broll) >= target:
                break
            if any(abs(k - item["i"]) < 2 for item in broll):
                continue
            idea = str(shared["captions"].get(k) or shared["captions"].get(str(k)) or "").strip()
            if idea:
                broll.append({
                    "i": k,
                    "visual": "A single restrained symbolic object representing this Persian idea: " + idea,
                    "label": " ".join(idea.split()[:4]),
                    "media": "",
                })
        if len(broll) < target:
            used = {item["i"] for item in broll}
            for k in candidates:
                if len(broll) >= target:
                    break
                if k in used:
                    continue
                idea = str(shared["captions"].get(k) or shared["captions"].get(str(k)) or "").strip()
                if idea:
                    broll.append({
                        "i": k,
                        "visual": "A clear editorial metaphor using recognizable objects for this Persian idea: " + idea,
                        "label": " ".join(idea.split()[:4]),
                        "media": "",
                    })
    hook = str(data.get("hook") or "").strip()
    if not hook:
        raise RuntimeError("the LLM returned no hook")
    return {"hook": hook, "captions": shared["captions"], "drop": shared["drop"],
            "cold_open": shared.get("cold_open"), "broll": sorted(broll, key=lambda b: b["i"]),
            "chips": chips[:2]}
