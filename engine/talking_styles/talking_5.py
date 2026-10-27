"""Talking-head style 5: a style-pack reel.

Planning is the proven talking_2 cut (speech ranges, pieces of 1.6-3 s, face per shot). What is different is who draws:
the speaker is cropped, punched-in and graded by ffmpeg, every graphic (panels, captions, the hook, key-moment slams) is ONE
transparent HyperFrames page (engine/hyperframes/overlay_reel.py) laid over it, so a new look is a new StylePack
(creative/style_packs.py), never a new renderer.

Hard cuts only (the reference style): the speaker is either full-frame or a rounded card under the panel, and the page knows
which, shot by shot.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from creative.style_packs import REFERENCE_AI_NEWS, StylePack

from . import talking_2 as base
from .talking_1 import H, W, music_bed

log = logging.getLogger(__name__)

CARD_Y = 888                          # the speaker card starts here (matches overlay_reel.SPLIT_Y)
CARD_H = H - CARD_Y
CARD_RADIUS = 58
LOUDNESS = -14.0
MUSIC_DB = -17.0
GRADES = {
    "warm": "eq=contrast=1.06:saturation=1.10:gamma=0.98,colorbalance=rs=.03:gs=0:bs=-.04:rm=.02:bm=-.02",
    "cool": "eq=contrast=1.06:saturation=1.05,colorbalance=rs=-.03:bs=.04",
    "neutral": "eq=contrast=1.03:saturation=1.0",
}

track_faces = base.track_faces
probe_video = base.probe_video
Shot = base.Shot
ReelPlan = base.ReelPlan


# ── planning ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def plan_reel(transcript: dict, decisions: dict, faces: list, duration: float, pack: StylePack | None = None,
              beats: list[dict] | None = None, key_moments: list[dict] | None = None, creative_plan: dict | None = None) -> ReelPlan:
    """The talking_2 cut with a layout per shot (full / split) and the script the overlay page needs on plan.script."""
    pack = pack or REFERENCE_AI_NEWS
    plan = base.plan_reel(transcript, {**decisions, "broll": [], "chips": []}, faces, duration, pictures={}, continuous_split=False)
    sentences = transcript["sentences"]
    by_sentence = {int(b["sentence"]): b for b in (beats or []) if b.get("sentence") is not None}
    ratio = pack.rhythm.split_ratio
    # Which shots get a panel: the shots that sit inside a beat's sentence, spread so about `ratio` of the reel is split.
    candidates = []
    for shot in plan.shots:
        k = base._sentence_at(sentences, (shot.src_in + shot.src_out) / 2)
        shot.slot = k
        if ratio > 0 and k in by_sentence and shot.out_start >= plan.cold_open + 0.01:
            candidates.append(shot)
    chosen = candidates
    if candidates and ratio < 1:
        limit = max(1, round(ratio * len(plan.shots)))
        chosen = candidates[:limit] if len(candidates) > limit else candidates
    split_ids = {id(s) for s in chosen}
    # a key-moment slam owns the whole frame: no panel under it
    windows = []
    for m in key_moments or []:
        if m.get("i") is not None and 0 <= int(m["i"]) < len(sentences):
            windows.append((float(sentences[int(m["i"])]["start"]) - 0.1, float(sentences[int(m["i"])]["start"]) + 2.2))
    for shot in plan.shots:
        shot.split = id(shot) in split_ids and not any(shot.src_in < b and shot.src_out > a for a, b in windows)
        shot.close = (not shot.split) and (shot.out_start // 1 % 2 == 1)

    plan.script = _script(plan, transcript, decisions, by_sentence, key_moments or [], pack)
    plan.pack = pack
    plan.sentences = sentences
    plan.creative_plan = creative_plan
    return plan


def _word_times(plan: ReelPlan, words: list[dict]) -> list[dict]:
    """Transcript words on the output timeline. The cold-open line is spoken twice in the output (teaser, then in place):
    its words are timed once per occurrence, each against its own shot."""
    from brain.talking_reel import is_filler
    cold = plan.shots[0] if plan.cold_open > 0 else None
    main = plan.shots[1:] if cold else plan.shots
    out = []

    def place(shot: Shot, w: dict) -> None:
        a = shot.out_start + float(w["start"]) - shot.src_in
        b = shot.out_start + float(w["end"]) - shot.src_in
        end = shot.out_start + shot.length
        b = min(max(b, a + 0.12), end)
        if a < end:
            out.append({"w": base.persian_digits(str(w["w"])), "start": round(a, 3), "end": round(b, 3)})

    for w in words:
        if is_filler(w.get("w", "")):
            continue
        t0, t1 = float(w["start"]), float(w["end"])
        if cold and cold.src_in - 1e-3 <= t0 and t1 <= cold.src_out + 1e-3:
            place(cold, w)
        for shot in main:
            if shot.src_in - 1e-3 <= t0 and t1 <= shot.src_out + 1e-3:
                place(shot, w)
                break
    out.sort(key=lambda x: x["start"])
    return out


def _out_map(plan: ReelPlan):
    main = plan.shots[1:] if plan.cold_open > 0 else plan.shots

    def out_time(src: float) -> float | None:
        for s in main:
            if s.src_in - 1e-3 <= src <= s.src_out + 1e-3:
                return s.out_start + max(0.0, src - s.src_in)
        return None
    return out_time


def _script(plan: ReelPlan, transcript: dict, decisions: dict, by_sentence: dict, moments: list[dict], pack: StylePack) -> dict:
    out_time = _out_map(plan)
    words = _word_times(plan, transcript["words"])
    segments, cur = [], None
    for shot in plan.shots:
        layout = "split" if shot.split else "full"
        beat = by_sentence.get(shot.slot) if shot.split else None
        key = (layout, shot.slot if shot.split else None)
        end = shot.out_start + shot.length
        if cur and cur["key"] == key and abs(cur["end"] - shot.out_start) < 0.02:
            cur["end"] = end
        else:
            cur = {"key": key, "start": shot.out_start, "end": end, "layout": layout, "beat": beat}
            segments.append(cur)
    for s in segments:
        s.pop("key", None)
    sentences = transcript["sentences"]
    slams = []
    for m in moments:
        i = m.get("i")
        if i is None or not (0 <= int(i) < len(sentences)):
            continue
        a = out_time(float(sentences[int(i)]["start"]))
        if a is None:
            continue
        slams.append({"text": base.persian_digits(str(m.get("text") or "")), "start": round(a, 3), "end": round(a + 2.0, 3)})
    hook = None
    if decisions.get("hook") and pack.hook.mode != "none":
        hook = {"text": base.persian_digits(str(decisions["hook"])), "highlight": " ".join(decisions.get("hook_highlight") or []),
                "start": 0.0, "end": min(pack.hook.seconds, plan.duration)}
    return {"duration": round(plan.duration, 3), "segments": segments, "words": words, "hook": hook, "moments": slams}


# ── rendering ────────────────────────────────────────────────────────────────────────────────────────────────────────

EXTRA = 300                           # how far above the card the speaker's head may rise (px)
TALL_H = CARD_H + EXTRA
FACE_FRAC = (EXTRA + 70) / TALL_H     # where the face centre sits in the tall window: just under the card's top edge


def _crop(shot: Shot, src_w: int, src_h: int, pack: StylePack, split: bool) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the source window for this shot: the face stays inside, close shots punch in. Split shots use the tall window
    (card + the head room above it) so the head can rise over the panel."""
    zoom = pack.rhythm.close_zoom if shot.close else 1.0
    if split:
        zoom *= 1.12
        h = min(src_h, src_h / zoom)
        w = min(src_w, h * (W / TALL_H))
        h = w * (TALL_H / W)
    else:
        h = src_h / zoom
        w = h * (9 / 16)
    cx, cy = shot.face
    x = min(max(0.0, cx * src_w - w / 2), src_w - w)
    y = min(max(0.0, cy * src_h - h * (FACE_FRAC if split else 0.38)), src_h - h)
    return int(x) // 2 * 2, int(y) // 2 * 2, int(w) // 2 * 2, int(h) // 2 * 2


def _round_mask(path: Path) -> Path:
    import cv2
    import numpy as np
    mask = np.zeros((CARD_H, W), np.uint8)
    cv2.rectangle(mask, (0, CARD_RADIUS), (W, CARD_H), 255, -1)
    cv2.rectangle(mask, (CARD_RADIUS, 0), (W - CARD_RADIUS, CARD_RADIUS), 255, -1)
    cv2.circle(mask, (CARD_RADIUS, CARD_RADIUS), CARD_RADIUS, 255, -1)
    cv2.circle(mask, (W - CARD_RADIUS, CARD_RADIUS), CARD_RADIUS, 255, -1)
    cv2.imwrite(str(path), mask)
    return path


def _hex(color: str) -> str:
    return "0x" + color.lstrip("#")


def _mattes(video: Path, plan: ReelPlan, pack: StylePack, work_dir: Path, src_w: int, src_h: int, fps: int) -> dict[int, Path]:
    """One matte video per split shot (half resolution), or {} when segmentation is unavailable (the head then stays inside the card)."""
    from engine import person_matte
    if not person_matte.available():
        return {}
    jobs, index = [], []
    for i, shot in enumerate(plan.shots):
        if not shot.split:
            continue
        x, y, w, h = _crop(shot, src_w, src_h, pack, True)
        jobs.append({"src": str(video), "start": shot.src_in, "end": shot.src_out, "crop": [x, y, w, h], "size": [W // 2, TALL_H // 2],
                     "fps": fps, "out": str(work_dir / "mattes" / f"m{i}.mp4")})
        index.append(i)
    if not jobs:
        return {}
    try:
        outs = person_matte.matte(jobs)
    except Exception as exc:                                   # the reel is still good without the pop-out
        log.warning("person matte unavailable: %s", str(exc)[:200])
        return {}
    return dict(zip(index, outs))


def _graph(plan: ReelPlan, pack: StylePack, src_w: int, src_h: int, fps: int, mattes: dict[int, Path], first_matte_input: int) -> tuple[list[str], list[str]]:
    """(filter parts, extra -i arguments) for: bg + panel + speaker layer + head layer + text. Inputs 0 = video, 1 = card mask, then mattes."""
    grade = GRADES.get(pack.grade, GRADES["neutral"])
    parts, slayer, player, alabels = [], [], [], []
    matte_args: list[str] = []
    matte_input = {}
    for k, i in enumerate(sorted(mattes)):
        matte_input[i] = first_matte_input + k
        matte_args += ["-i", str(mattes[i])]
    for i, shot in enumerate(plan.shots):
        a, b = shot.src_in, shot.src_out
        d = b - a
        x, y, w, h = _crop(shot, src_w, src_h, pack, shot.split)
        if shot.split:
            parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS,crop={w}:{h}:{x}:{y},scale={W}:{TALL_H}:flags=lanczos,{grade},format=yuva420p,split[ta{i}][tb{i}]")
            parts.append(f"[ta{i}]crop={W}:{CARD_H}:0:{EXTRA}[cc{i}]")
            parts.append(f"[1:v]trim=duration={d:.3f},setpts=PTS-STARTPTS,format=gray[mk{i}]")
            parts.append(f"[cc{i}][mk{i}]alphamerge[card{i}]")
            parts.append(f"color=c=black@0.0:s={W}x{H}:r={fps}:d={d:.3f},format=yuva420p[e{i}]")
            parts.append(f"[e{i}][card{i}]overlay=0:{CARD_Y}:format=auto,format=yuva420p[s{i}]")
            if i in matte_input:
                parts.append(f"[{matte_input[i]}:v]format=gray,scale={W}:{TALL_H}:flags=bilinear,gblur=sigma=1.2,format=gray[mm{i}]")
                parts.append(f"[tb{i}][mm{i}]alphamerge[person{i}]")
                parts.append(f"color=c=black@0.0:s={W}x{H}:r={fps}:d={d:.3f},format=yuva420p[f{i}]")
                parts.append(f"[f{i}][person{i}]overlay=0:{CARD_Y - EXTRA}:format=auto,format=yuva420p[p{i}]")
            else:
                parts.append(f"[tb{i}]nullsink")
                parts.append(f"color=c=black@0.0:s={W}x{H}:r={fps}:d={d:.3f},format=yuva420p[p{i}]")
        else:
            parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS,crop={w}:{h}:{x}:{y},scale={W}:{H}:flags=lanczos,{grade},format=yuva420p[s{i}]")
            parts.append(f"color=c=black@0.0:s={W}x{H}:r={fps}:d={d:.3f},format=yuva420p[p{i}]")
        parts.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[a{i}]")
        slayer.append(f"[s{i}]")
        player.append(f"[p{i}]")
        alabels.append(f"[a{i}]")
    n = len(plan.shots)
    parts.append(f"{''.join(slayer)}concat=n={n}:v=1:a=0[L1]")
    parts.append(f"{''.join(player)}concat=n={n}:v=1:a=0[L2]")
    parts.append(f"{''.join(alabels)}concat=n={n}:v=0:a=1[ca]")
    return parts, matte_args


def render_composite(video: Path, plan: ReelPlan, panel: Optional[Path], text: Optional[Path], out: Path, *, work_dir: Path,
                     music: Optional[Path] = None, pack: StylePack | None = None, on_progress=None) -> Path:
    """One ffmpeg pass: panel colour -> panel layer -> speaker (full frame or card) -> head over the panel -> text; cuts, grade, music, loudness."""
    pack = pack or plan.pack
    work_dir.mkdir(parents=True, exist_ok=True)
    probe = base.probe_video(video)
    src_w, src_h = int(probe[0]), int(probe[1])
    fps = int(round(base.eval_fps(base.probe_fps(video)) or 30))
    mask = _round_mask(work_dir / "card_mask.png")
    mattes = _mattes(video, plan, pack, work_dir, src_w, src_h, fps)
    inputs = ["-i", str(video), "-loop", "1", "-framerate", str(fps), "-i", str(mask)]
    parts, matte_args = _graph(plan, pack, src_w, src_h, fps, mattes, 2)
    inputs += matte_args
    nxt = 2 + len(mattes)
    parts.append(f"color=c={_hex(pack.palette.panel_bg)}:s={W}x{H}:r={fps}:d={plan.duration:.3f}[bg]")
    last = "bg"
    if panel and panel.is_file():
        inputs += ["-c:v", "libvpx-vp9", "-i", str(panel)]
        parts.append(f"[{nxt}:v]format=yuva420p,setpts=PTS-STARTPTS[pn]")
        parts.append(f"[{last}][pn]overlay=0:0:format=auto:eof_action=pass[x1]")
        last, nxt = "x1", nxt + 1
    parts.append(f"[{last}][L1]overlay=0:0:format=auto:shortest=0:eof_action=pass[x2]")
    parts.append("[x2][L2]overlay=0:0:format=auto:eof_action=pass[x3]")
    last = "x3"
    if text and text.is_file():
        inputs += ["-c:v", "libvpx-vp9", "-i", str(text)]
        parts.append(f"[{nxt}:v]format=yuva420p,setpts=PTS-STARTPTS[tx]")
        parts.append(f"[{last}][tx]overlay=0:0:format=auto:eof_action=pass[x4]")
        last, nxt = "x4", nxt + 1
    parts.append(f"[{last}]fps={fps},format=yuv420p[vout]")
    loud = f"loudnorm=I={LOUDNESS}:TP=-1:LRA=8,aresample=48000[aout]"
    if music and music.is_file():
        inputs += ["-i", str(music_bed(music, plan.duration + 1.0, work_dir))]
        parts.append(f"[{nxt}:a]volume={MUSIC_DB}dB,atrim=0:{plan.duration:.3f}[bed]")
        parts.append(f"[ca][bed]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=300[ducked];[ca][ducked]amix=inputs=2:duration=first:normalize=0,{loud}")
    else:
        parts.append(f"[ca]{loud}")
    cmd = ["ffmpeg", "-hide_banner", "-y", *inputs, "-filter_complex", ";".join(parts), "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-t", f"{plan.duration:.3f}", "-movflags", "+faststart", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + proc.stderr[-1600:])
    return out


def render_layer(plan: ReelPlan, out: Path, *, work_dir: Path, part: str, pack: StylePack | None = None,
                 on_progress: Optional[Callable[[int], None]] = None, timeout: int = 5400) -> Optional[Path]:
    """A transparent HyperFrames layer: "panel" (under the speaker) or "text" (over it). None when the layer has nothing in it."""
    from engine.hyperframes import overlay_reel
    from engine.hyperframes.product_reel import _run_cli
    pack = pack or plan.pack
    if part == "panel" and not any(s["layout"] == "split" and s.get("beat") for s in plan.script["segments"]):
        return None
    project = work_dir / f"layer_{part}"
    if project.exists():
        shutil.rmtree(project)
    project.mkdir(parents=True)
    overlay_reel.build_project(project, pack, plan.script, part=part)
    _run_cli(project, out, timeout=timeout, on_progress=on_progress, fmt="webm")
    return out


def author_panels(plan: ReelPlan, work_dir: Path) -> int:
    """The Motion Designer writes one scene per panel (creative/motion.py, cached next to the job). Returns how many were authored."""
    from creative import motion as creative_motion
    from engine.hyperframes.schema import VisualBeat
    if not creative_motion.enabled():
        return 0
    segs = [s for s in plan.script["segments"] if s["layout"] == "split" and s.get("beat")]
    beats = []
    for n, seg in enumerate(segs):
        b = seg["beat"]
        sentence = int(b.get("sentence") if b.get("sentence") is not None else 0)
        bid = f"beat-{sentence}-{n}"
        b["bid"] = bid
        spoken = plan.sentences[sentence]["text"] if 0 <= sentence < len(plan.sentences) else ""
        beats.append(VisualBeat(id=bid, start=float(seg["start"]), end=float(seg["end"]), title=(str(b.get("title") or "") or "…")[:80],
                                items=[str(i)[:35] for i in (b.get("items") or [])][:4], layout="top_panel",
                                narrative_role=str(b.get("role") or "evidence"), why=str(b.get("visual") or ""), spoken=spoken))
    if not beats:
        return 0
    creative_motion.compose(beats, creative_motion.plan_from_public(plan.creative_plan), plan.sentences, cache=work_dir / "authored_scenes.json")
    done = 0
    for seg, beat in zip(segs, beats):
        if beat.custom:
            seg["beat"]["custom"] = beat.custom
            done += 1
    return done


def render(video: Path, plan: ReelPlan, out: Path, *, work_dir: Path, music: Optional[Path] = None,
           on_progress: Optional[Callable[[int], None]] = None, **kwargs) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    pack = kwargs.get("pack") or plan.pack
    report = (lambda lo, hi: (lambda p: on_progress(lo + int(p * (hi - lo) / 100)))) if on_progress else (lambda lo, hi: None)
    if getattr(plan, "creative_plan", None) is not None and author_panels(plan, work_dir):
        bg = next((s["beat"]["custom"].get("bg") for s in plan.script["segments"] if s.get("beat") and s["beat"].get("custom")), None)
        if bg:                                          # the speaker card's rounded corners show this colour: it must be the panel's
            pack = pack.model_copy(update={"palette": pack.palette.model_copy(update={"panel_bg": bg})})
    panel = render_layer(plan, work_dir / "t5_panel.webm", work_dir=work_dir, part="panel", pack=pack, on_progress=report(5, 45))
    text = render_layer(plan, work_dir / "t5_text.webm", work_dir=work_dir, part="text", pack=pack, on_progress=report(45, 75))
    render_composite(video, plan, panel, text, out, work_dir=work_dir, music=music, pack=pack)
    if on_progress:
        on_progress(99)
    return out
