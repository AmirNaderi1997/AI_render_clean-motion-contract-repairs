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
    "music": DEFAULT_MUSIC, "cta": "", "style": "talking_1", "suggested_style": None,
    "suggested_style_reason": "", "analysis_ready": False, "output": None, "decisions": None,
    "render_settings": {
        "grade": {"brightness": 0, "contrast": 100, "saturation": 100, "temperature": 0, "vignette": 50},
        "zoom": {"enabled": True, "amount": 100, "base_scale": 100, "close_scale": 140},
        "key_moments_enabled": True,
        "first_key_moment_enabled": True,
        "first_key_moment_sentence": None,
        "key_moment_effect": "grayscale_title",
        "title_color": "#F5B800",
        "outro_logo": {"enabled": True, "motion": "pop"},
        "disabled_moments": [],
    },
}
EDITABLE = {"hook", "hook2", "hook_highlight", "name", "title", "music", "cta", "style", "captions", "storyboard", "render_settings"}
_lock = threading.Lock()
_running: set[str] = set()
_cancel_events: dict[str, threading.Event] = {}
_pause_events: dict[str, threading.Event] = {}

class TaskCanceled(Exception):
    pass

def _checkpoint(job_dir: Path) -> None:
    key = str(job_dir)
    while True:
        with _lock:
            cancel_event, pause_event = _cancel_events.get(key), _pause_events.get(key)
        if cancel_event and cancel_event.is_set():
            raise TaskCanceled()
        if not pause_event or not pause_event.is_set():
            return
        time.sleep(0.2)


def _path(job_dir: Path) -> Path:
    return job_dir / "talking_reel.json"


def load(job_dir: Path) -> dict:
    path = _path(job_dir)
    state = dict(DEFAULTS)
    if path.is_file():
        state.update(json.loads(path.read_text()))
    state["render_settings"] = _clean_render_settings(state.get("render_settings"))
    return state


def save(job_dir: Path, state: dict) -> dict:
    state["updated_at"] = time.time()
    tmp = _path(job_dir).with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    tmp.replace(_path(job_dir))
    return state


def public(state: dict) -> dict:
    result = {k: v for k, v in state.items() if not k.startswith("decisions")}
    key = _decisions_key(str(state.get("style") or "talking_1"))
    decisions = state.get(key) or {}
    captions = decisions.get("captions") or {}
    result["captions"] = [
        {"i": int(index), "text": str(text)}
        for index, text in sorted(captions.items(), key=lambda item: int(item[0]))
    ]
    result["storyboard"] = decisions.get("storyboard") or []
    result["timeline"] = _timeline(decisions, str(state.get("style") or "talking_1"))
    return result


def _timeline(decisions: dict, style: str) -> list[dict]:
    """Editable pre-render events, using transcript sentence indices as stable ids."""
    rows = []
    for source in ("notes", "titles", "storyboard", "broll"):
        for index, item in enumerate(decisions.get(source) or []):
            try:
                sentence = int(item.get("i", index))
            except (TypeError, ValueError):
                sentence = index
            rows.append({
                "id": f"{style}-{source}-{sentence}-{index}", "sentence": sentence,
                "title": str(item.get("text") or item.get("title") or item.get("label") or f"لحظه کلیدی {len(rows) + 1}"),
                "kind": "key_moment", "order": len(rows),
            })
    return rows


def _clean_render_settings(value: object) -> dict:
    current = json.loads(json.dumps(DEFAULTS["render_settings"]))
    if not isinstance(value, dict):
        return current
    grade = value.get("grade") if isinstance(value.get("grade"), dict) else {}
    limits = {"brightness": (-30, 30), "contrast": (50, 160), "saturation": (0, 180),
              "temperature": (-50, 50), "vignette": (0, 100)}
    for key, (low, high) in limits.items():
        try:
            current["grade"][key] = max(low, min(high, int(grade.get(key, current["grade"][key]))))
        except (TypeError, ValueError):
            pass
    zoom = value.get("zoom") if isinstance(value.get("zoom"), dict) else {}
    current["zoom"]["enabled"] = bool(zoom.get("enabled", current["zoom"]["enabled"]))
    try:
        current["zoom"]["amount"] = max(0, min(200, int(zoom.get("amount", 100))))
    except (TypeError, ValueError):
        pass
    for key, default, low, high in (
        ("base_scale", 100, 100, 180), ("close_scale", 140, 100, 220),
    ):
        try:
            current["zoom"][key] = max(low, min(high, int(zoom.get(key, default))))
        except (TypeError, ValueError):
            pass
    current["zoom"]["close_scale"] = max(
        current["zoom"]["base_scale"], current["zoom"]["close_scale"]
    )
    for key in ("key_moments_enabled", "first_key_moment_enabled"):
        current[key] = bool(value.get(key, current[key]))
    try:
        selected = value.get("first_key_moment_sentence")
        current["first_key_moment_sentence"] = None if selected in (None, "") else max(0, int(selected))
    except (TypeError, ValueError):
        pass
    if value.get("key_moment_effect") in {"grayscale_title", "title_only", "grayscale", "none"}:
        current["key_moment_effect"] = value["key_moment_effect"]
    import re
    colour = str(value.get("title_color") or "").upper()
    if re.fullmatch(r"#[0-9A-F]{6}", colour):
        current["title_color"] = colour
    outro = value.get("outro_logo") if isinstance(value.get("outro_logo"), dict) else {}
    current["outro_logo"]["enabled"] = bool(outro.get("enabled", True))
    if outro.get("motion") in {"pop", "fade", "slide", "none"}:
        current["outro_logo"]["motion"] = outro["motion"]
    current["disabled_moments"] = [str(v)[:80] for v in (value.get("disabled_moments") or [])][:30]
    return current


def _decisions_key(style: str) -> str:
    return "decisions" if style == "talking_1" else f"decisions_{style.rsplit('_', 1)[-1]}"


def update(job_dir: Path, changes: dict) -> dict:
    with _lock:
        if str(job_dir) in _running:
            raise ValueError("talking reel is busy")
        state = load(job_dir)
        for key in EDITABLE & set(changes):
            value = changes[key]
            if key == "render_settings":
                state[key] = _clean_render_settings(value)
                continue
            if key in {"captions", "storyboard"}:
                decisions_key = _decisions_key(str(state.get("style") or "talking_1"))
                decisions = dict(state.get(decisions_key) or {})
                if key == "storyboard":
                    allowed = {"concept", "stat", "comparison", "steps", "ui_showcase", "media_collage",
                               "chat", "map_route", "spec_callout", "kinetic_type", "before_after"}
                    board = []
                    for item in value or []:
                        if not isinstance(item, dict) or not str(item.get("title") or "").strip():
                            continue
                        clean = dict(item)
                        clean["title"] = str(clean["title"]).strip()[:80]
                        if clean.get("visual_type") not in allowed:
                            clean["visual_type"] = "concept"
                        board.append(clean)
                    decisions["storyboard"] = board[:9]
                    state[decisions_key] = decisions
                    continue
                current = dict(decisions.get("captions") or {})
                for item in value or []:
                    try:
                        index = int(item.get("i"))
                    except (AttributeError, TypeError, ValueError):
                        continue
                    text = str(item.get("text") or "").strip()
                    if text and (index in current or str(index) in current):
                        current[index] = text
                        current.pop(str(index), None)
                decisions["captions"] = current
                state[decisions_key] = decisions
                continue
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


def analyze(job_dir: Path, raw_video: Path, *, style: Optional[str] = None) -> dict:
    """Transcribe and prepare editable AI decisions without starting a render."""
    key = str(job_dir)
    with _lock:
        if key in _running:
            raise ValueError("talking reel is busy")
        state = load(job_dir)
        state.update(status="running", stage="transcribing", message="", progress=5, analysis_ready=False)
        save(job_dir, state)
        _running.add(key)
        _cancel_events[key], _pause_events[key] = threading.Event(), threading.Event()

    def run() -> None:
        try:
            _analyze(job_dir, raw_video, style=style)
        except TaskCanceled:
            current = load(job_dir); current.update(status="canceled", stage="", message="Canceled by user"); save(job_dir, current)
        except Exception as exc:
            log.exception("talking reel analysis failed for %s", job_dir.name)
            current = load(job_dir)
            current.update(status="error", stage="", message=str(exc)[:500], analysis_ready=False)
            save(job_dir, current)
        finally:
            with _lock:
                _running.discard(key)
                _cancel_events.pop(key, None); _pause_events.pop(key, None)

    threading.Thread(target=run, daemon=True).start()
    return state


def _analyze(job_dir: Path, video: Path, *, style: Optional[str]) -> None:
    from dotenv import load_dotenv
    from importlib import import_module
    from brain import talking_reel as base_brain

    load_dotenv(PROJECT_ROOT / ".env")
    transcript = transcript_for(job_dir, video)
    selected = style
    reason = ""
    if not selected:
        _stage(job_dir, "choosing style", progress=15)
        selected, reason = base_brain.recommend_style(transcript["sentences"])
    from engine.talking_reel import STYLES
    if selected not in STYLES:
        raise ValueError(f"unknown style {selected!r}")

    _stage(job_dir, "editing text", progress=30)
    state = load(job_dir)
    if selected == "talking_1":
        decisions = base_brain.decide(transcript["sentences"])
        state["decisions"] = decisions
        state["hook"] = decisions["hook"]
        state["hook_highlight"] = decisions["hook_highlight"]
    else:
        brain_name, decisions_key, _music = SPLIT_STYLES[selected]
        decisions = import_module(brain_name).decide(
            transcript["sentences"], [p.name for p in user_media(job_dir)]
        )
        state[decisions_key] = decisions
        state["hook2"] = decisions["hook"]
    state.update(
        status="ready", stage="", message="", progress=100, style=selected,
        suggested_style=selected if style is None else state.get("suggested_style"),
        suggested_style_reason=reason if style is None else state.get("suggested_style_reason", ""),
        analysis_ready=True,
    )
    save(job_dir, state)


def start(job_dir: Path, raw_video: Path, *, regenerate: bool = False) -> dict:
    key = str(job_dir)
    with _lock:
        if key in _running:
            raise ValueError("talking reel is busy")
        state = load(job_dir)
        if not state.get("analysis_ready"):
            raise ValueError("analyze and review the talking reel before rendering")
        state.update(status="running", stage="queued", message="", progress=0)
        save(job_dir, state)
        _running.add(key)
        _cancel_events[key], _pause_events[key] = threading.Event(), threading.Event()

    def run() -> None:
        try:
            _run(job_dir, raw_video, regenerate=regenerate)
        except TaskCanceled:
            current = load(job_dir); current.update(status="canceled", stage="", message="Canceled by user"); save(job_dir, current)
        except Exception as exc:
            log.exception("talking reel failed for %s", job_dir.name)
            current = load(job_dir)
            current.update(status="error", stage="", message=str(exc)[:500])
            save(job_dir, current)
        finally:
            with _lock:
                _running.discard(key)
                _cancel_events.pop(key, None); _pause_events.pop(key, None)

    threading.Thread(target=run, daemon=True).start()
    return state


def _stage(job_dir: Path, stage: str, **extra) -> None:
    _checkpoint(job_dir)
    state = load(job_dir)
    state.update(stage=stage, **extra)
    save(job_dir, state)

def pause(job_dir: Path) -> dict:
    key = str(job_dir)
    with _lock:
        event = _pause_events.get(key)
        if event is None: raise ValueError("talking reel is not running")
        event.set()
    state = load(job_dir); state.update(status="paused", message="Paused by user"); return save(job_dir, state)

def resume(job_dir: Path) -> dict:
    key = str(job_dir)
    with _lock:
        event = _pause_events.get(key)
        if event is None: raise ValueError("talking reel is not running")
        event.clear()
    state = load(job_dir); state.update(status="running", message=""); return save(job_dir, state)

def cancel(job_dir: Path) -> dict:
    key = str(job_dir)
    with _lock:
        event, pause_event = _cancel_events.get(key), _pause_events.get(key)
        if event is None: raise ValueError("talking reel is not running")
        event.set()
        if pause_event: pause_event.clear()
    state = load(job_dir); state.update(status="canceled", message="Canceling…"); return save(job_dir, state)


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
    if style in SPLIT_STYLES:
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
    settings = state.get("render_settings") or DEFAULTS["render_settings"]
    decisions = _apply_timeline_choices(decisions, "talking_1", settings)

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
                 render_settings=settings,
                 logo_path=custom_logo(job_dir),
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


def custom_logo(job_dir: Path) -> Optional[Path]:
    path = job_dir / "talking_reel_logo.png"
    return path if path.is_file() else None


def _library_pictures() -> list[dict]:
    index = PROJECT_ROOT / "assets" / "library_index.json"
    try:
        assets = json.loads(index.read_text()).get("assets") or []
    except (OSError, ValueError):
        return []
    return [a for a in assets if Path(str(a.get("path") or "")).suffix.lower() in IMAGE_EXTENSIONS
            and (PROJECT_ROOT / a["path"]).is_file()]


def resolve_pictures(job_dir: Path, decisions: dict, style: str) -> tuple[dict[int, str], list[dict]]:
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
                provider_name = _talking_image_provider()
                # Include the renderer/prompt revision in the cache key so an
                # improved visual direction never silently reuses the old,
                # low-quality AI pictures.
                cache_material = f"minimal-v3|{style}|{provider_name}|{slot['visual']}"
                key = hashlib.sha256(cache_material.encode()).hexdigest()[:16]
                entry.update(source="ai", file=str(job_dir / "talking2_broll" / f"ai_{key}.png"))
                wanted_ai.append((_visual_prompt(slot["visual"], style), Path(entry["file"]), provider_name))
        slots.append(entry)

    def generate(item: tuple[str, Path, str]) -> None:
        prompt, dst, provider_name = item
        if dst.is_file():
            return
        from brain.media_provider import get_provider

        dst.parent.mkdir(parents=True, exist_ok=True)
        result = get_provider(provider_name).generate_image(prompt, "1:1", dst.parent)
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


def _talking_image_provider() -> str:
    """Best configured provider for talking-reel visuals.

    The premium Google model is preferred. Deployments can override this with
    TALKING_IMAGE_PROVIDER without changing the general content-creator model.
    """
    import os
    from brain.media_provider import get_provider

    configured = os.getenv("TALKING_IMAGE_PROVIDER", "").strip()
    candidates = [configured] if configured else [
        "sarovi_nano_banana_pro", "jarvis_image", "sarovi_nano_banana",
    ]
    for name in candidates:
        if name and get_provider(name).has_key:
            return name
    return candidates[0]


def _visual_prompt(subject: str, style: str) -> str:
    shared = (
        "Create one premium, restrained visual for a vertical educational reel. "
        "One clear focal subject, simple composition, generous negative space, crisp edges, "
        "subtle natural texture, tasteful studio art direction. No people, faces, hands, crowds, "
        "screens, charts, text, letters, logos, watermarks, surreal anatomy, glossy stock-art look, "
        "or generic AI aesthetics. Compose safely for a near-square editorial panel. "
    )
    if style == "talking_3":
        direction = (
            "Use a believable minimalist still-life photograph on charcoal or warm ivory, soft "
            "directional light, muted colors, premium editorial magazine mood. "
        )
    else:
        direction = (
            "Use a Swiss-style flat editorial illustration built from two to four recognizable "
            "everyday objects, off-white background, charcoal linework, and one muted teal or amber "
            "accent. Communicate the idea immediately; avoid meaningless abstract geometry. No gradients or 3D. "
        )
    return shared + direction + "Concept to communicate: " + subject.strip()


def _try(fn, item) -> Optional[str]:
    try:
        fn(item)
        return None
    except Exception as exc:  # one failed picture becomes a text card, not a failed render
        return str(exc)[:200]


SPLIT_STYLES = {   # style -> (brain module, decisions key, default music)
    "talking_2": ("brain.talking_reel_2", "decisions_2", "assets/music/motivational_piano_beat.mp3"),
    "talking_3": ("brain.talking_reel_3", "decisions_3", "assets/music/cinematic_pulse.mp3"),
    "talking_4": ("brain.talking_reel_4", "decisions_4", "assets/music/soft_lofi_loop.mp3"),
}


def _apply_timeline_choices(decisions: dict, style: str, settings: dict) -> dict:
    """Apply review choices to AI decisions before a render plan is built."""
    result = dict(decisions)
    if not settings.get("first_key_moment_enabled", True):
        result["cold_open"] = None
    elif settings.get("first_key_moment_sentence") is not None:
        cold = dict(result.get("cold_open") or {})
        cold["i"] = int(settings["first_key_moment_sentence"])
        result["cold_open"] = cold
    effect = settings.get("key_moment_effect", "grayscale_title")
    if not settings.get("key_moments_enabled", True) or effect == "none":
        for key in ("notes", "titles", "storyboard"):
            result[key] = []
        result["bw"] = []
    elif effect == "title_only":
        result["bw"] = []
    elif effect == "grayscale":
        result["notes"] = []
        result["titles"] = []
    disabled = set(settings.get("disabled_moments") or [])
    for key in ("notes", "titles", "storyboard", "broll"):
        kept = []
        for index, item in enumerate(result.get(key) or []):
            moment_id = f"{style}-{key}-{int(item.get('i', index))}-{index}"
            if moment_id not in disabled:
                kept.append(item)
        result[key] = kept
    return result


def _run_split(job_dir: Path, video: Path, style: str, *, regenerate: bool) -> None:
    """The split-screen styles ("صحبتی ۲", "صحبتی ۳"): pictures on top, the speaker below."""
    from importlib import import_module

    from app.config import settings
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
    render_settings = state.get("render_settings") or DEFAULTS["render_settings"]
    decisions = _apply_timeline_choices(decisions, style, render_settings)
    hyperframes = style == "talking_2" and settings.TALKING_HYPERFRAMES_ENABLED
    _stage(job_dir, "planning visual beats" if hyperframes else "finding pictures", progress=25)
    if hyperframes:
        # A neutral placeholder makes the proven style-2 renderer place the
        # speaker in the lower half. HyperFrames paints over the upper card,
        # so motion graphics never cover the speaker's face.
        from PIL import Image

        placeholder = job_dir / "talking_reel_work" / "motion_placeholder.png"
        placeholder.parent.mkdir(parents=True, exist_ok=True)
        if not placeholder.is_file():
            Image.new("RGB", (1080, 1080), "#F3F0E8").save(placeholder)
        pictures = {int(item["i"]): str(placeholder) for item in decisions.get("broll") or []}
        slots = [{"i": item["i"], "source": "motion", "status": "planned"}
                 for item in decisions.get("broll") or []]
    else:
        pictures, slots = resolve_pictures(job_dir, decisions, style)
    if not hyperframes and style in {"talking_2", "talking_3"} and decisions.get("broll"):
        required = min(2, len(decisions["broll"]))
        if len(pictures) < required:
            raise RuntimeError("Enough AI visuals were not generated. Check the image provider, then analyze and render again.")
        # A failed image slot should return to the real speaker, never become
        # an unattractive text-card substitute.
        decisions = {
            **decisions,
            "broll": [item for item in decisions["broll"] if item["i"] in pictures],
        }
    _stage(job_dir, "tracking the face", progress=35, slots=slots)
    faces = _faces(job_dir, video, media)
    source_duration = float(transcript.get("duration") or 0) or media.probe_video(video)[2]
    visual_plan = media.plan_reel(transcript, decisions, faces, source_duration, pictures)
    # The rough cut stays clean: HyperFrames owns the visual beats, while the
    # proven FFmpeg renderer keeps cuts, audio, face framing and Ray captions.
    clean_decisions = {**decisions, "chips": [], "broll": []} if hyperframes else decisions
    plan = media.plan_reel(transcript, clean_decisions, faces, source_duration,
                           {} if hyperframes else pictures)
    _stage(job_dir, "rendering", progress=45)
    out = _next_output(job_dir)
    state = load(job_dir)

    def progress(pct: int) -> None:
        ceiling = 30 if hyperframes else 55
        _stage(job_dir, "rendering rough cut" if hyperframes else "rendering",
               progress=45 + int(pct * ceiling / 100))

    # The talking_1 default bed does not suit every style; an explicit choice wins.
    music = state.get("music")
    if music in (None, DEFAULT_MUSIC) and state.get("music") is not None:
        music = default_music
    rough = job_dir / "talking_reel_work" / "hyperframes_base.mp4" if hyperframes else out
    media.render(video, plan, rough, work_dir=job_dir / "talking_reel_work",
                 music=resolve_music(music), cta=state.get("cta") or "", render_settings=render_settings,
                 logo_path=custom_logo(job_dir),
                 on_progress=progress)
    if hyperframes:
        from engine.hyperframes import build_project, build_visual_beats, render_project

        beats = build_visual_beats(visual_plan, decisions, transcript)
        if not beats:
            raise RuntimeError("The visual planner produced no usable motion beats")
        _stage(job_dir, "building motion graphics", progress=78,
               visual_beats=[beat.model_dump() for beat in beats])
        project = job_dir / "talking_reel_work" / "hyperframes"
        build_project(project, rough, beats, duration=plan.duration)
        _stage(job_dir, "rendering motion graphics", progress=82)
        render_project(
            project, out,
            on_progress=lambda pct: _stage(job_dir, "rendering motion graphics", progress=pct),
        )
        from engine.hyperframes.quality import improve_beats, review_render
        review = review_render(out, beats, job_dir / "talking_reel_work")
        _stage(job_dir, "reviewing motion graphics", progress=99, visual_qc=review)
        if not review["passed"]:
            beats = improve_beats(beats)
            _stage(job_dir, "improving motion graphics", progress=82,
                   visual_beats=[beat.model_dump() for beat in beats])
            build_project(project, rough, beats, duration=plan.duration)
            render_project(project, out,
                           on_progress=lambda pct: _stage(job_dir, "improving motion graphics", progress=pct))
            review = review_render(out, beats, job_dir / "talking_reel_work")
            _stage(job_dir, "reviewing improved render", progress=99, visual_qc=review)
    state = load(job_dir)
    state.update(status="done", stage="", message="", progress=100, output=f"exports/{out.name}",
                 duration=round(plan.duration, 2), shots=len(plan.shots))
    save(job_dir, state)
