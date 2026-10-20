"""Talking-head style 4: quiet, full-frame and intentionally non-generative.

This option keeps the real speaker on screen, uses restrained color and
calmer multi-word captions, and avoids AI B-roll entirely. It is the reliable
minimal alternative when generated imagery would make the reel feel fake.

Captions, the hook and key moments are drawn by the Tscaps engine (engine/tscaps_overlay.py) as a transparent
layer composited by ffmpeg. If that layer cannot be produced the reel is rendered with the built-in ASS text.
"""
from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import Callable, Optional

from . import talking_2 as base

log = logging.getLogger(__name__)

track_faces = base.track_faces
probe_video = base.probe_video


def plan_reel(transcript: dict, decisions: dict, faces: list[tuple[float, float, float]], duration: float,
              pictures: Optional[dict[int, str]] = None) -> base.ReelPlan:
    clean = {**decisions, "broll": [], "chips": [], "titles": []}
    plan = base.plan_reel(transcript, clean, faces, duration, pictures={})
    plan.theme = "minimal"
    return plan


def _overlay(video: Path, plan: base.ReelPlan, work_dir: Path, settings: dict) -> Optional[Path]:
    from engine import tscaps_overlay as tso
    cues = tso.reel_cues(plan)
    if not cues:
        return None
    try:
        fps = base.eval_fps(base.probe_fps(video))
        return tso.render_overlay(cues, work_dir / "tscaps_overlay.webm", width=base.W, height=base.H,
                                  fps=int(round(fps or 30)), duration=plan.duration + 0.1, work_dir=work_dir)
    except tso.OverlayUnavailable as exc:
        log.warning("tscaps overlay unavailable, using built-in captions: %s", str(exc)[:240])
    except Exception as exc:  # the overlay may improve a reel; it must never fail one
        log.warning("tscaps overlay failed, using built-in captions: %s", str(exc)[:240])
    return None


def render(video: Path, plan: base.ReelPlan, out: Path, *, work_dir: Path, **kwargs) -> Path:
    overlay = _overlay(video, plan, work_dir, kwargs.get("render_settings") or {})
    if overlay:
        try:
            return base.render(video, dataclasses.replace(plan, captions=[], hook=None), out, work_dir=work_dir,
                               overlay=overlay, **kwargs)
        except Exception as exc:
            log.warning("render with the tscaps overlay failed (%s); rendering with built-in captions", str(exc)[:240])
    return base.render(video, plan, out, work_dir=work_dir, **kwargs)
