"""Social-media reference fetcher for the editor (runs on Vercel, outside the network that blocks these sites).

POST /api/index  {"url": "https://www.instagram.com/reel/..."}   header x-relay-secret: <RELAY_SECRET>
  Instagram links (posts, reels, stories, highlights) go through the GetInSaver API when GETINSAVER_API_KEY is set: Instagram asks datacenter
  IPs to log in, so yt-dlp alone needs cookies that expire. yt-dlp stays as the fallback and handles every other site.
  -> the video file itself (progressive mp4, <= 80 MB, <= 180 s), streamed; metadata in x-* response headers.
GET  /api/index -> {"ok": true, "yt_dlp": "<version>"}

The secret is required, only a fixed list of hosts is allowed, and nothing is stored: the file lives in /tmp for the length of
one request. Optional environment: YTDLP_COOKIES_B64 (base64 Netscape cookies for networks that need a login), YTDLP_PROXY and, for Instagram,
GETINSAVER_API_KEY (the key stays on Vercel and never reaches the editor).
"""
from __future__ import annotations

import base64
import hmac
import os
import shutil
import json
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

HOSTS = {"instagram.com", "youtube.com", "youtu.be", "tiktok.com", "vimeo.com", "x.com", "twitter.com", "facebook.com", "fb.watch"}
MAX_BYTES = 80 * 1024 * 1024
MAX_SECONDS = 180
CHUNK = 1024 * 1024

GETINSAVER_URL = "https://developers.getinsaver.com/v1/resolve"
# Failure codes of the API, as the editor should report them (the editor maps these words to a plain explanation).
GETINSAVER_REASONS = {"INSUFFICIENT_CREDITS": "getinsaver credits exhausted", "UPSTREAM_REJECTED": "private, deleted or login-only content",
                      "MEDIA_NOT_FOUND": "no downloadable media found", "RATE_LIMITED": "getinsaver rate limited", "API_KEY_INVALID": "getinsaver key invalid",
                      "URL_INVALID": "link not valid for instagram"}

app = FastAPI(title="editor social relay", docs_url=None, redoc_url=None, openapi_url=None)


class Fetch(BaseModel):
    url: str


def _allowed(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    return parts.scheme == "https" and not parts.username and not parts.password and any(host == h or host.endswith("." + h) for h in HOSTS)


def _authorized(supplied: str | None) -> bool:
    expected = os.environ.get("RELAY_SECRET", "")
    return len(expected) >= 32 and isinstance(supplied, str) and hmac.compare_digest(supplied.encode(), expected.encode())


def _instagram(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower().removeprefix("www.").removeprefix("m.")
    return host == "instagram.com" or host.endswith(".instagram.com")


def _service(url: str) -> str:
    path = urllib.parse.urlsplit(url).path.lower()
    return "instagram-highlight" if "/highlights/" in path else "instagram-story" if "/stories/" in path else "instagram"


def _pick_video(payload: dict) -> str | None:
    """The first video link in a GetInSaver answer (``items[].url`` with ``type`` video); a picture or audio item is never taken for it."""
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return None
    for item in payload.get("items") or []:
        link = item.get("url") if isinstance(item, dict) else None
        if isinstance(link, str) and link.startswith("https://") and str(item.get("type") or "").lower() == "video":
            return link
    return None


def _getinsaver(url: str) -> dict:
    request = urllib.request.Request(
        GETINSAVER_URL, method="POST", data=json.dumps({"service": _service(url), "url": url, "max_results": 1}).encode(),
        headers={"authorization": "Bearer " + os.environ["GETINSAVER_API_KEY"], "content-type": "application/json", "accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=130) as response:        # the provider asks for client timeouts of 130 s or more
            return json.loads(response.read(2_000_000).decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read(200_000).decode("utf-8", "replace"))
        except ValueError:
            return {"error": True, "code": f"HTTP_{exc.code}", "message": ""}


def _api_download(url: str, work: Path) -> tuple[Path | None, str]:
    """Instagram through GetInSaver: (file, "") on success, (None, reason) otherwise. Without a key nothing is called."""
    if not os.environ.get("GETINSAVER_API_KEY"):
        return None, ""
    try:
        payload = _getinsaver(url)
        media = _pick_video(payload)
        if not media:
            code = str(payload.get("code") or "")
            return None, GETINSAVER_REASONS.get(code, code or "no video in the answer")
        target = work / "video.mp4"
        size = 0
        with urllib.request.urlopen(urllib.request.Request(media, headers={"user-agent": "Mozilla/5.0"}), timeout=60) as response, open(target, "wb") as out:
            while chunk := response.read(CHUNK):
                size += len(chunk)
                if size > MAX_BYTES:
                    return None, "file larger than max-filesize"
                out.write(chunk)
        return (target, "") if size > 2000 else (None, "empty media")
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        return None, f"download error {type(exc).__name__}"


@app.get("/api/index")
@app.get("/api")
@app.get("/")
def health():
    import yt_dlp
    return {"ok": True, "yt_dlp": yt_dlp.version.__version__, "getinsaver": bool(os.environ.get("GETINSAVER_API_KEY"))}


@app.post("/api/index")
@app.post("/api")
@app.post("/")
def fetch(body: Fetch, x_relay_secret: str | None = Header(default=None)):
    if not _authorized(x_relay_secret):
        raise HTTPException(401, "unauthorized")
    if not _allowed(body.url):
        raise HTTPException(403, "host_not_allowed")
    work = Path(tempfile.mkdtemp(prefix="relay-", dir="/tmp"))
    info: dict = {}
    path, api_reason = _api_download(body.url, work) if _instagram(body.url) else (None, "")
    if path is not None:
        info = {"extractor_key": "getinsaver"}
    else:
        import yt_dlp
        options = {"outtmpl": str(work / "video.%(ext)s"), "quiet": True, "no_warnings": True, "noplaylist": True, "max_filesize": MAX_BYTES,
                   "format": "best[ext=mp4][height<=720]/best[height<=720]/best", "socket_timeout": 25, "retries": 2,
                   "match_filter": yt_dlp.utils.match_filter_func(f"duration <=? {MAX_SECONDS}"), "cachedir": False}
        if os.environ.get("YTDLP_PROXY"):
            options["proxy"] = os.environ["YTDLP_PROXY"]
        cookies = os.environ.get("YTDLP_COOKIES_B64", "")
        if cookies:
            (work / "cookies.txt").write_bytes(base64.b64decode(cookies))
            options["cookiefile"] = str(work / "cookies.txt")
        try:
            with yt_dlp.YoutubeDL(options) as client:
                info = client.extract_info(body.url, download=True) or {}
        except Exception as exc:
            shutil.rmtree(work, ignore_errors=True)
            message = (f"[downloader api] {api_reason}; " if api_reason else "") + str(exc)
            return JSONResponse({"error": "download_failed", "message": message[:500]}, status_code=502)
        files = sorted(p for p in work.glob("video.*") if p.suffix.lower() in {".mp4", ".webm", ".mov", ".mkv", ".m4v"})
        if not files:
            shutil.rmtree(work, ignore_errors=True)
            return JSONResponse({"error": "no_file", "message": "nothing was downloaded (too long, too large, or not a video)"}, status_code=502)
        path = files[0]
    size = path.stat().st_size

    def stream():
        try:
            with open(path, "rb") as handle:
                while chunk := handle.read(CHUNK):
                    yield chunk
        finally:
            shutil.rmtree(work, ignore_errors=True)

    media = {"mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime", "mkv": "video/x-matroska", "m4v": "video/mp4"}
    headers = {"content-length": str(size), "x-source-title": urllib.parse.quote(str(info.get("title") or "")[:200]),
               "x-source-duration": str(info.get("duration") or ""), "x-source-extractor": str(info.get("extractor_key") or ""),
               "x-source-ext": path.suffix.lstrip(".")}
    return StreamingResponse(stream(), media_type=media.get(path.suffix.lstrip(".").lower(), "application/octet-stream"), headers=headers)
