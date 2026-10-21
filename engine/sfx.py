"""Synthesised sound design for authored motion scenes.

Every sound is generated here with ffmpeg (noise, sine and envelopes), so there is no third-party audio and no
licence question: a short whoosh when a scene arrives and when the speaker returns, a soft hit as the main word
lands. They are quiet on purpose; the voice stays the loudest thing in the mix."""
from __future__ import annotations

import subprocess
from pathlib import Path

RECIPES: dict[str, tuple[str, str]] = {
    "whoosh": ("anoisesrc=d=0.6:c=pink:a=0.9:r=44100",
               "highpass=f=400,lowpass=f=6000,afade=t=in:d=0.28:curve=qsin,afade=t=out:st=0.28:d=0.32:curve=exp"),
    "hit": ("aevalsrc='0.9*sin(2*PI*(55+90*exp(-t*28))*t)*exp(-t*9)':d=0.5:s=44100", "lowpass=f=300,volume=1.2"),
    "pop": ("aevalsrc='0.8*sin(2*PI*(420+900*t)*t)*exp(-t*38)':d=0.18:s=44100", "anull"),
    "tick": ("aevalsrc='0.7*sin(2*PI*2600*t)*exp(-t*160)':d=0.06:s=44100", "anull"),
    "riser": ("anoisesrc=d=1.1:c=white:a=0.7:r=44100", "highpass=f=900,lowpass=f=9000,afade=t=in:d=1.0:curve=exp,afade=t=out:st=1.0:d=0.1"),
}
DURATION = {"whoosh": 0.6, "hit": 0.5, "pop": 0.18, "tick": 0.06, "riser": 1.1}
GAIN = {"whoosh": 0.30, "hit": 0.34, "pop": 0.30, "tick": 0.22, "riser": 0.22}


def ensure(directory: Path, names: set[str] | None = None) -> dict[str, Path]:
    """Create the requested sounds in `directory` (once) and return name -> file. Missing ffmpeg means no sound, not an error."""
    directory.mkdir(parents=True, exist_ok=True)
    made: dict[str, Path] = {}
    for name in sorted(names or RECIPES):
        source, chain = RECIPES[name]
        target = directory / f"{name}.wav"
        if not target.is_file():
            try:
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", source, "-af", chain, str(target)],
                               check=True, capture_output=True, timeout=60)
            except (OSError, subprocess.SubprocessError):
                continue
        made[name] = target
    return made


def cues_for(beats: list) -> list[tuple[float, str]]:
    """(time, sound) pairs for authored beats: arrive, land, return."""
    cues: list[tuple[float, str]] = []
    for beat in beats:
        if not getattr(beat, "custom", None):
            continue
        cues.append((max(0.0, beat.start - 0.04), "whoosh"))
        cues.append((beat.start + 0.34, "hit"))
        if beat.custom.get("speaker") in {"pip", "dim", "hidden"}:
            cues.append((max(beat.start + 0.8, beat.end - 0.5), "whoosh"))
    cues.sort()
    return cues


def markup(cues: list[tuple[float, str]], duration: float, files: dict[str, Path], track: int = 5) -> str:
    """<audio> clips for the HyperFrames root; HyperFrames mixes them with the speaker's audio."""
    parts = []
    lane_ends: list[float] = []
    for index, (time, name) in enumerate(sorted(cues)):
        if name not in files or time >= duration - 0.1:
            continue
        length = min(DURATION[name], duration - time)
        # Overlapping sound design is intentional, but each simultaneous clip
        # needs its own lane. Reuse lanes only after their preceding clip ends.
        lane = next((i for i, end in enumerate(lane_ends) if end <= time), len(lane_ends))
        if lane == len(lane_ends):
            lane_ends.append(time + length)
        else:
            lane_ends[lane] = time + length
        parts.append(f'<audio id="sfx-{index}" src="./assets/sfx/{name}.wav" data-start="{time:.3f}" data-duration="{length:.3f}" '
                     f'data-track-index="{track + lane}" data-volume="{GAIN[name]}"></audio>')
    return "\n".join(parts)
