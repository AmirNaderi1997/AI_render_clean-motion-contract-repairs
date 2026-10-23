"""The caption fonts the renders use (presets/fonts), so the browser can draw captions with the very same files."""
from __future__ import annotations

import re
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parents[1] / "presets" / "fonts"
EXTENSIONS = {".ttf", ".otf"}


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _files() -> dict[str, Path]:
    return {p.name: p for p in FONT_DIR.rglob("*") if p.suffix.lower() in EXTENSIONS and p.is_file()}


def font_file(family: str) -> str | None:
    """The file name that carries an ASS font family ("Ray ExtraBlack" -> RAY-EXTRABLACK.TTF), or None."""
    wanted = _norm(family)
    if not wanted:
        return None
    exact = [name for name in _files() if _norm(Path(name).stem) == wanted]
    if exact:
        return exact[0]
    prefix = sorted(name for name in _files() if _norm(Path(name).stem).startswith(wanted))
    return prefix[0] if prefix else None


def path_for(name: str) -> Path | None:
    return _files().get(name)
