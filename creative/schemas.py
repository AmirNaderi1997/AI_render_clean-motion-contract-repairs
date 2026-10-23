"""Typed contracts of the Creative Engine. Tolerant on input (models vary), strict on output."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreativeUnavailable(RuntimeError):
    """The creative layer could not produce a validated result. Callers fall back to the standard pipeline."""


def _text(value: Any, limit: int = 600) -> str:
    return " ".join(str(value or "").split())[:limit]


def _texts(value: Any, limit: int = 8, size: int = 300) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [_text(v, size) for v in (value or []) if _text(v, size)][:limit]


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class KeyMoment(_Model):
    i: int = Field(ge=0)
    why: str = ""
    emotion: str = ""

    @field_validator("why", "emotion", mode="before")
    @classmethod
    def _clean(cls, value):
        return _text(value, 240)


Kind = Literal["talk", "product", "idea", "images"]


class ContentBrief(_Model):
    kind: Kind = "talk"
    topic: str
    core_message: str
    audience: str = ""
    goal: str = ""
    tone: str = ""
    genre: Literal["education", "story", "motivation", "sales", "explainer", "showcase"] = "explainer"
    emotional_arc: list[str] = Field(default_factory=list)
    key_moments: list[KeyMoment] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)   # facts actually present in the source
    must_not: list[str] = Field(default_factory=list)       # claims/edits that would distort the source

    @field_validator("topic", "core_message", "audience", "goal", "tone", mode="before")
    @classmethod
    def _clean(cls, value):
        return _text(value)

    @field_validator("emotional_arc", "proof_points", "must_not", mode="before")
    @classmethod
    def _list(cls, value):
        return _texts(value)

    @field_validator("key_moments", mode="before")
    @classmethod
    def _moments(cls, value):
        return [v for v in (value or []) if isinstance(v, dict)][:8]


class Beat(_Model):
    role: str = ""                 # hook | setup | claim | proof | turn | payoff | cta ...
    intent: str = ""               # what the viewer should feel/understand here
    visual: str = ""               # concrete on-screen idea (not "nice visuals")
    motion: str = ""               # motion/typography treatment, in terms the engine can render
    sentence: int | None = None    # transcript sentence index when the source is a talk
    title: str = ""
    narration: str = ""
    source_asset_index: int | None = Field(default=None, ge=0)
    visual_type: Literal["concept", "stat", "comparison", "steps", "ui_showcase", "media_collage",
                         "chat", "map_route", "spec_callout", "kinetic_type", "before_after"] = "concept"
    items: list[str] = Field(default_factory=list, max_length=4)
    duration_weight: float = Field(default=1, gt=0, le=10)
    motion_engine: Literal['default','motion_so'] = 'default'

    @field_validator("role", "intent", "visual", "motion", "title", "narration", mode="before")
    @classmethod
    def _clean(cls, value):
        return _text(value, 280)

    @field_validator("sentence", mode="before")
    @classmethod
    def _index(cls, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class Concept(_Model):
    id: str
    name: str
    angle: str                      # the creative idea in 1–2 sentences
    hook: str                       # exactly what happens in the first 2–3 seconds
    outline: list[str] = Field(default_factory=list)   # compact beat sketch from the proposal stage
    beats: list[Beat] = Field(default_factory=list)    # full beats, filled by the expansion stage
    visual_language: str = ""
    pacing: str = ""
    style_hint: str | None = None   # an existing engine style id (talk only)
    why_it_works: str = ""
    risks: str = ""

    @field_validator("id", "name", "angle", "hook", "visual_language", "pacing", "why_it_works", "risks", mode="before")
    @classmethod
    def _clean(cls, value):
        return _text(value, 500)

    @field_validator("beats", mode="before")
    @classmethod
    def _beats(cls, value):
        return [v.model_dump() if isinstance(v, Beat) else v for v in (value or []) if isinstance(v, (dict,Beat))][:9]

    @field_validator("outline", mode="before")
    @classmethod
    def _outline(cls, value):
        return _texts(value, 7, 160)


SCORE_KEYS = ("hook_strength", "originality", "fit_to_content", "feasibility", "faithfulness")


class ConceptScore(_Model):
    id: str
    hook_strength: float = 0
    originality: float = 0
    fit_to_content: float = 0
    feasibility: float = 0
    faithfulness: float = 0
    note: str = ""

    @field_validator(*SCORE_KEYS, mode="before")
    @classmethod
    def _score(cls, value):
        try:
            return max(0.0, min(10.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    @property
    def total(self) -> float:
        # Faithfulness and feasibility are gates as much as virtues: weight them up.
        return (self.hook_strength * 1.3 + self.originality + self.fit_to_content * 1.2
                + self.feasibility * 1.2 + self.faithfulness * 1.3)


class Critique(_Model):
    scores: list[ConceptScore] = Field(default_factory=list)
    chosen_id: str
    verdict: str = ""
    improvements: list[str] = Field(default_factory=list)
    improved_hook: str = ""

    @field_validator("verdict", "improved_hook", mode="before")
    @classmethod
    def _clean(cls, value):
        return _text(value, 500)

    @field_validator("improvements", mode="before")
    @classmethod
    def _list(cls, value):
        return _texts(value, 6, 300)


class CreativePlan(_Model):
    schema_version: int = 2
    kind: Kind
    brief: ContentBrief
    concepts: list[Concept]
    critique: Critique
    chosen: Concept
    style: str | None = None
    director_notes: str = ""                    # compact guidance the engines receive
    models: list[str] = Field(default_factory=list)
    elapsed_s: float = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def public(self) -> dict:
        """What may be stored on a job and shown to the user: the decision and its reasons, not raw prompts."""
        return {
            "schema_version": self.schema_version,
            "kind": self.kind, "style": self.style, "created_at": self.created_at, "elapsed_s": self.elapsed_s,
            "brief": self.brief.model_dump(),
            "chosen": self.chosen.model_dump(),
            "alternatives": [{"id": c.id, "name": c.name, "angle": c.angle, "hook": c.hook, "style_hint": c.style_hint,
                              "visual_language": c.visual_language, "pacing": c.pacing, "why_it_works": c.why_it_works}
                             for c in self.concepts if c.id != self.chosen.id],
            "verdict": self.critique.verdict, "director_notes": self.director_notes,
            "critique":self.critique.model_dump(),
        }
