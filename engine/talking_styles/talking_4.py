"""Talking-head style 4: quiet, full-frame and intentionally non-generative.

This option keeps the real speaker on screen, uses restrained color and
calmer multi-word captions, and avoids AI B-roll entirely. It is the reliable
minimal alternative when generated imagery would make the reel feel fake.
"""
from __future__ import annotations

from typing import Optional

from . import talking_2 as base

track_faces = base.track_faces
probe_video = base.probe_video
render = base.render


def plan_reel(transcript: dict, decisions: dict, faces: list[tuple[float, float, float]], duration: float,
              pictures: Optional[dict[int, str]] = None) -> base.ReelPlan:
    clean = {**decisions, "broll": [], "chips": [], "titles": []}
    plan = base.plan_reel(transcript, clean, faces, duration, pictures={})
    plan.theme = "minimal"
    return plan
