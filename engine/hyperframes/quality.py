"""Small deterministic post-render review for talking-head motion graphics."""
from __future__ import annotations

import subprocess
import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

def review_render(video: Path, beats: list, work_dir: Path) -> dict:
    problems: list[str] = []
    warnings: list[str] = []
    unavailable: list[str] = []
    media = {}
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                                 '-of', 'json', str(video)], capture_output=True, text=True, timeout=30, check=True)
        data = json.loads(result.stdout)
        stream = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), None)
        if not stream:
            problems.append('output has no video stream')
        else:
            duration = float(stream.get('duration') or data.get('format', {}).get('duration') or 0)
            width, height = int(stream.get('width', 0)), int(stream.get('height', 0))
            media = {'duration_s': duration if math.isfinite(duration) else None, 'width': width, 'height': height,
                     'has_audio': any(s.get('codec_type') == 'audio' for s in data.get('streams', []))}
            if not math.isfinite(duration) or duration <= 0 or min(width, height) <= 0:
                problems.append('output has invalid dimensions or duration')
            if any(b.end > duration + .15 for b in beats):
                problems.append('output ends before an approved visual beat')
    except (subprocess.SubprocessError, OSError, ValueError, TypeError):
        unavailable.append('output metadata could not be inspected')
    continuous = bool(beats) and all(b.layout == 'top_panel' for b in beats)
    if len(beats) < 4 and not continuous:
        warnings.append("fewer than four visual worlds")
    if not continuous and any(beat.end - beat.start > 2.5 for beat in beats):
        warnings.append("a visual remains on screen longer than 2.5 seconds")
    if any(beat.layout not in {'full_frame', 'top_panel'} for beat in beats):
        warnings.append("speaker occlusion requires visual review")
    if not continuous and any(a.visual_type == b.visual_type for a, b in zip(beats, beats[1:])):
        warnings.append("consecutive scenes repeat the same visual grammar")
    primaries = [beat.registry_refs[0] for beat in beats if beat.registry_refs]
    if continuous and any(abs(a.end-b.start) > .04 for a,b in zip(beats,beats[1:])):
        problems.append('explanatory motion has uncovered gaps')
    if len(primaries) != len(set(primaries)):
        warnings.append("catalog templates repeat")

    sample_dir = work_dir / "visual_qc"
    sample_dir.mkdir(parents=True, exist_ok=True)
    images = []
    for index, beat in enumerate(beats):
        target = sample_dir / f"beat-{index:02d}.jpg"
        if target.exists():
            target.unlink()  # A failed extraction must not reuse a prior render's frame.
        try:
            extracted=subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss",
                f"{(beat.start + beat.end) / 2:.3f}", "-i", str(video), "-frames:v", "1",
                "-vf", "crop=iw:min(ih\\,888):0:0,scale=96:79" if continuous else "scale=96:170", str(target),
            ], check=False, capture_output=True, timeout=40)
        except (OSError, subprocess.SubprocessError):
            unavailable.append(f"could not inspect actual scene {beat.id}")
            continue
        if extracted.returncode==0 and target.is_file():
            with Image.open(target) as source:
                images.append(source.convert("RGB"))
        else:
            unavailable.append(f"could not inspect actual scene {beat.id}")
    differences = []
    for left, right in zip(images, images[1:]):
        differences.append(sum(ImageStat.Stat(ImageChops.difference(left, right)).mean) / 3)
    if differences and sum(value > 7.0 for value in differences) < min(len(differences), max(2, len(differences) // 2)):
        warnings.append("sampled scenes are visually similar; intentional repetition is allowed")
    return {"passed": not problems and not unavailable,
            "status": "failed" if problems else "unavailable" if unavailable else "passed",
            "problems": problems, "warnings": warnings, "unavailable": unavailable,
            "media": media, "samples": len(images),
            "mean_scene_change": round(sum(differences) / len(differences), 2) if differences else 0}


def improve_beats(beats: list) -> list:
    """Compatibility shim: never rewrite approved semantics to satisfy a quota.

    Repairs require a specific finding and approval through the existing plan flow.
    """
    return beats
