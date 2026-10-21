"""Small deterministic post-render review for talking-head motion graphics."""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

def review_render(video: Path, beats: list, work_dir: Path) -> dict:
    problems: list[str] = []
    continuous = bool(beats) and all(b.layout == 'top_panel' for b in beats)
    if len(beats) < 4 and not continuous:
        problems.append("fewer than four visual worlds")
    if not continuous and any(beat.end - beat.start > 2.5 for beat in beats):
        problems.append("a visual remains on screen too long")
    if any(beat.layout not in {'full_frame', 'top_panel'} for beat in beats):
        problems.append("a visual overlay can cover the speaker's face")
    if not continuous and any(a.visual_type == b.visual_type for a, b in zip(beats, beats[1:])):
        problems.append("consecutive scenes repeat the same visual grammar")
    primaries = [beat.registry_refs[0] for beat in beats if beat.registry_refs]
    if continuous and any(abs(a.end-b.start) > .04 for a,b in zip(beats,beats[1:])):
        problems.append('explanatory motion has uncovered gaps')
    if len(primaries) != len(set(primaries)):
        problems.append("catalog templates repeat")

    sample_dir = work_dir / "visual_qc"
    sample_dir.mkdir(parents=True, exist_ok=True)
    images = []
    for index, beat in enumerate(beats):
        target = sample_dir / f"beat-{index:02d}.jpg"
        if target.exists():
            target.unlink()  # A failed extraction must not reuse a prior render's frame.
        extracted=subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss",
            f"{(beat.start + beat.end) / 2:.3f}", "-i", str(video), "-frames:v", "1",
            "-vf", "crop=iw:888:0:0,scale=96:79" if continuous else "scale=96:170", str(target),
        ], check=False, timeout=40)
        if extracted.returncode==0 and target.is_file():
            with Image.open(target) as source:
                images.append(source.convert("RGB"))
        else:
            problems.append(f"could not inspect actual scene {beat.id}")
    differences = []
    for left, right in zip(images, images[1:]):
        differences.append(sum(ImageStat.Stat(ImageChops.difference(left, right)).mean) / 3)
    if differences and sum(value > 7.0 for value in differences) < min(len(differences), max(2, len(differences) // 2)):
        problems.append("sampled scenes do not change enough")
    return {"passed": not problems, "problems": problems, "samples": len(images),
            "mean_scene_change": round(sum(differences) / len(differences), 2) if differences else 0}


def improve_beats(beats: list) -> list:
    """Diversify a failed board before the single automatic retry."""
    types = ["kinetic_type", "concept", "comparison", "media_collage", "ui_showcase", "stat", "chat", "before_after"]
    motions = ["slam", "assemble", "wipe", "collage", "orbit", "count_up", "type_on", "reveal"]
    for index, beat in enumerate(beats):
        beat.visual_type = types[index % len(types)]
        beat.motion_style = motions[index % len(motions)]
        beat.layout = "full_frame"
        # build_project will install and record only adapters that are truly
        # mounted.  Never advertise a catalog result as used code here.
        beat.registry_refs = []
    return beats
