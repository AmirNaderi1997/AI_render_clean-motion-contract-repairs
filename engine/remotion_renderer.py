"""Render owned, typed scene data with the repository's fixed React composition.

No code from a model or remote page is executed by this adapter.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def render(config: dict, output: Path, *, job_dir: Path, on_progress=None) -> None:
    root = job_dir.resolve()
    config = json.loads(json.dumps(config))
    if not 1 <= len(config.get("scenes", [])) <= 30:
        raise ValueError("Motion scene count is outside render limits")
    if sum(scene.get("frames", 0) for scene in config["scenes"]) > 2700:
        raise ValueError("Motion duration exceeds 90 seconds")
    for scene in config["scenes"]:
        for field in ("asset", "narration"):
            if not scene.get(field):
                continue
            path = (root / scene[field]).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError(f"Invalid owned scene {field}")
            scene[field] = str(path)
        if not 1 <= scene["frames"] <= 900:
            raise ValueError("Scene duration is outside render limits")
        supporting = []
        for item in scene.get("supporting_assets", [])[:3]:
            path = (root / item).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError("Invalid owned supporting asset")
            supporting.append(str(path))
        scene["supporting_assets"] = supporting
    if config.get("music"):
        music = Path(config["music"])
        if not music.is_absolute():
            music = root / music
        # Music is selected by the server from its approved library.
        music = music.resolve()
        if not (music.is_relative_to(root) or music.is_relative_to((ROOT / "assets/music").resolve())):
            raise ValueError("Music must belong to the job or approved library")
        if not music.is_file():
            raise ValueError("Music asset is missing")
        config["music"] = str(music.resolve())
    config["font"] = str(ROOT / "presets/fonts/RAY-EXTRABLACK.TTF")
    config_path = output.with_suffix(".remotion.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False))
    command = ["node", "render.mjs", str(config_path), str(output.resolve())]
    process = subprocess.Popen(command, cwd=ROOT / "remotion", stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, start_new_session=True)
    def stop():
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    timer = threading.Timer(1800, stop)
    timer.daemon = True
    timer.start()
    tail = deque(maxlen=30)
    last_progress = -1
    try:
        for line in process.stdout:
            tail.append(line)
            if line.startswith("REMOTION_PROGRESS ") and on_progress:
                progress = min(95, int(line.split()[-1]))
                if progress != last_progress:
                    on_progress(progress)
                    last_progress = progress
        if process.wait() != 0:
            raise RuntimeError("Remotion render failed: " + "".join(tail)[-1800:])
    finally:
        timer.cancel()
        stop()
        process.stdout.close()


def scene_config(storyboard, media: list[dict], narration: list[dict], job_dir: Path, music: str | None) -> dict:
    voices = {item["scene_index"]: item for item in narration}
    sources = {item["scene_index"]: item for item in media}
    scenes = []
    assets = list(dict.fromkeys(scene.source_asset for scene in storyboard.scenes))
    for scene in storyboard.scenes:
        source = sources[scene.index]
        voice = voices.get(scene.index)
        scenes.append({"asset": scene.source_asset,
                       "title": scene.text_overlay,
                       "role":scene.narrative_role,"visual_type":scene.visual_type,"motion_style":scene.motion_style,
                       "frames": max(1, round(source["duration_s"] * 30)),
                       "narration": str(Path(voice["file_path"]).relative_to(job_dir)) if voice else None})
        # Only use relevant assets explicitly selected by the storyboard.
        # No automatic gallery of unrelated product photos every third scene.
        scenes[-1]["supporting_assets"] = [scene.source_asset]
    directed=any(scene.narrative_role for scene in storyboard.scenes)
    return {"scenes": scenes, "music": music,"version":2 if directed else 1}
