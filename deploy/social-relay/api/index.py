"""Social-media reference fetcher for the editor (runs on Vercel, outside the network that blocks these sites).

POST /api/index  {"url": "https://www.instagram.com/reel/..."}   header x-relay-secret: <RELAY_SECRET>
  -> the video file itself (progressive mp4, <= 80 MB, <= 180 s), streamed; metadata in x-* response headers.
GET  /api/index -> {"ok": true, "yt_dlp": "<version>"}

The secret is required, only a fixed list of hosts is allowed, and nothing is stored: the file lives in /tmp for the length of
one request. Optional environment: YTDLP_COOKIES_B64 (base64 Netscape cookies for networks that need a login) and YTDLP_PROXY.
"""
from __future__ import annotations

import base64
import hmac
import os
import shutil
import tempfile
import urllib.parse
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

HOSTS = {"instagram.com", "youtube.com", "youtu.be", "tiktok.com", "vimeo.com", "x.com", "twitter.com", "facebook.com", "fb.watch"}
MAX_BYTES = 80 * 1024 * 1024
MAX_SECONDS = 180
CHUNK = 1024 * 1024

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


@app.get("/api/index")
@app.get("/api")
@app.get("/")
def health():
    import yt_dlp
    return {"ok": True, "yt_dlp": yt_dlp.version.__version__}


@app.post("/api/index")
@app.post("/api")
@app.post("/")
def fetch(body: Fetch, x_relay_secret: str | None = Header(default=None)):
    if not _authorized(x_relay_secret):
        raise HTTPException(401, "unauthorized")
    if not _allowed(body.url):
        raise HTTPException(403, "host_not_allowed")
    import yt_dlp
    work = Path(tempfile.mkdtemp(prefix="relay-", dir="/tmp"))
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
            info = client.extract_info(body.url, download=True)
    except Exception as exc:
        shutil.rmtree(work, ignore_errors=True)
        return JSONResponse({"error": "download_failed", "message": str(exc)[:500]}, status_code=502)
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
    headers = {"content-length": str(size), "x-source-title": urllib.parse.quote(str((info or {}).get("title") or "")[:200]),
               "x-source-duration": str((info or {}).get("duration") or ""), "x-source-extractor": str((info or {}).get("extractor_key") or ""),
               "x-source-ext": path.suffix.lstrip(".")}
    return StreamingResponse(stream(), media_type=media.get(path.suffix.lstrip(".").lower(), "application/octet-stream"), headers=headers)
