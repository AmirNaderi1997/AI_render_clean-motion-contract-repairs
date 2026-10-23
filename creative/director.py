"""Content understanding → concept exploration → critique → creative plan."""
from __future__ import annotations

import logging
import os
import time

from . import capabilities, llm, prompts
from .schemas import (Beat, Concept, ContentBrief, CreativePlan, CreativeUnavailable, Critique)

log = logging.getLogger(__name__)

# Keep the whole creative stage bounded: a slow model must not hold a job hostage.
DEFAULT_BUDGET_S = 240


def enabled() -> bool:
    """On by default; set CREATIVE_ENGINE=0 to run the standard pipelines only."""
    return os.environ.get("CREATIVE_ENGINE", "1").strip().lower() not in {"0", "false", "off", "no"}


class _Concepts(llm.BaseModel):
    concepts: list[Concept]


class _Expansion(llm.BaseModel):
    beats: list[Beat] = []
    visual_language: str = ""
    pacing: str = ""


def _numbered(sentences: list[dict]) -> str:
    return "\n".join(f"{k}: [{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for k, s in enumerate(sentences))


def _fallback_critique(concepts: list[Concept], reason: str) -> Critique:
    return Critique(scores=[], chosen_id=concepts[0].id, verdict=f"Not reviewed ({reason}); first concept used.")


def _pick(critique: Critique, concepts: list[Concept]) -> Concept:
    by_id = {c.id: c for c in concepts}
    if critique.scores:
        ranked = sorted(critique.scores, key=lambda s: s.total, reverse=True)
        # Trust the critic's explicit choice unless the numbers clearly disagree with it.
        chosen = by_id.get(critique.chosen_id)
        best = by_id.get(ranked[0].id)
        if chosen is None or (best is not None and ranked[0].total - next((s.total for s in critique.scores if s.id == chosen.id), 0) > 4):
            return best or concepts[0]
        return chosen
    return by_id.get(critique.chosen_id) or concepts[0]


def _outline_beats(concept: Concept) -> list[Beat]:
    """Fallback when expansion is unavailable: the sketch already names a role and an idea per beat."""
    beats = []
    for item in concept.outline:
        role, _, idea = item.partition(":")
        beats.append(Beat(role=role.strip() if idea else "", intent=(idea or item).strip()))
    return beats


def _expand(chosen: Concept, brief: ContentBrief, critique: Critique, caps: str, guide: str,
            used: list[str], started: float, budget_s: float, source: str = "") -> None:
    """Detail only the winner: smaller outputs, fewer tokens, and a result that fits the model's output limit."""
    if time.monotonic() - started > budget_s:
        chosen.beats = chosen.beats or _outline_beats(chosen)
        return
    try:
        request = llm.dumps({"brief": brief.model_dump(), "concept": chosen.model_dump(exclude={"beats"}),
                             "reviewer_improvements": critique.improvements, "improved_hook": critique.improved_hook})
        expansion = llm.ask(_Expansion, prompts.EXPAND, request + f"\n\n{guide}\n\nSource evidence:\n{source}\n\nCapabilities:\n{caps}",
                            route=llm.DIRECTOR_ROUTE, tokens=5000, used=used)
        chosen.beats = expansion.beats[:7] or _outline_beats(chosen)
        chosen.visual_language = expansion.visual_language or chosen.visual_language
        chosen.pacing = expansion.pacing or chosen.pacing
    except CreativeUnavailable as exc:
        log.warning("creative expansion skipped: %s", exc)
        chosen.beats = chosen.beats or _outline_beats(chosen)


def compose_notes(brief: ContentBrief, concept: Concept, critique: Critique) -> str:
    """The compact guidance the existing engines' own prompts receive."""
    hook = critique.improved_hook or concept.hook
    lines = [f"Creative direction — concept “{concept.name}”",
             f"Angle: {concept.angle}",
             f"Hook (first 2-3 s): {hook}",
             f"Audience: {brief.audience}; goal: {brief.goal}; tone: {brief.tone}"]
    if concept.beats:
        lines.append("Arc: " + " → ".join(f"{b.role}: {b.intent}" for b in concept.beats if b.role or b.intent))
        picks = [f"sentence {b.sentence}: {b.visual} [{b.motion}]" for b in concept.beats if b.sentence is not None and b.visual]
        if picks:
            lines.append("Visual ideas anchored to the talk:\n- " + "\n- ".join(picks))
    if concept.visual_language:
        lines.append(f"Visual language: {concept.visual_language}")
    if concept.pacing:
        lines.append(f"Pacing: {concept.pacing}")
    if critique.improvements:
        lines.append("Apply: " + "; ".join(critique.improvements))
    if brief.must_not:
        lines.append("Must not: " + "; ".join(brief.must_not))
    lines.append("Follow this direction where it agrees with the transcript; the transcript always wins.")
    return "\n".join(lines)


def _direct(kind: str, understand_system: str, source_text: str, caps: str, *, budget_s: float) -> CreativePlan:
    started = time.monotonic()
    used: list[str] = []
    guide = prompts.STRUCTURE_GUIDE[kind]

    brief = llm.ask(ContentBrief, understand_system, source_text, route=llm.DIRECTOR_ROUTE, tokens=4000, used=used)
    brief.kind = kind  # the caller knows the kind better than the model

    context = f"{llm.dumps(brief.model_dump())}\n\nSource:\n{source_text}\n\n{guide}\n\nCapabilities:\n{caps}"
    proposal = llm.ask(_Concepts, prompts.PROPOSE, context, route=llm.DIRECTOR_ROUTE, tokens=6000, used=used)
    concepts = [c for c in proposal.concepts if c.hook and c.angle][:3]
    if not concepts:
        raise CreativeUnavailable("no usable concepts returned")
    for index, concept in enumerate(concepts):  # ids must be unique and stable
        concept.id = "ABC"[index]
        if kind != "talk":
            concept.style_hint = None

    critique: Critique
    if time.monotonic() - started > budget_s:
        critique = _fallback_critique(concepts, "time budget")
    else:
        try:
            review_input = llm.dumps({"brief": brief.model_dump(), "concepts": [c.model_dump() for c in concepts]})
            critique = llm.ask(Critique, prompts.CRITIQUE, review_input + f"\n\nCapabilities:\n{caps}", route=llm.CRITIC_ROUTE,
                               tokens=3000, used=used)
        except CreativeUnavailable as exc:
            log.warning("creative critique skipped: %s", exc)
            critique = _fallback_critique(concepts, "reviewer unavailable")

    chosen = _pick(critique, concepts)
    critique.chosen_id = chosen.id
    _expand(chosen, brief, critique, caps, guide, used, started, budget_s, source_text)
    style = chosen.style_hint if (kind == "talk" and chosen.style_hint in capabilities.TALKING_STYLES) else None
    return CreativePlan(kind=kind, brief=brief, concepts=concepts, critique=critique, chosen=chosen, style=style,
                        director_notes=compose_notes(brief, chosen, critique), models=used,
                        elapsed_s=round(time.monotonic() - started, 1))


def direct_talk(sentences: list[dict], request: str = "", *, style: str | None = None,
                budget_s: float = DEFAULT_BUDGET_S) -> CreativePlan:
    if not sentences:
        raise CreativeUnavailable("no speech in the transcript")
    source = "Transcript sentences:\n" + _numbered(sentences) + (f"\n\nWhat the creator asked for: {request}" if request.strip() else "")
    plan = _direct("talk", prompts.UNDERSTAND_TALK, source, capabilities.talk_capabilities(style), budget_s=budget_s)
    if style in capabilities.TALKING_STYLES:
        plan.style = style  # the creator's explicit choice always wins over the director's
    return plan


def direct_product(facts: dict | None, request: str, *, image_count: int = 0, duration_s: int = 30,
                   budget_s: float = DEFAULT_BUDGET_S, assets: list[dict] | None = None) -> CreativePlan:
    source = (f"What the user asked for: {request}\nTarget length: {duration_s} seconds. Usable images available: {image_count}.\n"
              f"Verified facts (from the page / user):\n{llm.dumps(facts or {})}\n"
              f"Visually inspected assets (only listed indices may be used):\n{llm.dumps(assets or [])}")
    return _direct("product", prompts.UNDERSTAND_PRODUCT, source, capabilities.product_capabilities(), budget_s=budget_s)


def direct_idea(request: str, *, image_count: int = 0, duration_s: int = 30, budget_s: float = DEFAULT_BUDGET_S,
                assets: list[dict] | None = None) -> CreativePlan:
    kind = "images" if image_count else "idea"
    source = (f"The brief: {request}\nTarget length: {duration_s} seconds. Images supplied by the user: {image_count}.\n"
              f"Visually inspected assets (only listed indices may be used):\n{llm.dumps(assets or [])}")
    return _direct(kind, prompts.UNDERSTAND_IDEA, source, capabilities.product_capabilities(), budget_s=budget_s)
