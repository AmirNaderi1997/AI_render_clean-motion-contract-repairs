"""Burn captions.ass onto a rendered video with an ffmpeg that has libass.

Some MLT builds (for example the melt bundled with Shotcut) ship without the
libass-backed ``avfilter.subtitles`` filter, so MLT can only draw single-colour
SRT captions. When an ffmpeg with the ``subtitles`` filter is available the
build step leaves captions out of the MLT graph and this module burns the ASS
file after melt instead.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Optional

# Homebrew's default ffmpeg formula is built without libass; ffmpeg-full is
# keg-only, so look for it explicitly before falling back to PATH.
_CANDIDATES = (
    "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
    "/usr/local/opt/ffmpeg-full/bin/ffmpeg",
)


def _has_subtitles_filter(ffmpeg: str) -> bool:
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return any(line.split()[1:2] == ["subtitles"] for line in result.stdout.splitlines())


@lru_cache(maxsize=1)
def ass_burner_ffmpeg() -> Optional[str]:
    """Return an ffmpeg executable with the libass ``subtitles`` filter, or None."""
    if os.environ.get("AI_RENDER_DISABLE_ASS_BURN", "").lower() in {"1", "true", "yes"}:
        return None
    configured = os.environ.get("AI_RENDER_ASS_FFMPEG", "").strip()
    candidates = [configured] if configured else []
    candidates += [c for c in _CANDIDATES if Path(c).is_file()]
    on_path = shutil.which("ffmpeg")
    if on_path:
        candidates.append(on_path)
    for candidate in dict.fromkeys(candidates):
        if _has_subtitles_filter(candidate):
            return candidate
    return None


def _filter_value(value: str) -> str:
    """Escape a path for use as a filter option inside a filtergraph."""
    option = value.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    graph = option.replace("\\", "\\\\").replace("'", "\\'")
    for ch in "[],;":
        graph = graph.replace(ch, "\\" + ch)
    return graph


def subtitles_filter(ass: Path, fonts_dir: Optional[Path]) -> str:
    vf = f"subtitles=filename={_filter_value(str(ass))}"
    if fonts_dir:
        vf += f":fontsdir={_filter_value(str(fonts_dir))}"
    return vf


def burn_ass(
    src: Path,
    dst: Path,
    ass: Path,
    fonts_dir: Optional[Path] = None,
    *,
    crf: int = 20,
    preset: str = "medium",
    time_offset: float = 0.0,
    still: bool = False,
) -> Path:
    """Write ``src`` with ``ass`` burned in to ``dst``.

    ``time_offset`` shifts the input clock before libass draws, which lets a
    single exported frame pick up the captions active at that timeline time.
    """
    ffmpeg = ass_burner_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError("no ffmpeg with the libass subtitles filter is available")
    vf = subtitles_filter(Path(ass), Path(fonts_dir) if fonts_dir else None)
    # Offset the input clock rather than the filter's PTS: libass reads the
    # input timestamp, and a setpts on a single still is not honoured.
    offset = ["-itsoffset", f"{time_offset:.6f}"] if time_offset else []
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *offset, "-i", str(src), "-vf", vf]
    if still:
        cmd += ["-frames:v", "1", "-q:v", "2"]
    else:
        cmd += ["-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-crf", str(crf),
                "-preset", preset, "-pix_fmt", "yuv420p", "-c:a", "copy",
                "-movflags", "+faststart"]
    cmd.append(str(dst))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ASS caption burn failed: {proc.stderr.strip()[-800:]}")
    return Path(dst)
