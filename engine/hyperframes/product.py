"""Build source-less product motion reels with the audited visual adapters."""
from __future__ import annotations

import subprocess
from pathlib import Path

from engine.hyperframes.builder import build_project
from engine.hyperframes.schema import VisualBeat
from engine.motion_recipes import BY_ID, select_recipe


def visual_beats(board: dict) -> tuple[list[VisualBeat], float]:
    cursor = 0.0
    beats: list[VisualBeat] = []
    used: dict[str, int] = {}
    accents = ("teal", "ink", "amber", "blue", "coral")
    for index, scene in enumerate(board.get("scenes") or []):
        duration = max(2.2, min(5.0, float(scene.get("duration") or 3.5)))
        requested = BY_ID.get(str(scene.get("recipe") or ""))
        recipe = requested or select_recipe(
            role=str(scene.get("role") or "evidence"), title=str(scene.get("title") or "Product"),
            items=list(scene.get("items") or []), used=used,
        )
        used[recipe.id] = used.get(recipe.id, 0) + 1
        scene.update(recipe=recipe.id, renderer=recipe.renderer, motion=recipe.motion)
        beats.append(VisualBeat(
            id=f"product-{index + 1}", start=round(cursor, 3), end=round(cursor + duration, 3),
            anchor_word=str(scene.get("title") or "").split()[0], visual_type=recipe.renderer,
            title=str(scene.get("title") or "Product")[:80],
            items=[str(value)[:35] for value in scene.get("items") or []][:4],
            layout="full_frame", accent=accents[index % len(accents)],
            registry_refs=[], narrative_role=str(scene.get("role") or "evidence"),
            motion_style=recipe.motion, recipe_id=recipe.id, why=str(scene.get("why") or recipe.best_for),
        ))
        cursor += duration
    return beats, round(cursor, 3)


def create_background(path: Path, duration: float, music: Path | None = None) -> Path:
    """Create a deterministic portrait base so the normal renderer owns A/V sync."""
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=#0b1010:s=1080x1920:r=30",
    ]
    if music and music.is_file():
        command += ["-stream_loop", "-1", "-i", str(music), "-map", "0:v:0", "-map", "1:a:0",
                    "-af", f"atrim=0:{duration:.3f},afade=t=in:st=0:d=1,afade=t=out:st={max(0, duration-2):.3f}:d=2,volume=0.22"]
    command += ["-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if music and music.is_file():
        command += ["-c:a", "aac", "-b:a", "192k"]
    else:
        command += ["-an"]
    command.append(str(path))
    subprocess.run(command, check=True, timeout=max(120, int(duration * 5)))
    return path


def build_product_project(project_dir: Path, board: dict, *, music: Path | None = None) -> tuple[Path, list[VisualBeat], float]:
    beats, duration = visual_beats(board)
    if not beats:
        raise ValueError("storyboard has no scenes")
    background = create_background(project_dir.parent / "product_base.mp4", duration, music)
    entry = build_project(project_dir, background, beats, duration=duration, enable_registry=False)
    return entry, beats, duration
