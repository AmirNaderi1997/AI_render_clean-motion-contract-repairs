"""Owned data only: no generated JavaScript, arbitrary URLs or shell commands.

The first browser adapter reuses the fixed ProductReel composition. Native
FFmpeg/MLT/HyperFrames projects deliberately remain server-only until their
effects have a verified browser equivalent.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def bundle(job) -> tuple[dict, dict[str, Path]]:
    config = copy.deepcopy((job.plan_data or {}).get("generation_meta", {}).get("remotion"))
    if not isinstance(config, dict):
        raise ValueError("This project uses a server-only renderer; browser rendering is not available yet.")
    scenes = config.get("scenes", [])
    if not 1 <= len(scenes) <= 30:
        raise ValueError("Invalid scene count")
    frames = [scene.get("frames") for scene in scenes]
    if any(type(n) is not int or not 1 <= n <= 900 for n in frames) or sum(frames) > 2700:
        raise ValueError("Browser render is limited to 90 seconds")
    root = job.dir.resolve()
    files: dict[str, Path] = {}

    def asset(value, *, library=False, font=False):
        if not value:
            return None
        path = Path(value)
        path = (path if path.is_absolute() else root / path).resolve()
        allowed = [root]
        if library:
            allowed.append((ROOT / "assets/music").resolve())
        if font:
            allowed.append((ROOT / "presets/fonts").resolve())
        if not any(path.is_relative_to(base) for base in allowed) or not path.is_file():
            raise ValueError("Render asset is missing or outside this project")
        if path.stat().st_size > 256 * 1024**2:
            raise ValueError("Asset is too large for browser rendering")
        key = hashlib.sha256(str(path).encode()).hexdigest()[:24]
        files[key] = path
        return key

    for scene in scenes:
        if Path(str(scene.get("asset", ""))).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("This browser composition currently requires still-image scenes")
        scene["asset"] = asset(scene["asset"])
        scene["narration"] = asset(scene.get("narration"))
        scene["supporting_assets"] = [asset(item) for item in scene.get("supporting_assets", [])[:3]]
    config["music"] = asset(config.get("music"), library=True)
    config["font"] = asset(str(ROOT / "presets/fonts/RAY-EXTRABLACK.TTF"), font=True)
    if sum(path.stat().st_size for path in files.values()) > 384 * 1024**2:
        raise ValueError("Project assets exceed the browser memory safety limit; use server rendering")
    revision = hashlib.sha256(json.dumps(config, sort_keys=True).encode() +
                              repr([(key, p.stat().st_size, p.stat().st_mtime_ns) for key, p in files.items()]).encode()).hexdigest()
    return {"renderer": "remotion-product-v1", "revision": revision, "width": 1080,
            "height": 1920, "fps": 30, "durationInFrames": sum(frames), "props": config,
            "assets": [{"id": key, "bytes": path.stat().st_size} for key, path in files.items()]}, files
