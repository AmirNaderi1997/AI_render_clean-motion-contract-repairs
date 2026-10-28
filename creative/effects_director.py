"""Chooses which face effects (engine/face_effects, the 42 effects of claude-video-effects) go on a talking reel, where and with what words.

Only the stretches where the speaker has the whole frame can carry an effect (a panel owns the top half otherwise). The model sees what is said in
each stretch and the catalog (what each effect is for) and returns at most a few well-spaced effects; everything it returns is checked by
``face_effects.clean_plan`` and anything invalid is dropped. No model, no effects: the reel is still complete without them.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field

from . import llm
from .schemas import CreativeUnavailable

log = logging.getLogger(__name__)

MIN_WINDOW = 1.8
MAX_EFFECT = 3.2
EDGE = 0.4


class Pick(BaseModel):
    model_config = ConfigDict(extra="ignore")
    window: int
    fx: str
    text: str = ""
    why: str = ""


class Picks(BaseModel):
    model_config = ConfigDict(extra="ignore")
    effects: list[Pick] = Field(default_factory=list)


def windows(plan, words: list[dict], protect: list[tuple[float, float]]) -> list[dict]:
    """Stretches (output time) where the speaker is full frame, long enough for an effect, away from the teaser, panels and key-moment slams."""
    out, cur = [], None
    for shot in plan.shots:
        free = (not shot.split) and shot.out_start >= plan.cold_open + 0.5
        if free and cur and abs(cur["end"] - shot.out_start) < 0.02:
            cur["end"] = shot.out_start + shot.length
        elif free:
            cur = {"start": shot.out_start, "end": shot.out_start + shot.length}
            out.append(cur)
        else:
            cur = None
    res = []
    for w in out:
        a, b = w["start"] + EDGE, w["end"] - EDGE
        for p0, p1 in protect:
            if a < p1 and b > p0:
                a = max(a, p1) if p0 <= a else a
                b = min(b, p0) if p0 > a else b
        if b - a >= MIN_WINDOW:
            said = " ".join(x["w"] for x in words if a - 0.05 <= x["start"] < b)
            res.append({"start": round(a, 2), "end": round(min(b, a + MAX_EFFECT), 2), "spoken": said})
    return res


def choose(plan, *, per_minute: float, protect: list[tuple[float, float]] | None = None, used: list[str] | None = None) -> list[dict]:
    from engine.face_effects import CATALOG, clean_plan
    count = int(round(per_minute * max(plan.duration, 1.0) / 60.0))
    if count <= 0:
        return []
    cands = windows(plan, plan.script["words"], protect or [])
    if not cands:
        return []
    catalog = "\n".join(f"- {c['id']}: {c['title']} — {c['use']}" + (f" (text: {c['text']['label']})" if c.get("text") else "") for c in CATALOG)
    listing = "\n".join(f"[{i}] {w['start']:.1f}-{w['end']:.1f}s «{w['spoken']}»" for i, w in enumerate(cands))
    system = ("You are the editor of a Persian short-form video. Choose visual effects for moments where the speaker is on screen alone. "
              "Return ONLY JSON {\"effects\":[{\"window\":<index>,\"fx\":\"<id>\",\"text\":\"<words, Persian, as the effect needs them>\",\"why\":\"<short>\"}]}. "
              f"Rules: at most {count} effects, never two in neighbouring windows, never the same effect twice, only where the effect supports what is said "
              "(a list for lineup/todo, a number for graph/wall, a contrast for tier-list/broll-split). Words on screen must come from the speech, kept very short; "
              "separate lines with |. Skip a window when nothing fits: fewer, better effects.")
    try:
        picks = llm.ask(Picks, system, f"Catalog:\n{catalog}\n\nWindows:\n{listing}", route=llm.DIRECTOR_ROUTE, tokens=2000, used=used)
    except CreativeUnavailable as exc:
        log.warning("effects director unavailable: %s", str(exc)[:200])
        return []
    plan_out, seen, last = [], set(), -9
    for pick in sorted(picks.effects, key=lambda p: p.window):
        if not (0 <= pick.window < len(cands)) or pick.fx in seen or pick.window - last < 2 or len(plan_out) >= count:
            continue
        w = cands[pick.window]
        item = {"fx": pick.fx, "start": w["start"], "end": w["end"], **({"text": pick.text} if pick.text.strip() else {})}
        try:
            plan_out += clean_plan([item])
        except ValueError:
            continue
        seen.add(pick.fx)
        last = pick.window
    return plan_out
