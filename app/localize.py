"""Localization projects: Persian voice-over + captions for English reels.

A project lives in ``LOCALIZE_ROOT/<id>/`` with ``state.json``, the uploaded
source under ``raw/`` and renders under ``exports/``. Analysis (transcribe,
translate, find caption positions) and rendering run in background threads;
clients poll the state.
"""
from __future__ import annotations

import json
import logging
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from app.config import settings

log = logging.getLogger(__name__)

LOCALIZE_ROOT = (Path(settings.LOCALIZE_DIR).expanduser() if settings.LOCALIZE_DIR
                 else Path(settings.JOBS_DIR).expanduser().parent / "localize_jobs")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Voice and transcription helpers read provider keys from os.environ, which
# pydantic settings do not populate; load .env so a render right after a
# restart (with no analysis in this process) still finds them.
load_dotenv(PROJECT_ROOT / ".env")
_lock = threading.Lock()
_running: set[str] = set()
_cancel_events: dict[str, threading.Event] = {}
_pause_events: dict[str, threading.Event] = {}


class TaskCanceled(Exception):
    pass
DEFAULT_LOCALIZE_MUSIC = "assets/music/motivational_piano_beat.mp3"

EDITABLE_LINE_FIELDS = {"fa", "kind"}


def _dir(project_id: str) -> Path:
    if not project_id.isalnum() or len(project_id) != 12:
        raise KeyError(project_id)
    return LOCALIZE_ROOT / project_id


def load(project_id: str) -> dict:
    path = _dir(project_id) / "state.json"
    if not path.is_file():
        raise KeyError(project_id)
    return json.loads(path.read_text())


def save(state: dict) -> dict:
    state["updated_at"] = time.time()
    path = _dir(state["id"]) / "state.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    tmp.replace(path)
    return state


def public(state: dict) -> dict:
    """State as returned by the API (no internal word timings)."""
    out = {k: v for k, v in state.items() if k not in {"words", "english_regions"}}
    out["lines"] = [{**{k: v for k, v in line.items() if k != "words"},
                     "covers": [{k: v for k, v in cover.items() if k != "frames"}
                                for cover in line.get("covers", [])]}
                    for line in state.get("lines", [])]
    return out


def list_projects(user_id: str | None) -> list[dict]:
    if not LOCALIZE_ROOT.is_dir():
        return []
    items = []
    for path in LOCALIZE_ROOT.glob("*/state.json"):
        try:
            state = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if user_id is None or str(state.get("user_id")) == str(user_id):
            items.append({k: state.get(k) for k in
                          ("id", "name", "status", "stage", "message", "title", "output",
                           "progress", "created_at", "updated_at")})
    return sorted(items, key=lambda s: s.get("created_at") or 0, reverse=True)


def create(user_id: str, filename: str, src, cta_number: str, music: Optional[str]) -> dict:
    from brain.localize import DEFAULT_CTA_NUMBER, default_voice_provider

    project_id = uuid.uuid4().hex[:12]
    root = _dir(project_id)
    (root / "raw").mkdir(parents=True)
    (root / "exports").mkdir()
    name = Path(filename).name or "source.mp4"
    try:
        with open(root / "raw" / name, "wb") as out:
            shutil.copyfileobj(src, out, 1024 * 1024)
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    state = {
        "id": project_id, "user_id": str(user_id), "name": name,
        "source": f"raw/{name}", "created_at": time.time(),
        "cta_number": (cta_number or "").strip() or DEFAULT_CTA_NUMBER,
        "music": music or DEFAULT_LOCALIZE_MUSIC,
        "voice_provider": default_voice_provider(),
        "status": "queued", "stage": "", "message": "", "progress": 0,
        "title": "", "title_emojis": "", "title_layout": None, "lines": [],
        "output": None, "cost_usd": 0.0,
    }
    save(state)
    return state


def delete(project_id: str) -> None:
    with _lock:
        if project_id in _running:
            raise ValueError("project is busy")
    shutil.rmtree(_dir(project_id), ignore_errors=True)


def resolve_music(music: Optional[str]) -> Optional[Path]:
    """Library music paths are stored relative to the project root (assets/...)."""
    if not music:
        return None
    path = (PROJECT_ROOT / music).resolve()
    assets = (PROJECT_ROOT / "assets").resolve()
    if not path.is_relative_to(assets) or not path.is_file():
        return None
    return path


def update(project_id: str, changes: dict) -> dict:
    """Apply user edits (title, emojis, CTA number, music, line texts)."""
    from brain.localize import cta_text

    with _lock:
        if project_id in _running:
            raise ValueError("project is busy")
        state = load(project_id)
        if "title" in changes:
            state["title"] = str(changes["title"] or "").strip()
        if "title_emojis" in changes:
            state["title_emojis"] = str(changes["title_emojis"] or "").strip()
        if "music" in changes:
            music = changes["music"] or None
            if music and resolve_music(music) is None:
                raise ValueError("music file not found in the library")
            state["music"] = music
        if "voice_provider" in changes:
            from brain.localize import VOICE_PROVIDERS
            if changes["voice_provider"] not in VOICE_PROVIDERS:
                raise ValueError("voice provider must be elevenlabs")
            state["voice_provider"] = changes["voice_provider"]
        for key in ("caption_box", "title_box"):
            if key in changes:
                from engine.localize import BOX_STYLES
                value = changes[key] or None
                if value and value not in BOX_STYLES:
                    raise ValueError(f"{key} must be one of {', '.join(BOX_STYLES)}")
                state[key] = value
        if "end_card" in changes:
            state["end_card"] = bool(changes["end_card"])
        if "end_card_seconds" in changes:
            seconds = float(changes["end_card_seconds"] or 0)
            if not 1.0 <= seconds <= 10.0:
                raise ValueError("end card length must be 1-10 seconds")
            state["end_card_seconds"] = seconds
        if "cta_number" in changes:
            state["cta_number"] = str(changes["cta_number"] or "").strip() or state["cta_number"]
        edits = {int(item["i"]): item for item in changes.get("lines") or [] if "i" in item}
        for line in state["lines"]:
            edit = edits.get(line["i"])
            if not edit:
                continue
            if edit.get("kind") in {"speech", "lyrics", "cta"}:
                line["kind"] = edit["kind"]
            if "fa" in edit and line["kind"] == "speech":
                line["fa"] = str(edit["fa"] or "").strip()
        for line in state["lines"]:
            if line["kind"] == "cta":
                line["fa"] = cta_text(state["cta_number"])
        return save(state)


def _start(project_id: str, target, status: str) -> None:
    with _lock:
        if project_id in _running:
            raise ValueError("project is busy")
        state = load(project_id)
        state.update(status=status, message="", progress=0)
        save(state)
        _running.add(project_id)
        _cancel_events[project_id] = threading.Event()
        _pause_events[project_id] = threading.Event()

    def run() -> None:
        try:
            target(project_id)
        except TaskCanceled:
            state = load(project_id)
            state.update(status="canceled", stage="", message="Canceled by user")
            save(state)
        except Exception as exc:  # surface the failure in the project state
            log.exception("localize %s failed", project_id)
            state = load(project_id)
            state.update(status="error", message=str(exc)[:500])
            save(state)
        finally:
            with _lock:
                _running.discard(project_id)
                _cancel_events.pop(project_id, None)
                _pause_events.pop(project_id, None)

    threading.Thread(target=run, daemon=True).start()


def start_analyze(project_id: str) -> None:
    _start(project_id, _analyze, "analyzing")


def start_render(project_id: str) -> None:
    state = load(project_id)
    if not state.get("lines"):
        raise ValueError("analyze the video first")
    _start(project_id, _render, "rendering")


def pause(project_id: str) -> dict:
    with _lock:
        event = _pause_events.get(project_id)
        if event is None:
            raise ValueError("project is not running")
        event.set()
    state = load(project_id)
    state["resume_status"] = state.get("status") or "analyzing"
    state.update(status="paused", message="Paused by user")
    return save(state)


def resume(project_id: str) -> dict:
    with _lock:
        event = _pause_events.get(project_id)
        if event is None:
            raise ValueError("project is not running")
        event.clear()
    state = load(project_id)
    status = state.pop("resume_status", "analyzing")
    state.update(status=status, message="")
    return save(state)


def cancel(project_id: str) -> dict:
    with _lock:
        event = _cancel_events.get(project_id)
        pause_event = _pause_events.get(project_id)
        if event is None:
            raise ValueError("project is not running")
        event.set()
        if pause_event:
            pause_event.clear()
    state = load(project_id)
    state.update(status="canceled", message="Canceling…")
    return save(state)


def _checkpoint(project_id: str) -> None:
    while True:
        with _lock:
            cancel_event = _cancel_events.get(project_id)
            pause_event = _pause_events.get(project_id)
        if cancel_event and cancel_event.is_set():
            raise TaskCanceled()
        if not pause_event or not pause_event.is_set():
            return
        time.sleep(0.2)


def _stage(project_id: str, stage: str, **extra) -> dict:
    state = load(project_id)
    state.update(stage=stage, **extra)
    return save(state)


def _transcribe(video: Path, root: Path) -> tuple[dict, float, str]:
    """ElevenLabs Scribe first; local Whisper when it is unavailable.

    ElevenLabs transcription and voice share one credit balance, so an
    exhausted plan must not block analysis. Whisper gives the word timings
    caption detection needs and handles English sources well.
    """
    import hashlib

    from brain.transcribe_elevenlabs import transcribe_elevenlabs

    from brain.localize import elevenlabs_characters_left

    digest = hashlib.sha256(video.read_bytes()).hexdigest()[:16]
    error: Exception | None = None
    attempts = 3
    if elevenlabs_characters_left() == 0:
        error, attempts = RuntimeError("ElevenLabs credit is used up"), 0
    for _ in range(attempts):
        try:
            transcript, cost = transcribe_elevenlabs(video, root, language=None, file_digest=digest)
            return transcript, cost, "elevenlabs"
        except RuntimeError as exc:
            error = exc
            if "quota" in str(exc).lower() or "not set" in str(exc).lower():
                break  # permanent: do not retry
    log.warning("ElevenLabs transcription unavailable (%s); using local Whisper", str(error)[:200])
    from brain.transcribe import transcribe

    try:
        transcript = transcribe(video, root / "whisper", language=None, initial_prompt="", engine="whisper")
    except Exception as exc:
        raise RuntimeError(f"transcription failed (ElevenLabs: {str(error)[:200]}; Whisper: {exc})") from exc
    if not transcript.get("words"):
        raise RuntimeError(f"transcription failed: ElevenLabs unavailable ({str(error)[:200]}) "
                           "and local Whisper found no speech")
    return transcript, 0.0, "whisper"


def _analyze(project_id: str) -> None:
    from brain import localize as text
    from engine import localize as media

    root = _dir(project_id)
    _checkpoint(project_id)
    state = load(project_id)
    video = root / state["source"]
    _stage(project_id, "transcribing", progress=5)
    transcript, asr_cost, engine = _transcribe(video, root)
    _checkpoint(project_id)
    lines = text.split_lines(transcript)
    if not lines:
        raise RuntimeError("no speech found in the video")

    _stage(project_id, "finding captions", progress=20)
    scan = media.ocr_video(video)
    _checkpoint(project_id)
    headline = media.source_headline(scan)

    _stage(project_id, "translating", progress=50)
    data, usage = text.translate(lines, source_headline=headline)
    _checkpoint(project_id)
    lines, title, emojis = text.apply_translation(lines, data, state["cta_number"])

    _stage(project_id, "finding captions", progress=70)
    title_layout, layout = media.detect_layout(video, lines, transcript.get("words"), scan=scan)
    _checkpoint(project_id)
    english = media.english_regions(scan)
    for line, item in zip(lines, layout):
        line.update(item)

    state = load(project_id)
    state.update(
        status="ready", stage="", message="", progress=100,
        language=transcript.get("language"), asr_engine=engine,
        title=title, title_emojis=emojis, source_headline=headline,
        title_layout=title_layout, lines=lines, english_regions=english,
        caption_detector="visual-outline-v2",
        cost_usd=round(state.get("cost_usd", 0.0) + asr_cost + usage["cost_usd"], 4),
    )
    save(state)


def _render(project_id: str) -> None:
    from brain import localize as text
    from engine import localize as media

    root = _dir(project_id)
    _checkpoint(project_id)
    state = load(project_id)
    video = root / state["source"]
    if state.get("caption_detector") not in {"visual-outline-v2", "frame-outline-v3", "frame-outline-v4", "frame-outline-v5", "frame-outline-v6"}:
        # Upgrade legacy analyses without touching user-edited translations.
        _stage(project_id, "finding captions")
        scan = media.ocr_video(video)
        title_layout, layout = media.detect_layout(video, state["lines"], scan=scan)
        for line, item in zip(state["lines"], layout):
            line.update(item)
        state.update(title_layout=title_layout, caption_detector="visual-outline-v2")
        save(state)
    if state.get("caption_detector") != "frame-outline-v6":
        # The dropshipping renderer needs the source card boundaries, not one
        # median box per translated sentence. Track every source frame once
        # and preserve the user's edited translations.
        _stage(project_id, "tracking caption frames")
        _, _, source_duration = media.probe_video(video)
        windows = media.frame_caption_windows(video, state, source_duration)
        _checkpoint(project_id)
        media.read_caption_cards(video, windows)
        _checkpoint(project_id)
        spoken_lines = [line for line in state["lines"] if line.get("kind") != "lyrics" and line.get("fa")]
        owned = {line["i"]: [] for line in state["lines"]}
        for window in windows:
            owner = max(spoken_lines, key=lambda line: max(0, min(window["end"], line["end"])
                                                          - max(window["start"], line["start"])), default=None)
            if owner and window["end"] > owner["start"] and window["start"] < owner["end"]:
                owned[owner["i"]].append(window)
        for line in state["lines"]:
            covers = owned[line["i"]]
            line["covers"] = covers
            line["box"] = ({key: media._median([c["box"][key] for c in covers])
                            for key in ("cx", "cy", "w", "h")} if covers else line.get("box"))
        state["caption_detector"] = "frame-outline-v6"
        save(state)
    _stage(project_id, "planning caption phrases")
    text.translate_caption_cards(state["lines"])
    _checkpoint(project_id)
    save(state)
    _stage(project_id, "generating voice")
    clips = {}
    spoken = [l for l in state["lines"] if l["kind"] != "lyrics" and l.get("fa")]
    # Existing projects may still persist the former Sarovi choice. All new
    # and resumed renders now use Localize's canonical ElevenLabs pipeline.
    provider = text.default_voice_provider()
    state["voice_provider"] = provider
    text.check_voice_budget([l["fa"] for l in spoken], provider, root / "tts")
    if provider == "elevenlabs":
        # One take for the whole narration, cut per line by character timings.
        pieces = text.synthesize_narration([l["fa"] for l in spoken], root / "tts")
        clips = {line["i"]: clip for line, clip in zip(spoken, pieces) if clip[1] > 0}
        _stage(project_id, "generating voice", progress=40)
    else:
        for n, line in enumerate(spoken, 1):
            clips[line["i"]] = text.synthesize(line["fa"], root / "tts", provider)
            _stage(project_id, "generating voice", progress=int(n / max(1, len(spoken)) * 40))
    if "english_regions" not in state:
        # Projects analysed before English text covers existed.
        _stage(project_id, "finding English text")
        state["english_regions"] = media.english_regions(media.ocr_video(video))
        _stage(project_id, "rendering", english_regions=state["english_regions"])
    _, _, duration = media.probe_video(video)
    placements = media.place_clips(state["lines"], clips, duration)

    _stage(project_id, "rendering")
    version = len(list((root / "exports").glob("localized_v*.mp4"))) + 1
    out = root / "exports" / f"localized_v{version}.mp4"
    logo = PROJECT_ROOT / "assets" / "brand" / "logo.png"

    def progress(pct: int) -> None:
        _checkpoint(project_id)
        current = load(project_id)
        current["progress"] = 40 + int(pct * 0.6)
        save(current)

    # Box colours: the project's choice, else the next colour each render.
    names = list(media.BOX_STYLES)
    caption_box = state.get("caption_box") or names[version % len(names)]
    style = {**state, "caption_box": caption_box, "title_box": state.get("title_box") or caption_box}
    media.render(
        video, style, placements, out, work_dir=root / "work",
        fonts_dir=PROJECT_ROOT / "presets" / "fonts",
        music=resolve_music(state.get("music") or DEFAULT_LOCALIZE_MUSIC),
        logo=logo if logo.is_file() else None,
        on_progress=progress,
    )
    state = load(project_id)
    state.update(status="done", stage="", message="", progress=100, output=f"exports/{out.name}",
                 placements=placements)
    save(state)


def recover_interrupted() -> int:
    """Mark projects left analyzing/rendering by a restart as failed."""
    if not LOCALIZE_ROOT.is_dir():
        return 0
    n = 0
    for path in LOCALIZE_ROOT.glob("*/state.json"):
        try:
            state = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if state.get("status") in {"queued", "analyzing", "rendering"}:
            state.update(status="error", message="Interrupted by a server restart. Run it again.")
            save(state)
            n += 1
    return n
