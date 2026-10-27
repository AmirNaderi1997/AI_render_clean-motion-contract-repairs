"""Style packs: a complete, data-only look for an edited video (captions, hook, panels, rhythm, grade, sound).

A pack is plain data composed from building blocks the renderers implement, so a new pack is never new code: the director can
compose one per video, a reference video can be turned into one, and a pack the creator liked can be saved and reused.
Rendering lives in engine/talking_styles/talking_5.py and engine/hyperframes/overlay_reel.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

CAPTION_MODES = ("words", "phrase", "slam")                # word-by-word pages, calm phrases, one big word at a time
HOOK_MODES = ("headline", "slam", "none")
PANEL_THEMES = ("paper", "ink", "gradient")
PANEL_SCENES = ("stack", "versus", "stat", "kinetic", "steps")


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Palette(_M):
    panel_bg: str = "#EFE9DD"          # the panel behind the picture cards (and behind the speaker card's rounded corners)
    panel_ink: str = "#15181A"
    card: str = "#FFFFFF"
    accent: str = "#F26B5B"
    accent_2: str = "#2F7D6B"
    highlight: str = "#FFD23F"         # the word being said
    dark: str = "#0E1112"

    @field_validator("*")
    @classmethod
    def _hex(cls, value: str) -> str:
        if not HEX.match(value):
            raise ValueError("colours are #RRGGBB")
        return value


class CaptionStyle(_M):
    mode: Literal["words", "phrase", "slam"] = "words"
    per_page: int = Field(default=3, ge=1, le=5)
    size_full: int = Field(default=96, ge=56, le=150)
    size_split: int = Field(default=84, ge=48, le=130)
    y_full: float = Field(default=0.70, ge=0.45, le=0.88)       # vertical centre as a fraction of the frame height
    pop: bool = True                                             # each word pops in as it is said
    box: bool = False                                            # a soft dark pill behind the line


class HookStyle(_M):
    mode: Literal["headline", "slam", "none"] = "headline"
    seconds: float = Field(default=3.0, ge=1.5, le=5.0)
    size: int = Field(default=92, ge=56, le=140)


class Rhythm(_M):
    split_ratio: float = Field(default=0.6, ge=0.0, le=1.0)      # share of the video shown as panel + speaker card
    close_zoom: float = Field(default=1.22, ge=1.0, le=1.6)      # punch-in scale on emphasis shots
    cut_min: float = Field(default=1.6, ge=0.8, le=4.0)
    cut_max: float = Field(default=2.8, ge=1.2, le=6.0)


class StylePack(_M):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,40}$")
    title: str = Field(max_length=60)
    summary: str = Field(default="", max_length=300)
    best_for: str = Field(default="", max_length=200)
    palette: Palette = Field(default_factory=Palette)
    panel_theme: Literal["paper", "ink", "gradient"] = "paper"
    caption: CaptionStyle = Field(default_factory=CaptionStyle)
    hook: HookStyle = Field(default_factory=HookStyle)
    rhythm: Rhythm = Field(default_factory=Rhythm)
    accent_font: Literal["Kharazmi", "Ray"] = "Kharazmi"          # the "serif italic" voice of the reference, in Persian
    grade: str = "warm"                                           # warm | cool | neutral
    source: str = ""                                              # what it was derived from ("reference: file.mp4", "director")


# The look measured in the reference reel (a fast AI-tools explainer): cream panels, coral/teal accents, rounded speaker card at the
# bottom, white word-by-word captions, hard cuts about every two seconds, a warm grade on the speaker.
REFERENCE_AI_NEWS = StylePack(
    id="ref-ai-news", title="اخبار ابزار و اکسپلینر سریع", source="reference: o88ewi7khq.mp4",
    summary="پنل کرم با کارت‌های گرد، گوینده در کارت پایین، زیرنویس سفید کلمه‌به‌کلمه، برش‌های تند هر ۲ ثانیه، گرید گرم.",
    best_for="معرفی ابزار، آموزش سریع، اکسپلینر صحبتی",
    palette=Palette(), panel_theme="paper",
    caption=CaptionStyle(mode="words", per_page=3, size_full=96, size_split=84, pop=True),
    hook=HookStyle(mode="headline", seconds=3.0, size=92),
    rhythm=Rhythm(split_ratio=0.6, close_zoom=1.22, cut_min=1.6, cut_max=2.8),
    accent_font="Kharazmi", grade="warm",
)

BOLD_VIRAL = StylePack(
    id="bold-viral", title="بولد وایرال", source="preset",
    summary="زیرنویس خیلی درشت زرد، پانچ‌زوم روی تأکیدها، پس‌زمینه‌ی تیره، انرژی بالا.",
    best_for="ریلز انگیزشی، فروش، کلیپ کوتاه پرانرژی",
    palette=Palette(panel_bg="#0E1112", panel_ink="#F4F1E8", card="#1B2022", accent="#FFD23F", accent_2="#FF5A5F", highlight="#FFD23F", dark="#050607"),
    panel_theme="ink",
    caption=CaptionStyle(mode="slam", per_page=2, size_full=124, size_split=104, y_full=0.66, pop=True),
    hook=HookStyle(mode="slam", seconds=2.6, size=110),
    rhythm=Rhythm(split_ratio=0.35, close_zoom=1.35, cut_min=1.2, cut_max=2.2),
    accent_font="Ray", grade="warm",
)

CALM_PODCAST = StylePack(
    id="calm-podcast", title="مینیمال پادکست", source="preset",
    summary="زیرنویس آرام و کوچک‌تر، بدون پنل، گوینده تمام‌قاب، رنگ‌های خنثی.",
    best_for="مصاحبه، پادکست، محتوای جدی و تأمل‌برانگیز",
    palette=Palette(panel_bg="#E9E6DF", panel_ink="#1A1C1D", accent="#8A6F4D", accent_2="#3F5E5A", highlight="#FFFFFF"),
    panel_theme="paper",
    caption=CaptionStyle(mode="phrase", per_page=4, size_full=76, size_split=70, y_full=0.76, pop=False, box=True),
    hook=HookStyle(mode="headline", seconds=2.5, size=72),
    rhythm=Rhythm(split_ratio=0.0, close_zoom=1.12, cut_min=2.4, cut_max=4.5),
    accent_font="Kharazmi", grade="neutral",
)

PRESETS = {p.id: p for p in (REFERENCE_AI_NEWS, BOLD_VIRAL, CALM_PODCAST)}


def get(pack_id: str) -> StylePack:
    return PRESETS[pack_id]


def parse(value: str | dict | StylePack) -> StylePack:
    """A pack from JSON / a dict (a saved or director-composed pack), validated; raises ValueError with the reason."""
    if isinstance(value, StylePack):
        return value
    data = json.loads(value) if isinstance(value, str) else value
    return StylePack.model_validate(data)


def save(pack: StylePack, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{pack.id}.json"
    path.write_text(pack.model_dump_json(indent=1), encoding="utf-8")
    return path
