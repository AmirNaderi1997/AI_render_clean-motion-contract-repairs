"""Small deterministic post-render review for talking-head motion graphics."""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from .catalog import recommend


def review_render(video: Path, beats: list, work_dir: Path) -> dict:
    problems: list[str] = []
    if len(beats) < 5:
        problems.append("fewer than five visual worlds")
    if any(beat.end - beat.start > 5.2 for beat in beats):
        problems.append("a visual remains on screen too long")
    if any(a.visual_type == b.visual_type for a, b in zip(beats, beats[1:])):
        problems.append("consecutive scenes repeat the same visual grammar")
    primaries = [beat.registry_refs[0] for beat in beats if beat.registry_refs]
    if len(primaries) != len(set(primaries)):
        problems.append("catalog templates repeat")

    sample_dir = work_dir / "visual_qc"
    sample_dir.mkdir(parents=True, exist_ok=True)
    images = []
    for index, beat in enumerate(beats):
        target = sample_dir / f"beat-{index:02d}.jpg"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss",
            f"{(beat.start + beat.end) / 2:.3f}", "-i", str(video), "-frames:v", "1",
            "-vf", "scale=96:170", str(target),
        ], check=False, timeout=40)
        if target.is_file():
            images.append(Image.open(target).convert("RGB"))
    differences = []
    for left, right in zip(images, images[1:]):
        differences.append(sum(ImageStat.Stat(ImageChops.difference(left, right)).mean) / 3)
    if differences and sum(value > 7.0 for value in differences) < max(2, len(differences) // 2):
        problems.append("sampled scenes do not change enough")
    return {"passed": not problems, "problems": problems, "samples": len(images),
            "mean_scene_change": round(sum(differences) / len(differences), 2) if differences else 0}


def improve_beats(beats: list) -> list:
    """Diversify a failed board before the single automatic retry."""
    types = ["kinetic_type", "concept", "comparison", "media_collage", "ui_showcase", "stat", "chat", "before_after"]
    motions = ["slam", "assemble", "wipe", "collage", "orbit", "count_up", "type_on", "reveal"]
    used: set[str] = set()
    for index, beat in enumerate(beats):
        beat.visual_type = types[index % len(types)]
        beat.motion_style = motions[index % len(motions)]
        beat.layout = "full_frame" if index % 3 == 0 else "top_panel"
        refs = recommend(beat.visual_type, beat.title, limit=3, exclude=used)
        beat.registry_refs = [item["name"] for item in refs]
        if beat.registry_refs:
            used.add(beat.registry_refs[0])
    return beats
