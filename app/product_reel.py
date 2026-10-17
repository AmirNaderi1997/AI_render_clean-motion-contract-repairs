"""Landing URL -> editable storyboard -> source-less HyperFrames product reel."""
from __future__ import annotations

from html.parser import HTMLParser
import ipaddress
import json
import logging
import re
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from app import jobs as jobstore
from brain.product_reel import plan
from engine.hyperframes.product import build_product_project
from engine.hyperframes.renderer import render_project
from engine.motion_recipes import BY_ID

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = "product_reel.json"
_lock = threading.Lock()
_running: set[str] = set()
_cancel: dict[str, threading.Event] = {}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""; self.meta: dict[str, str] = {}; self.headings: list[str] = []
        self.paragraphs: list[str] = []; self._capture = ""; self._buffer: list[str] = []
        self.styles: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {str(k).lower(): str(v or "") for k, v in attrs}
        if tag in {"title", "h1", "h2", "h3", "p", "style"}:
            self._capture, self._buffer = tag, []
        if tag == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            if key and values.get("content"):
                self.meta[key] = values["content"].strip()

    def handle_endtag(self, tag: str) -> None:
        if tag != self._capture:
            return
        text = re.sub(r"\s+", " ", "".join(self._buffer)).strip()
        if tag == "title": self.title = text
        elif tag.startswith("h") and text: self.headings.append(text)
        elif tag == "p" and text: self.paragraphs.append(text)
        elif tag == "style" and text: self.styles.append(text)
        self._capture, self._buffer = "", []

    def handle_data(self, data: str) -> None:
        if self._capture: self._buffer.append(data)


def _public_url(value: str) -> str:
    value = value.strip()
    if not re.match(r"^https?://", value, re.I):
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Enter a public HTTP or HTTPS landing-page URL")
    if parsed.hostname.lower() in {"localhost", "localhost.localdomain"}:
        raise ValueError("Local and private addresses are not allowed")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError("The landing-page hostname could not be resolved") from exc
    for entry in addresses:
        ip = ipaddress.ip_address(entry[4][0])
        if not ip.is_global:
            raise ValueError("Local and private addresses are not allowed")
    return value


def inspect_url(value: str) -> dict:
    url = _public_url(value)
    headers = {"User-Agent": "RafieiAIEditor/1.0 (+product-reel-crawler)"}
    with httpx.Client(timeout=20, follow_redirects=False, headers=headers) as client:
        for _ in range(4):
            response = client.get(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                target = response.headers.get("location")
                if not target: raise ValueError("Landing page returned an empty redirect")
                url = _public_url(urljoin(url, target)); continue
            response.raise_for_status(); break
        else:
            raise ValueError("Landing page redirected too many times")
    if len(response.content) > 2_000_000:
        raise ValueError("Landing page is larger than 2 MB")
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower():
        raise ValueError("URL must point to an HTML landing page")
    parser = PageParser(); parser.feed(response.text[:2_000_000])
    description = parser.meta.get("og:description") or parser.meta.get("description") or next(iter(parser.paragraphs), "")
    name = parser.meta.get("og:site_name") or parser.meta.get("application-name") or parser.title.split("|")[0].split("–")[0].strip()
    colour_source = " ".join(parser.styles) + " " + response.text[:200_000]
    colours = []
    for colour in re.findall(r"#[0-9a-fA-F]{6}\b", colour_source):
        colour = colour.upper()
        if colour not in colours and colour not in {"#FFFFFF", "#000000"}: colours.append(colour)
        if len(colours) >= 6: break
    return {
        "url": url, "host": urlparse(url).hostname, "name": name or parser.title or urlparse(url).hostname,
        "title": parser.meta.get("og:title") or parser.title, "description": description[:900],
        "features": (parser.headings + parser.paragraphs)[:18], "colours": colours,
        "image": urljoin(url, parser.meta.get("og:image", "")) if parser.meta.get("og:image") else None,
    }


def _path(job_dir: Path) -> Path: return job_dir / STATE_FILE


def load(job_dir: Path) -> dict:
    if not _path(job_dir).is_file(): raise FileNotFoundError("product reel not found")
    return json.loads(_path(job_dir).read_text())


def save(job_dir: Path, state: dict) -> dict:
    state["updated_at"] = time.time(); tmp = _path(job_dir).with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2)); tmp.replace(_path(job_dir)); return state


def create(user_id: str, url: str) -> tuple[jobstore.Job, dict]:
    # Validate before allocating persistent state so malformed/private URLs do
    # not leave orphan jobs behind. The worker resolves again before fetching.
    normalized_url = _public_url(url)
    job = jobstore.create_job(user_id=user_id)
    state = {"status": "analyzing", "stage": "reading landing page", "progress": 5,
             "url": normalized_url, "source": None, "storyboard": None, "usage": {}, "output": None, "message": ""}
    save(job.dir, state); job.generate.status = "running"; job.generate.stage = "reading landing page"; jobstore.update_job(job)
    key = str(job.dir)
    with _lock: _running.add(key); _cancel[key] = threading.Event()
    def run() -> None:
        try:
            source = inspect_url(normalized_url); state.update(source=source, stage="directing product story", progress=40); save(job.dir, state)
            if _cancel[key].is_set(): raise InterruptedError
            board, usage = plan(source); state.update(status="ready", stage="review storyboard", progress=100,
                                                       storyboard=board, usage=usage); save(job.dir, state)
            job.generate.status = "done"; job.generate.stage = "review storyboard"; job.generate.model = str(usage.get("model") or "")
        except InterruptedError:
            state.update(status="canceled", stage="", message="Canceled by user"); save(job.dir, state); job.generate.status = "error"
        except Exception as exc:
            log.exception("product reel analysis failed for %s", job.id)
            state.update(status="error", stage="", message=str(exc)[:500]); save(job.dir, state)
            job.generate.status = "error"; job.generate.message = str(exc)[:500]
        finally:
            jobstore.update_job(job)
            with _lock: _running.discard(key); _cancel.pop(key, None)
    threading.Thread(target=run, daemon=True).start()
    return job, state


def update(job_dir: Path, payload: dict) -> dict:
    if str(job_dir) in _running: raise ValueError("product reel is busy")
    state = load(job_dir); board = dict(state.get("storyboard") or {}); scenes = []
    for index, raw in enumerate(payload.get("scenes") or []):
        if not isinstance(raw, dict) or not str(raw.get("title") or "").strip(): continue
        recipe = BY_ID.get(str(raw.get("recipe") or ""))
        if not recipe: raise ValueError(f"Unknown motion recipe: {raw.get('recipe')}")
        scenes.append({"id": str(raw.get("id") or f"scene-{index+1}"), "role": str(raw.get("role") or "evidence")[:24],
                       "title": str(raw["title"]).strip()[:90], "items": [str(v).strip()[:48] for v in raw.get("items") or []][:4],
                       "duration": max(2.2, min(5.0, float(raw.get("duration") or 3.5))), "recipe": recipe.id,
                       "renderer": recipe.renderer, "motion": recipe.motion, "why": str(raw.get("why") or recipe.best_for)[:180]})
    if len(scenes) < 3: raise ValueError("Keep at least three storyboard scenes")
    board["scenes"] = scenes[:8]; state["storyboard"] = board; return save(job_dir, state)


def start_render(job: jobstore.Job) -> dict:
    key = str(job.dir)
    with _lock:
        if key in _running: raise ValueError("product reel is busy")
        _running.add(key); _cancel[key] = threading.Event()
    state = load(job.dir); state.update(status="rendering", stage="building motion graphics", progress=5, message=""); save(job.dir, state)
    job.render.status = "running"; job.render.progress = 5; jobstore.update_job(job)
    def run() -> None:
        try:
            music = ROOT / "assets/music/motivational_piano_beat.mp3"
            project = job.dir / "product_reel_work" / "hyperframes"
            _, beats, duration = build_product_project(project, state["storyboard"], music=music)
            state.update(progress=25); save(job.dir, state)
            out = job.dir / "exports" / f"product_reel_v{int(time.time())}.mp4"
            def progress(value: int) -> None:
                state.update(progress=value, stage="rendering motion graphics"); save(job.dir, state)
                job.render.progress = value; jobstore.update_job(job)
            render_project(project, out, on_progress=progress, should_cancel=lambda: _cancel[key].is_set())
            state.update(status="done", stage="", progress=100, output=out.name,
                         visual_beats=[beat.model_dump() for beat in beats], duration=duration); save(job.dir, state)
            job.render.status = "done"; job.render.progress = 100; job.render.output = out.name
        except Exception as exc:
            if "render canceled" in str(exc).lower():
                state.update(status="canceled", stage="", message="Canceled by user"); save(job.dir, state)
                job.render.status = "error"; job.render.message = "Canceled by user"; return
            log.exception("product reel render failed for %s", job.id)
            state.update(status="error", stage="", message=str(exc)[:500]); save(job.dir, state)
            job.render.status = "error"; job.render.message = str(exc)[:500]
        finally:
            jobstore.update_job(job)
            with _lock: _running.discard(key); _cancel.pop(key, None)
    threading.Thread(target=run, daemon=True).start(); return state


def cancel(job_dir: Path) -> dict:
    event = _cancel.get(str(job_dir))
    if event: event.set()
    state = load(job_dir); state.update(status="canceled", stage="", message="Canceled by user"); return save(job_dir, state)
