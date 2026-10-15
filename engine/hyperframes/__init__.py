"""HyperFrames visual-composition bridge for talking reels."""

from .builder import build_project, build_visual_beats
from .renderer import HyperFramesError, render_project
from .schema import VisualBeat

__all__ = ["VisualBeat", "build_project", "build_visual_beats", "render_project", "HyperFramesError"]
