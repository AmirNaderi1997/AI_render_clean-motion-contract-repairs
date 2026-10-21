"""Talking-head style 4: quiet, full-frame and intentionally non-generative.

This option keeps the real speaker on screen, uses restrained color and
calmer multi-word captions, and avoids AI B-roll entirely. It is the reliable
minimal alternative when generated imagery would make the reel feel fake.

Captions, the hook and key moments are drawn by the Tscaps engine (engine/tscaps_overlay.py) as a transparent
layer composited by ffmpeg. If that layer cannot be produced the reel is rendered with the built-in ASS text.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from engine import tscaps_overlay as tso

from . import talking_2 as base

track_faces = base.track_faces
probe_video = base.probe_video


def plan_reel(transcript: dict, decisions: dict, faces: list[tuple[float, float, float]], duration: float,
              pictures: Optional[dict[int, str]] = None) -> base.ReelPlan:
    clean = {**decisions, "broll": [], "chips": [], "titles": []}
    plan = base.plan_reel(transcript, clean, faces, duration, pictures={}, continuous_split=False)
    plan.theme = "minimal"
    return plan


def render(video: Path, plan: base.ReelPlan, out: Path, *, work_dir: Path, **kwargs) -> Path:
    fps = int(round(base.eval_fps(base.probe_fps(video)) or 30))
    return tso.render_with_overlay(
        base.render_plain, video, plan, out, work_dir=work_dir, cues=tso.reel_cues(plan),
        strip=lambda p: tso.without(p, captions=[], hook=None), fps=fps, duration=plan.duration, **kwargs)
