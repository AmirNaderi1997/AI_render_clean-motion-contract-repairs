"""Edit decisions for talking-head reels (podcast clips) with the configured LLM.

The model gets the transcript sentences (with indices) and returns:
corrected caption text per sentence, the pinned hook title with its
highlighted words, sentences to drop, a few emotional sentences to show in
black and white, and up to two short emphasis phrases. Timing
stays with the transcript; the model only edits text and picks indices.

There is no silent local fallback: a reel without corrected captions and a
hook is not worth rendering, so provider failures raise.
"""
from __future__ import annotations

import json
import logging
import re

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You edit short vertical reels cut from Persian business podcasts, in the style of
popular Persian business creators on Instagram. You receive the transcript as numbered
sentences (speech-to-text output, colloquial Tehrani Persian). Return ONLY a JSON object:

{
  "hook": "<pinned hook title in Persian, 3-8 words, a curiosity gap that makes people keep
           watching, usually first person and ending with ... when it teases; must be faithful
           to what the speaker actually says>",
  "hook_highlight": ["<1-2 words or short phrases copied exactly from hook to show in yellow>"],
  "captions": [{"i": <sentence index>, "text": "<corrected caption>"}],
  "drop": [<indices of sentences to cut: filler, false starts, an off-topic "yes"/"ok" at the end>],
  "bw": [<1-3 indices of the most emotional or dramatic sentences, shown in black and white>],
  "notes": [{"i": <index of one of the "bw" sentences>, "text": "<2-4 word punchy key takeaway of it>"}],
  "cold_open": {"i": <sentence index>, "text": "<the single most provocative 2-4 second line of the
                talk, copied word for word from that sentence's transcript (a contiguous part of it),
                played first as a teaser before the video starts from the beginning>"}
}

Caption rules:
- One caption entry for EVERY sentence index that is not dropped, in order.
- Fix every speech-to-text mistake (wrong letters, wrong words, missing spaces, half-space
  where needed) using the context; keep the speaker's colloquial wording (میخوام، نمیخواد، اینه).
- Remove hesitation sounds and stutters (اِاِاِ، امم، اوم) and immediate word repeats.
- Keep English terms the speaker says in Latin script (e.g. scalable, Drop Servicing).
- Write numbers with Persian digits.
- Do not add words the speaker did not say. Do not summarise.
Keep "notes" to at most 2 and "bw" to at most 3. Each note is shown alone, word by word, over its
black-and-white moment: write it in Persian words only (no English words, no Latin script)."""

FILLER_WORDS = re.compile(r"^(?:[اآ]+[ِ]?)+$|^(?:ا?م+|ا?و?م+|ا?ه+)$")


def _sentences_prompt(sentences: list[dict]) -> str:
    rows = [f"{k}: [{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for k, s in enumerate(sentences)]
    return "Transcript sentences:\n" + "\n".join(rows)


def _chat(system: str, user: str) -> dict:
    from .ai_provider import JarvisProvider, SaroviProvider

    errors = []
    for provider in (JarvisProvider(), SaroviProvider()):
        call = getattr(provider, "_chat_json", None) or getattr(provider, "_responses_json")
        for attempt in range(2):
            try:
                data, usage = call(system, user)
                log.info("talking reel decisions from %s (%s)", provider.name, usage.model)
                return data
            except Exception as exc:  # flaky provider connections
                errors.append(f"{provider.name}: {exc}")
                log.warning("talking reel LLM attempt failed (%s): %s", provider.name, exc)
    raise RuntimeError("LLM unavailable for the talking reel (check the VPN): " + " | ".join(errors)[:600])


def decide(sentences: list[dict]) -> dict:
    """Ask the LLM for text edits and highlights; returns validated decisions."""
    if not sentences:
        raise ValueError("no speech in the transcript")
    data = _chat(SYSTEM_PROMPT, _sentences_prompt(sentences))
    return normalize(data, len(sentences))


def normalize(data: dict, count: int) -> dict:
    """Validate indices and fill gaps so rendering never depends on a perfect answer."""
    def index(value) -> int | None:
        try:
            k = int(value)
        except (TypeError, ValueError):
            return None
        return k if 0 <= k < count else None

    drop = sorted({k for k in (index(v) for v in data.get("drop") or []) if k is not None})
    captions = {}
    for item in data.get("captions") or []:
        k = index((item or {}).get("i"))
        text = str((item or {}).get("text") or "").strip()
        if k is not None and text and k not in drop:
            captions[k] = text
    bw = [k for k in (index(v) for v in data.get("bw") or []) if k is not None and k not in drop][:3]
    notes = []
    for item in data.get("notes") or []:
        k = index((item or {}).get("i"))
        text = str((item or {}).get("text") or "").strip()
        # Emphasis phrases are Persian only.
        if k is not None and text and k not in drop and len(text.split()) <= 5 and not re.search(r"[A-Za-z]", text):
            notes.append({"i": k, "text": text})
    cold = data.get("cold_open") or {}
    cold_i = index(cold.get("i")) if isinstance(cold, dict) else None
    cold_open = ({"i": cold_i, "text": str(cold.get("text") or "").strip()}
                 if cold_i is not None and cold_i not in drop else None)
    hook = str(data.get("hook") or "").strip()
    if not hook:
        raise RuntimeError("the LLM returned no hook title")
    highlight = [str(h).strip() for h in data.get("hook_highlight") or [] if str(h).strip() and str(h).strip() in hook]
    return {"hook": hook, "hook_highlight": highlight[:2], "captions": captions, "drop": drop,
            "bw": bw, "notes": notes[:2], "cold_open": cold_open}


def is_filler(word: str) -> bool:
    """Hesitation tokens that the cut should remove (اِاِاِ، امم، ...)."""
    return bool(FILLER_WORDS.match(re.sub(r"[^\w؀-ۿ]", "", word or "")))
