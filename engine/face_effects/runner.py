"""Renders effect windows of a video (runs as its own process: ``python -m engine.face_effects.runner``).

Only the stretches of the video that carry an effect are tracked and composed frame by frame; the rest of the video is never touched by Python.
The composed stretches are laid over the original in ONE ffmpeg pass that also keeps the original audio.

  python -m engine.face_effects.runner --src in.mp4 --dst out.mp4 --plan plan.json --work dir
  python -m engine.face_effects.runner --src in.mp4 --plan plan.json --work dir --still 4.5 --png frame.png
Progress goes to stdout as JSON lines: {"progress": 0.0-1.0, "stage": "..."}.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from . import _fx

TRACK_MARGIN = 0.5      # seconds tracked before and after a window, so the smoothing of the face position has context


def _say(progress: float, stage: str) -> None:
    print(json.dumps({"progress": round(max(0.0, min(1.0, progress)), 3), "stage": stage}), flush=True)


def _groups(fxs: list) -> list[list]:
    """Effects whose windows touch or overlap are rendered together (they stack on the same frames, in listed order)."""
    groups: list[list] = []
    for fx in sorted(fxs, key=lambda item: item.start):
        if groups and fx.start <= max(item.end for item in groups[-1]) + TRACK_MARGIN:
            groups[-1].append(fx)
        else:
            groups.append([fx])
    return groups


def _thumbs(src: str, duration: float, aw: int, ah: int, n: int = 10) -> list[Image.Image]:
    """Evenly spread frames of the whole video: the pictures the 'reel' cards of orbit and noise are made of."""
    out = []
    for j in range(n):
        at = duration * (j + 0.5) / n
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{at:.2f}", "-i", src, "-frames:v", "1", "-vf", f"scale={aw}:{ah}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        if len(raw) == aw * ah * 3:
            out.append(Image.fromarray(np.frombuffer(raw, np.uint8).reshape(ah, aw, 3).copy()))
    return out


def _track(src: str, fr: str, fps: float, aw: int, ah: int, t0: float, t1: float):
    """Person masks and a smoothed face position for every frame of [t0, t1]; index i is the frame at t0 + i/fps."""
    tracker = _fx.Tracker(aw, ah)
    masks, faces = {}, []
    for i, frame in enumerate(_fx.read_frames(src, aw, ah, fr, ss=t0, t=t1 - t0)):
        mask, face = tracker(frame, int((t0 + i / fps) * 1000))
        masks[i] = mask
        faces.append(face)
    smoothed = _fx.smooth(faces, fps)
    if smoothed is None:
        smoothed = np.tile([aw / 2, ah * 0.33, aw * 0.15], (max(1, len(faces)), 1))
    return masks, smoothed


def _compose(frame: np.ndarray, t: float, active: list, masks: dict, smoothed, index: int, W: int, H: int, aw: int, fps: float) -> np.ndarray:
    ctx = _fx.Ctx()
    ctx.W, ctx.H, ctx.t, ctx.fps = W, H, t, fps
    ctx.img = frame.astype(np.float32) / 255.0
    mask = masks.get(index)
    ctx.m = cv2.resize(mask, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255.0 if mask is not None else np.zeros((H, W), np.float32)
    scale = W / aw
    fx_, fy_, fw_ = smoothed[min(index, len(smoothed) - 1)]
    ctx.fx, ctx.fy, ctx.fw = fx_ * scale, fy_ * scale, max(fw_ * scale, W * 0.05)
    for fx in active:
        ctx.lt = t - fx.start
        _fx.EFFECTS[fx.name][0](ctx, fx)
    return (np.clip(ctx.img, 0, 1) * 255 + 0.5).astype(np.uint8)


def _plan(args) -> list[dict]:
    plan = json.loads(Path(args.plan).read_text())
    return plan.get("effects", plan) if isinstance(plan, dict) else plan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--still", type=float)
    ap.add_argument("--png")
    args = ap.parse_args()
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    fr, fps, duration, sw, sh = _fx.probe(args.src)
    if sw <= sh:
        W, H = args.width, int(round(args.width * sh / sw / 2)) * 2
    else:
        H, W = args.width, int(round(args.width * sw / sh / 2)) * 2
    aw = 540 if sw <= sh else int(round(540 * sw / sh / 2)) * 2
    ah = int(round(aw * sh / sw / 2)) * 2
    items = _plan(args)
    for item in items:
        item["end"] = min(float(item["end"]), duration)
    fxs = [_fx.Fx(item, fps) for item in items if float(item["end"]) > float(item["start"])]
    if not fxs:
        print("nothing to do", file=sys.stderr)
        return 2
    thumbs = _thumbs(args.src, duration, aw, ah)
    for fx in fxs:
        if fx.name in _fx.CARD_FX:
            fx.cards = _fx.load_cards(fx.o.get("images"), thumbs)

    if args.still is not None:
        t = max(0.0, min(float(args.still), duration - 1 / fps))
        t0 = max(0.0, t - 0.4)
        masks, smoothed = _track(args.src, fr, fps, aw, ah, t0, min(duration, t + 0.2))
        frames = list(_fx.read_frames(args.src, W, H, fr, ss=t, t=0.2))
        if not frames:
            return 3
        index = int(round((t - t0) * fps))
        active = [fx for fx in fxs if fx.start <= t < fx.end]
        image = _compose(frames[0], t, active, masks, smoothed, index, W, H, aw, fps) if active else frames[0]
        cv2.imwrite(args.png, cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
        _say(1.0, "still")
        return 0

    groups = _groups(fxs)
    total_frames = sum(int((max(f.end for f in g) - min(f.start for f in g)) * fps) + 1 for g in groups) or 1
    done_frames = 0
    clips: list[tuple[Path, float, float]] = []
    for k, group in enumerate(groups):
        g0, g1 = min(f.start for f in group), max(f.end for f in group)
        t0, t1 = max(0.0, g0 - TRACK_MARGIN), min(duration, g1 + TRACK_MARGIN)
        _say(done_frames / total_frames, "tracking")
        masks, smoothed = _track(args.src, fr, fps, aw, ah, t0, t1)
        clip = work / f"fx_{k}.mp4"
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fr), "-i", "-",
                                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "14", "-pix_fmt", "yuv420p", "-an", str(clip)], stdin=subprocess.PIPE)
        count = 0
        for i, frame in enumerate(_fx.read_frames(args.src, W, H, fr, ss=g0, t=g1 - g0)):
            t = g0 + i / fps
            active = [fx for fx in group if fx.start <= t < fx.end]
            index = int(round((t - t0) * fps))
            image = _compose(frame, t, active, masks, smoothed, index, W, H, aw, fps) if active else frame
            enc.stdin.write(image.tobytes())
            count += 1
            done_frames += 1
            if count % 10 == 0:
                _say(done_frames / total_frames * 0.85, "composing")
        enc.stdin.close()
        enc.wait()
        if enc.returncode != 0 or not clip.is_file():
            print("effect clip failed", file=sys.stderr)
            return 4
        clips.append((clip, g0, g0 + count / fps))

    _say(0.88, "encoding")
    cmd = ["ffmpeg", "-v", "error", "-y", "-threads", "2", "-i", args.src]
    for clip, _, _ in clips:
        cmd += ["-i", str(clip)]
    graph = [f"[0:v]scale={W}:{H},setsar=1,format=yuv420p[b0]"]
    for k, (clip, a, b) in enumerate(clips):
        graph.append(f"[{k + 1}:v]setpts=PTS-STARTPTS+{a:.3f}/TB[w{k}]")
        graph.append(f"[b{k}][w{k}]overlay=eof_action=pass:enable='between(t,{a:.3f},{b:.3f})'[b{k + 1}]")
    cmd += ["-filter_complex", ";".join(graph), "-map", f"[b{len(clips)}]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", args.dst]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-800:], file=sys.stderr)
        return 5
    _say(1.0, "done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
