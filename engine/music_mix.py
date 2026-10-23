"""The music bed's mix: how loud it is under the voice, how it fades, and whether it ducks while someone speaks.

Each talking style has its own defaults (the values its renderer used before they were editable); the user's
``render_settings["music_mix"]`` overrides any of them. With no override the filter text is exactly what it always was,
so a project nobody edited renders identically.
"""
from __future__ import annotations

from dataclasses import dataclass

# style -> (volume dB, fade in s, fade out s, sidechain ratio, attack ms, release ms)
STYLE_DEFAULTS = {
    "talking_1": (-19.0, 0.8, 1.6, 5, 50, 500),
    "talking_2": (-15.0, 0.5, 1.6, 4, 40, 400),
    "talking_3": (-14.0, 0.8, 1.8, 4, 50, 500),
    "talking_4": (-15.0, 0.5, 1.6, 4, 40, 400),     # drawn by the style-2 renderer
}
LIMITS = {"volume_db": (-40.0, -3.0), "fade_in": (0.0, 5.0), "fade_out": (0.0, 8.0)}
KEYS = ("volume_db", "fade_in", "fade_out", "duck")


@dataclass(frozen=True)
class Mix:
    volume_db: float
    fade_in: float
    fade_out: float
    duck: bool
    ratio: int
    attack: int
    release: int

    def bed(self, index: int, total: float) -> str:
        """The music input's filter chain, ending in the labelled stream [m]."""
        fade_in = f"afade=t=in:d={self.fade_in}," if self.fade_in > 0 else ""
        fade_out = f"afade=t=out:st={max(0.0, total - self.fade_out):.3f}:d={self.fade_out}," if self.fade_out > 0 else ""
        return f"[{index}:a]atrim=0:{total:.3f},volume={self.volume_db}dB,{fade_in}{fade_out}aresample=48000,aformat=channel_layouts=stereo[m]"

    def graph(self, tail: str) -> list[str]:
        """The lines that mix [cpad] (the voice) with [m]; ``tail`` is what follows the mix (loudness, label)."""
        if not self.duck:
            return ["[cpad]aresample=48000,aformat=channel_layouts=stereo[vo]",
                    f"[vo][m]amix=inputs=2:normalize=0:duration=first,{tail}"]
        return ["[cpad]aresample=48000,aformat=channel_layouts=stereo,asplit[vo][key]",
                f"[m][key]sidechaincompress=threshold=0.03:ratio={self.ratio}:attack={self.attack}:release={self.release}[duck]",
                f"[vo][duck]amix=inputs=2:normalize=0:duration=first,{tail}"]


def clean(raw) -> dict:
    """Validated override fields only. Raises ValueError on a bad value."""
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict):
        raise ValueError("music mix must be an object")
    out: dict = {}
    for key, (low, high) in LIMITS.items():
        if raw.get(key) is None:
            continue
        try:
            value = float(raw[key])
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a number")
        if value != value or not low <= value <= high:
            raise ValueError(f"{key} is outside {low}..{high}")
        out[key] = round(value, 1) if key == "volume_db" else round(value, 2)
    if raw.get("duck") is not None:
        out["duck"] = bool(raw["duck"])
    return out


def resolve(style: str, settings: dict | None) -> Mix:
    db, fade_in, fade_out, ratio, attack, release = STYLE_DEFAULTS.get(style, STYLE_DEFAULTS["talking_2"])
    over = clean((settings or {}).get("music_mix"))
    return Mix(over.get("volume_db", db), over.get("fade_in", fade_in), over.get("fade_out", fade_out),
               over.get("duck", True), ratio, attack, release)


def defaults(style: str) -> dict:
    db, fade_in, fade_out, *_ = STYLE_DEFAULTS.get(style, STYLE_DEFAULTS["talking_2"])
    return {"volume_db": db, "fade_in": fade_in, "fade_out": fade_out, "duck": True}
