"""Talking-head reels for a job: transcribe, let the LLM edit, render (see ``engine.talking_reel``).

State lives in ``<job dir>/talking_reel.json``; renders go to the job's
``exports/talking_reel_v<N>.mp4``. Work runs in a background thread and
clients poll the state. User edits (hook, highlighted words, name, title,
music) are kept across renders; "regenerate" asks the LLM again.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MUSIC = "assets/music/motivational_piano_beat.mp3"
DEFAULTS = {
    "status": "idle", "stage": "", "message": "", "progress": 0,
    "hook": "", "hook_highlight": [], "name": "Reza Rafiei", "title": "Founder Of Rafiei Group",
    "music": DEFAULT_MUSIC, "cta": "", "style": "talking_1", "output": None, "decisions": None,
}
EDITABLE = {"hook", "hook2", "hook_highlight", "name", "title", "music", "cta", "style"}
_lock = threading.Lock()
_running: set[str] = set()


def _path(job_dir: Path) -> Path:
    return job_dir / "talking_reel.json"


def load(job_dir: Path) -> dict:
    path = _path(job_dir)
    state = dict(DEFAULTS)
    if path.is_file():
        state.update(json.loads(path.read_text()))
    return state


def save(job_dir: Path, state: dict) -> dict:
    state["updated_at"] = time.time()
    tmp = _path(job_dir).with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    tmp.replace(_path(job_dir))
    return state


def public(state: dict) -> dict:
    return {k: v for k, v in state.items() if not k.startswith("decisions")}


def update(job_dir: Path, changes: dict) -> dict:
    with _lock:
        if str(job_dir) in _running:
            raise ValueError("talking reel is busy")
        state = load(job_dir)
        for key in EDITABLE & set(changes):
            value = changes[key]
            if key == "hook_highlight":
                value = [str(v).strip() for v in (value or []) if str(v).strip()]
            elif key == "style":
                from engine.talking_reel import STYLES
                if value not in STYLES:
                    raise ValueError(f"unknown style {value!r}")
            elif key == "music":
                value = value or None
                if value and resolve_music(value) is None:
                    raise ValueError("music file not found in the library")
            else:
                value = str(value or "").strip()
            state[key] = value
        return save(job_dir, state)


def resolve_music(music: Optional[str]) -> Optional[Path]:
    if not music:
        return None
    path = (PROJECT_ROOT / music).resolve()
    if not path.is_relative_to((PROJECT_ROOT / "assets").resolve()) or not path.is_file():
        return None
    return path


def start(job_dir: Path, raw_video: Path, *, regenerate: bool = False) -> dict:
    key = str(job_dir)
    with _lock:
        if key in _running:
            raise ValueError("talking reel is busy")
        state = load(job_dir)
        state.update(status="running", stage="queued", message="", progress=0)
        save(job_dir, state)
        _running.add(key)

    def run() -> None:
        try:
            _run(job_dir, raw_video, regenerate=regenerate)
        except Exception as exc:
            log.exception("talking reel failed for %s", job_dir.name)
            current = load(job_dir)
            current.update(status="error", stage="", message=str(exc)[:500])
            save(job_dir, current)
        finally:
            with _lock:
                _running.discard(key)

    threading.Thread(target=run, daemon=True).start()
    return state


def _stage(job_dir: Path, stage: str, **extra) -> None:
    state = load(job_dir)
    state.update(stage=stage, **extra)
    save(job_dir, state)


def transcript_for(job_dir: Path, video: Path) -> dict:
    """ElevenLabs Scribe transcript with real word timings (cached per file).

    Estimated timings or a garbled fallback transcript make wrong cuts and
    wrong captions, so a failure stops here with a clear message.
    """
    from brain.transcribe_elevenlabs import transcribe_elevenlabs

    digest = hashlib.sha256(video.read_bytes()).hexdigest()[:16]
    try:
        transcript, _ = transcribe_elevenlabs(video, job_dir, language="fa", file_digest=digest)
    except Exception as exc:
        raise RuntimeError(f"Speech-to-text failed ({str(exc)[:200]}). ElevenLabs answers 403 when "
                           "the VPN is off; turn it on and run again.") from exc
    if not transcript.get("words"):
        raise RuntimeError("no speech found in the video")
    return transcript


def _run(job_dir: Path, video: Path, *, regenerate: bool) -> None:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    style = load(job_dir).get("style") or "talking_1"
    if style in ("talking_2", "talking_3"):
        _run_split(job_dir, video, style, regenerate=regenerate)
    else:
        _run_talking_1(job_dir, video, regenerate=regenerate)


def _faces(job_dir: Path, video: Path, media) -> list:
    faces_path = job_dir / "talking_reel_faces.json"
    if faces_path.is_file():
        return [tuple(f) for f in json.loads(faces_path.read_text())]
    faces = media.track_faces(video)
    faces_path.write_text(json.dumps(faces))
    return faces


def _next_output(job_dir: Path) -> Path:
    exports = job_dir / "exports"
    exports.mkdir(exist_ok=True)
    version = len(list(exports.glob("talking_reel_v*.mp4"))) + 1
    return exports / f"talking_reel_v{version}.mp4"


def _run_talking_1(job_dir: Path, video: Path, *, regenerate: bool) -> None:
    from brain import talking_reel as brain
    from engine.talking_reel import get_style

    media = get_style("talking_1")
    _stage(job_dir, "transcribing", progress=5)
    transcript = transcript_for(job_dir, video)

    state = load(job_dir)
    decisions = state.get("decisions")
    if regenerate or not decisions:
        _stage(job_dir, "editing text", progress=20)
        decisions = brain.decide(transcript["sentences"])
        state = load(job_dir)
        state["decisions"] = decisions
        if regenerate or not state.get("hook"):
            state["hook"] = decisions["hook"]
            state["hook_highlight"] = decisions["hook_highlight"]
        save(job_dir, state)
    decisions = {**decisions, "captions": {int(k): v for k, v in decisions["captions"].items()}}

    _stage(job_dir, "tracking the face", progress=35)
    faces_path = job_dir / "talking_reel_faces.json"
    if faces_path.is_file():
        faces = [tuple(f) for f in json.loads(faces_path.read_text())]
    else:
        faces = media.track_faces(video)
        faces_path.write_text(json.dumps(faces))

    plan = media.plan_reel(transcript, decisions, faces, float(transcript.get("duration") or 0)
                           or media.probe_video(video)[2])
    _stage(job_dir, "rendering", progress=45)
    exports = job_dir / "exports"
    exports.mkdir(exist_ok=True)
    version = len(list(exports.glob("talking_reel_v*.mp4"))) + 1
    out = exports / f"talking_reel_v{version}.mp4"
    state = load(job_dir)

    def progress(pct: int) -> None:
        _stage(job_dir, "rendering", progress=45 + int(pct * 0.55))

    media.render(video, plan, out, hook=state["hook"], highlight=state.get("hook_highlight") or [],
                 name=state.get("name") or "", title=state.get("title") or "",
                 work_dir=job_dir / "talking_reel_work", music=resolve_music(state.get("music")),
                 cta=state.get("cta") or "",
                 on_progress=progress)
    state = load(job_dir)
    state.update(status="done", stage="", message="", progress=100, output=f"exports/{out.name}",
                 duration=round(plan.duration, 2), shots=len(plan.shots))
    save(job_dir, state)


MEDIA_DIR = "talking_media"            # the creator's own pictures for "صحبتی ۲"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def user_media(job_dir: Path) -> list[Path]:
    folder = job_dir / MEDIA_DIR
    return sorted(p for p in folder.glob("*") if p.suffix.lower() in IMAGE_EXTENSIONS) if folder.is_dir() else []


def _library_pictures() -> list[dict]:
    index = PROJECT_ROOT / "assets" / "library_index.json"
    try:
        assets = json.loads(index.read_text()).get("assets") or []
    except (OSError, ValueError):
        return []
    return [a for a in assets if Path(str(a.get("path") or "")).suffix.lower() in IMAGE_EXTENSIONS
            and (PROJECT_ROOT / a["path"]).is_file()]


def resolve_pictures(job_dir: Path, decisions: dict) -> tuple[dict[int, str], list[dict]]:
    """Picture per B-roll slot: the creator's upload, then a library image, then an AI image.

    Returns ({sentence index: path}, slots for the settings card). Slots
    with no picture are drawn as text cards. AI images are cached by prompt.
    """
    import hashlib
    from concurrent.futures import ThreadPoolExecutor

    chip_slots = {c["i"] for c in decisions.get("chips", [])}
    uploads = {p.name: p for p in user_media(job_dir)}
    library = _library_pictures()
    pictures: dict[int, str] = {}
    slots: list[dict] = []
    wanted_ai = []
    for slot in decisions.get("broll", []):
        if slot["i"] in chip_slots:
            continue
        entry = {"i": slot["i"], "label": slot.get("label") or "", "source": "card", "file": None}
        if slot.get("media") in uploads:
            entry.update(source="upload", file=str(uploads[slot["media"]]))
        else:
            words = set((slot.get("label") or "").split()) | set(slot.get("visual", "").lower().split())
            match = next((a for a in library if words & {str(t).lower() for t in a.get("tags") or []}), None)
            if match:
                entry.update(source="library", file=str(PROJECT_ROOT / match["path"]))
            elif slot.get("visual"):
                key = hashlib.sha256(slot["visual"].encode()).hexdigest()[:16]
                entry.update(source="ai", file=str(job_dir / "talking2_broll" / f"ai_{key}.png"))
                wanted_ai.append((slot["visual"], Path(entry["file"])))
        slots.append(entry)

    def generate(item: tuple[str, Path]) -> None:
        prompt, dst = item
        if dst.is_file():
            return
        from brain.media_provider import get_provider

        dst.parent.mkdir(parents=True, exist_ok=True)
        result = get_provider("sarovi_nano_banana").generate_image(prompt, "1:1", dst.parent)
        Path(result.file_path).replace(dst)

    with ThreadPoolExecutor(max_workers=4) as pool:
        for item, outcome in zip(wanted_ai, pool.map(lambda i: _try(generate, i), wanted_ai)):
            if outcome:
                log.warning("AI picture failed for %s: %s", item[1].name, outcome)
    for entry in slots:
        if entry["file"] and Path(entry["file"]).is_file():
            pictures[entry["i"]] = entry["file"]
        else:
            entry.update(source="card", file=None)
    return pictures, slots


def _try(fn, item) -> Optional[str]:
    try:
        fn(item)
        return None
    except Exception as exc:  # one failed picture becomes a text card, not a failed render
        return str(exc)[:200]


SPLIT_STYLES = {   # style -> (brain module, decisions key, default music)
    "talking_2": ("brain.talking_reel_2", "decisions_2", "assets/music/motivational_piano_beat.mp3"),
    "talking_3": ("brain.talking_reel_3", "decisions_3", "assets/music/cinematic_pulse.mp3"),
}


def _run_split(job_dir: Path, video: Path, style: str, *, regenerate: bool) -> None:
    """The split-screen styles ("صحبتی ۲", "صحبتی ۳"): pictures on top, the speaker below."""
    from importlib import import_module

    from engine.talking_reel import get_style

    brain_name, decisions_key, default_music = SPLIT_STYLES[style]
    brain = import_module(brain_name)
    media = get_style(style)
    _stage(job_dir, "transcribing", progress=5)
    transcript = transcript_for(job_dir, video)
    state = load(job_dir)
    decisions = state.get(decisions_key)
    if regenerate or not decisions:
        _stage(job_dir, "editing text", progress=15)
        decisions = brain.decide(transcript["sentences"], [p.name for p in user_media(job_dir)])
        state = load(job_dir)
        state[decisions_key] = decisions
        if regenerate or not state.get("hook2"):
            state["hook2"] = decisions["hook"]
        save(job_dir, state)
    decisions = {**decisions, "captions": {int(k): v for k, v in decisions["captions"].items()},
                 "hook": load(job_dir).get("hook2") or decisions["hook"]}
    _stage(job_dir, "finding pictures", progress=25)
    pictures, slots = resolve_pictures(job_dir, decisions)
    _stage(job_dir, "tracking the face", progress=35, slots=slots)
    faces = _faces(job_dir, video, media)
    plan = media.plan_reel(transcript, decisions, faces, float(transcript.get("duration") or 0)
                           or media.probe_video(video)[2], pictures)
    _stage(job_dir, "rendering", progress=45)
    out = _next_output(job_dir)
    state = load(job_dir)

    def progress(pct: int) -> None:
        _stage(job_dir, "rendering", progress=45 + int(pct * 0.55))

    # The talking_1 default bed does not suit every style; an explicit choice wins.
    music = state.get("music")
    if music in (None, DEFAULT_MUSIC) and state.get("music") is not None:
        music = default_music
    media.render(video, plan, out, work_dir=job_dir / "talking_reel_work",
                 music=resolve_music(music), cta=state.get("cta") or "", on_progress=progress)
    state = load(job_dir)
    state.update(status="done", stage="", message="", progress=100, output=f"exports/{out.name}",
                 duration=round(plan.duration, 2), shots=len(plan.shots))
    save(job_dir, state)
