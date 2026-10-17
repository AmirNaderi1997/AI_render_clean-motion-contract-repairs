"""Audited, renderable motion recipes shared by talking and product reels.

The external catalogs are discovery sources.  This registry is deliberately
smaller: every item maps to a local, deterministic renderer and carries the
semantic/restraint fields needed by the planner and review UI.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re


@dataclass(frozen=True)
class MotionRecipe:
    id: str
    title: str
    renderer: str
    intents: tuple[str, ...]
    best_for: str
    avoid_when: str
    max_per_video: int = 1
    portrait_safe: bool = True
    talking_safe: bool = False
    motion: str = "reveal"


RECIPES = (
    MotionRecipe("kinetic-hook-slam", "Kinetic hook slam", "kinetic_type", ("hook", "claim", "headline"), "Short, forceful opening claims", "Long sentences", 1, motion="slam"),
    MotionRecipe("editorial-word-build", "Editorial word build", "kinetic_type", ("idea", "quote", "benefit"), "One memorable statement", "Lists or dense copy", 2, True, True, "type_on"),
    MotionRecipe("metric-count-up", "Metric count up", "stat", ("number", "metric", "growth", "price"), "One defensible number", "Claims with no numeric evidence", 2, True, True, "count_up"),
    MotionRecipe("price-flip", "Price comparison flip", "comparison", ("price", "saving", "comparison"), "Before/after prices", "More than two values", 1, motion="wipe"),
    MotionRecipe("versus-split", "Versus split", "comparison", ("versus", "choice", "comparison"), "Two alternatives", "A single concept", 1, True, True, "assemble"),
    MotionRecipe("steps-rail", "Progressive steps rail", "steps", ("steps", "process", "how", "workflow"), "Two to four ordered steps", "Unordered benefits", 1, True, True, "assemble"),
    MotionRecipe("feature-stack", "Feature stack", "spec_callout", ("feature", "benefit", "spec"), "Up to three concrete features", "Generic adjectives", 1, True, True, "reveal"),
    MotionRecipe("ui-window-reveal", "Product UI reveal", "ui_showcase", ("app", "software", "dashboard", "platform"), "Software and dashboards", "Physical products without UI", 2, motion="orbit"),
    MotionRecipe("media-contact-sheet", "Media contact sheet", "media_collage", ("gallery", "content", "collection", "templates"), "Several tangible examples", "One hero object", 1, motion="collage"),
    MotionRecipe("message-proof", "Message thread proof", "chat", ("chat", "review", "testimonial", "conversation"), "Social proof or conversation", "Unsupported invented testimonials", 1, motion="type_on"),
    MotionRecipe("route-journey", "Route journey", "map_route", ("global", "delivery", "location", "journey"), "Geographic movement", "No location meaning", 1, motion="reveal"),
    MotionRecipe("before-after-wipe", "Before/after wipe", "before_after", ("before", "after", "transformation", "result"), "A real transformation", "Unrelated states", 1, motion="wipe"),
    MotionRecipe("orbit-concept", "Orbit concept", "concept", ("ecosystem", "automation", "connected"), "A central idea with related parts", "Ordered steps", 1, True, True, "orbit"),
    MotionRecipe("scale-ladder", "Scale ladder", "concept", ("scale", "growth", "multiply"), "Growth from one to many", "Flat or negative change", 1, True, True, "assemble"),
    MotionRecipe("proof-stamp", "Proof stamp", "stat", ("proof", "trust", "guarantee", "score"), "A short proof point", "Long explanation", 1, motion="slam"),
    MotionRecipe("cta-lockup", "CTA lockup", "kinetic_type", ("cta", "action", "visit", "start"), "Final action and URL", "Mid-story detail", 1, motion="slam"),
    MotionRecipe("logo-orbit", "Logo orbit", "concept", ("brand", "logo", "identity"), "Brand reveal", "No usable brand name", 1, motion="orbit"),
    MotionRecipe("benefit-cards", "Benefit cards", "media_collage", ("benefit", "use-case", "audience"), "Three distinct benefits", "Repeated generic claims", 1, motion="collage"),
    MotionRecipe("timeline-pulse", "Timeline pulse", "steps", ("timeline", "speed", "launch"), "Milestones over time", "No temporal sequence", 1, motion="wipe"),
    MotionRecipe("focus-callout", "Focus callout", "spec_callout", ("detail", "highlight", "feature"), "One product detail", "A full feature list", 2, True, True, "reveal"),
)

BY_ID = {item.id: item for item in RECIPES}


def public_recipes() -> list[dict]:
    return [{**asdict(item), "intents": list(item.intents)} for item in RECIPES]


def select_recipe(*, role: str, title: str, items: list[str] | None = None,
                  used: dict[str, int] | None = None, talking: bool = False) -> MotionRecipe:
    """Choose a semantically relevant recipe with deterministic restraint."""
    usage = used or {}
    text = " ".join([role, title, *(items or [])]).lower()
    tokens = set(re.findall(r"[a-z0-9\u0600-\u06ff-]+", text))
    synonyms = {
        "hook": {"hook", "قلاب", "تیتر"}, "price": {"price", "قیمت", "$", "دلار"},
        "steps": {"steps", "مرحله", "روش", "چطور"}, "feature": {"feature", "ویژگی", "قابلیت"},
        "benefit": {"benefit", "مزیت", "نتیجه"}, "cta": {"cta", "شروع", "ببین", "خرید", "ثبت"},
        "number": {"عدد", "درصد", "آمار", "%"}, "app": {"app", "نرم", "پلتفرم", "داشبورد"},
        "comparison": {"مقایسه", "در برابر", "vs"}, "transformation": {"قبل", "بعد", "تغییر"},
    }
    expanded = set(tokens)
    for key, values in synonyms.items():
        if tokens & values or any(value in text for value in values):
            expanded.add(key)
    ranked: list[tuple[int, str, MotionRecipe]] = []
    for recipe in RECIPES:
        if talking and not recipe.talking_safe:
            continue
        if usage.get(recipe.id, 0) >= recipe.max_per_video:
            continue
        score = 6 * len(expanded & set(recipe.intents))
        if role in recipe.intents:
            score += 9
        if re.search(r"[0-9۰-۹٪%$]", text) and recipe.renderer == "stat":
            score += 8
        ranked.append((score, recipe.id, recipe))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return ranked[0][2] if ranked else BY_ID["editorial-word-build"]
