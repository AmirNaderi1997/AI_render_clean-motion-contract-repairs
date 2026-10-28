"""Bind source-grounded Director beats to existing local motion recipes.

This selects a visual resource inside an explicitly selected style. It does not
select an agent, provider, render engine, or download external code.
"""
from engine.motion_recipes import RECIPES
from .selection import ResourceRequirements, assess_resource


def plan_talking_resources(beats, sentences: list[dict], style: str | None) -> list[dict]:
    if style != "talking_2":
        return []
    usage: dict[str, int] = {}
    choices = []
    for index, beat in enumerate(beats):
        sentence = beat.sentence
        base = {"beat_index": index, "sentence": sentence, "resource_id": None}
        if sentence is None or not 0 <= sentence < len(sentences):
            choices.append({**base, "reason": "missing-source-anchor"})
            continue
        evidence = str(sentences[sentence].get("text") or "")
        if beat.visual_type == "stat" and not any(c.isdigit() for c in evidence):
            choices.append({**base, "reason": "no-numeric-source-evidence"})
            continue
        candidates = [r for r in RECIPES if r.renderer == beat.visual_type
                      and r.talking_safe and usage.get(r.id, 0) < r.max_per_video]
        candidates.sort(key=lambda r: (-(beat.role in r.intents), r.id))
        selected = None
        for recipe in candidates:
            rid = f"editorgpt-recipe:{recipe.id}"
            if assess_resource(rid, ResourceRequirements(context=style, engine="hyperframes", kind="motion-preset"))["eligible"]:
                selected = recipe
                break
        if selected is None:
            choices.append({**base, "reason": "no-compatible-local-recipe"})
            continue
        usage[selected.id] = usage.get(selected.id, 0) + 1
        choices.append({**base, "resource_id": f"editorgpt-recipe:{selected.id}",
                        "reason": "matching-visual-type-and-source-anchor",
                        "source_text": evidence[:600], "visual_type": beat.visual_type})
    return choices


def resolve_talking_recipe(resource_id: str, visual_type: str):
    """Revalidate a persisted choice at compilation; IDs cannot inject a path."""
    from .registry import get_resource
    if not assess_resource(resource_id, ResourceRequirements(
            context="talking_2", engine="hyperframes", kind="motion-preset"))["eligible"]:
        raise ValueError("Unsupported talking motion resource")
    row = get_resource(resource_id)
    recipe = next((r for r in RECIPES if r.id == row["legacy_id"]), None)
    if recipe is None or recipe.renderer != visual_type or not recipe.talking_safe:
        raise ValueError("Motion resource does not match this visual beat")
    return recipe
