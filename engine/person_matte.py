"""A matte video of the person in a crop of the source: what lets the speaker's head rise out of the card over the panel.

Segmentation is the same MediaPipe selfie segmenter + guided filter + temporal smoothing the face-effects engine uses (engine/face_effects/_fx.py
Tracker). It runs in a subprocess with the engine's environment (bundled libs, matplotlib/sounddevice stubs). One gray mp4 per request.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def available() -> bool:
    from engine import face_effects
    return face_effects.available()


def matte(jobs: list[dict], *, timeout: float = 1800) -> list[Path]:
    """jobs: [{src, start, end, crop:[x,y,w,h], size:[mw,mh], fps, out}] -> the gray matte videos (size mw x mh), in order."""
    from engine.face_effects import _env
    spec = ROOT / ".matte_spec.json"
    work = Path(jobs[0]["out"]).parent
    work.mkdir(parents=True, exist_ok=True)
    spec = work / "matte_spec.json"
    spec.write_text(json.dumps(jobs))
    proc = subprocess.run([sys.executable, "-m", "engine.person_matte", str(spec)], cwd=str(ROOT), env=_env(), capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError("person matte failed: " + (proc.stderr or proc.stdout)[-800:])
    return [Path(j["out"]) for j in jobs]


def _main(spec_path: str) -> int:
    import numpy as np
    from engine.face_effects._fx import Tracker
    jobs = json.loads(Path(spec_path).read_text())
    mw0, mh0 = jobs[0]["size"]
    tracker = Tracker(mw0, mh0)
    clock = 0.0                      # MediaPipe's video mode wants timestamps that only ever grow, across shots too
    for job in jobs:
        mw, mh = job["size"]
        x, y, w, h = job["crop"]
        fps = float(job.get("fps") or 30)
        frames = int(round((job["end"] - job["start"]) * fps))
        reader = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-ss", f"{job['start']:.3f}", "-t", f"{job['end'] - job['start']:.3f}", "-i", job["src"],
             "-vf", f"crop={w}:{h}:{x}:{y},scale={mw}:{mh}:flags=bilinear,fps={fps}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE)
        writer = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{mw}x{mh}", "-r", f"{fps}", "-i", "-",
             "-c:v", "libx264", "-crf", "10", "-preset", "ultrafast", "-pix_fmt", "yuv420p", job["out"]], stdin=subprocess.PIPE)
        size = mw * mh * 3
        index = 0
        tracker.prev = None
        while True:
            raw = reader.stdout.read(size)
            if len(raw) < size:
                break
            rgb = np.frombuffer(raw, np.uint8).reshape(mh, mw, 3)
            mask, _face = tracker(rgb, int(clock + index * 1000 / fps))
            writer.stdin.write(mask.tobytes())
            index += 1
        writer.stdin.close()
        writer.wait()
        reader.wait()
        clock += (index + 2) * 1000 / fps
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1]))
