"""Social-media reference fetcher for the editor (runs on Vercel, outside the network that blocks these sites).

POST /api/index  {"url": "https://www.instagram.com/reel/..."}   header x-relay-secret: <RELAY_SECRET>
  yt-dlp always goes first, with the logged-in cookies from YTDLP_COOKIES_B64 (Instagram and YouTube refuse datacenter IPs without a login).
  For Instagram links (posts, reels, stories, highlights) the GetInSaver API is the fallback when GETINSAVER_API_KEY is set.
  -> the video file itself (progressive mp4, <= 80 MB, <= 180 s), streamed; metadata in x-* response headers.
GET  /api/index -> {"ok": true, "yt_dlp": "<version>"}

The secret is required, only a fixed list of hosts is allowed, and nothing is stored: the file lives in /tmp for the length of
one request. Optional environment: YTDLP_COOKIES_B64 (base64 Netscape cookies for Instagram/YouTube), YTDLP_PROXY and, for the Instagram fallback,
GETINSAVER_API_KEY (the key stays on Vercel and never reaches the editor).
"""
from __future__ import annotations

import base64
import hmac
import os
import shutil
import subprocess
import json
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

HOSTS = {"instagram.com", "youtube.com", "youtu.be", "tiktok.com", "vimeo.com", "x.com", "twitter.com", "facebook.com", "fb.watch"}
MAX_BYTES = 80 * 1024 * 1024
# The editor's server downloads from here at roughly 20 KB/s (Iran), so a reference is sent as a small proxy copy: at most 45 s, 480p, a few MB.
SHRINK_SECONDS = 45
SHRINK_MIN_BYTES = 1_500_000
MAX_SECONDS = 180
CHUNK = 1024 * 1024

GETINSAVER_URL = "https://developers.getinsaver.com/v1/resolve"
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
# Failure codes of the API, as the editor should report them (the editor maps these words to a plain explanation).
GETINSAVER_REASONS = {"INSUFFICIENT_CREDITS": "getinsaver credits exhausted", "UPSTREAM_REJECTED": "private, deleted or login-only content",
                      "MEDIA_NOT_FOUND": "no downloadable media found", "RATE_LIMITED": "getinsaver rate limited", "API_KEY_INVALID": "getinsaver key invalid",
                      "URL_INVALID": "link not valid for instagram"}

app = FastAPI(title="editor social relay", docs_url=None, redoc_url=None, openapi_url=None)


class Fetch(BaseModel):
    url: str
    mode: str = "video"          # "page": fetch one public page or file for the editor (its own network cannot reach some hosts)


def _allowed(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    return parts.scheme == "https" and not parts.username and not parts.password and any(host == h or host.endswith("." + h) for h in HOSTS)


def _authorized(supplied: str | None) -> bool:
    expected = os.environ.get("RELAY_SECRET", "")
    return len(expected) >= 32 and isinstance(supplied, str) and hmac.compare_digest(supplied.encode(), expected.encode())


def _ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def _shrink(path: Path) -> Path:
    """A small copy for the trip to the editor (the original when ffmpeg is missing, the file is already small, or the copy would not be smaller)."""
    exe = _ffmpeg()
    if not exe or path.stat().st_size < SHRINK_MIN_BYTES:
        return path
    out = path.with_name("small.mp4")
    command = [exe, "-y", "-v", "error", "-i", str(path), "-t", str(SHRINK_SECONDS), "-vf", "scale=-2:'min(480,ih)',fps=24", "-c:v", "libx264",
               "-preset", "veryfast", "-crf", "32", "-c:a", "aac", "-b:a", "32k", "-ac", "1", "-movflags", "+faststart", str(out)]
    try:
        subprocess.run(command, capture_output=True, timeout=120, check=True)
    except (subprocess.SubprocessError, OSError):
        return path
    return out if out.is_file() and 0 < out.stat().st_size < path.stat().st_size else path


def _node() -> str | None:
    """A Node.js binary for yt-dlp's YouTube challenge solver (YouTube returns no video formats without a JS runtime). Vercel's Python runtime has
    none, so one ships in the ``nodejs-wheel-binaries`` package; it is copied to /tmp and made executable when the bundle is read-only."""
    found = shutil.which("node")
    if found:
        return found
    try:
        import nodejs_wheel
        root = Path(nodejs_wheel.__file__).resolve().parent
        candidate = next((c for c in [root / "bin" / "node", root / "node", *root.rglob("node")] if c.is_file()), None)
        if candidate is None:
            return None
        if os.access(candidate, os.X_OK):
            return str(candidate)
        target = Path("/tmp/node-runtime")
        if not target.is_file():
            shutil.copy2(candidate, target)
            target.chmod(0o755)
        return str(target)
    except Exception:
        return None


def _ytdlp_download(url: str, work: Path) -> tuple[Path | None, dict, str]:
    """yt-dlp with the cookies from YTDLP_COOKIES_B64 (Instagram and YouTube need a logged-in session from a datacenter IP). (file, info, "") or (None, {}, reason)."""
    import yt_dlp
    options = {"outtmpl": str(work / "video.%(ext)s"), "quiet": True, "no_warnings": True, "noplaylist": True, "max_filesize": MAX_BYTES,
               "format": "best[ext=mp4][height<=720]/best[height<=720]/best", "socket_timeout": 25, "retries": 2,
               "match_filter": yt_dlp.utils.match_filter_func(f"duration <=? {MAX_SECONDS}"), "cachedir": False}
    if os.environ.get("YTDLP_PROXY"):
        options["proxy"] = os.environ["YTDLP_PROXY"]
    node = _node()
    if node:
        options["js_runtimes"] = {"node": {"path": node}}
    cookies = os.environ.get("YTDLP_COOKIES_B64", "")
    if cookies:
        try:
            (work / "cookies.txt").write_bytes(base64.b64decode(cookies))
            options["cookiefile"] = str(work / "cookies.txt")
        except ValueError:
            return None, {}, "YTDLP_COOKIES_B64 is not valid base64"
    try:
        with yt_dlp.YoutubeDL(options) as client:
            info = client.extract_info(url, download=True) or {}
    except Exception as exc:
        return None, {}, str(exc)[:400]
    files = sorted(p for p in work.glob("video.*") if p.suffix.lower() in {".mp4", ".webm", ".mov", ".mkv", ".m4v"})
    if not files:
        return None, {}, "nothing was downloaded (too long, too large, or not a video)"
    return files[0], info, ""


def _instagram(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower().removeprefix("www.").removeprefix("m.")
    return host == "instagram.com" or host.endswith(".instagram.com")


def _service(url: str) -> str:
    path = urllib.parse.urlsplit(url).path.lower()
    return "instagram-highlight" if "/highlights/" in path else "instagram-story" if "/stories/" in path else "instagram"


def _pick_video(payload: dict) -> str | None:
    """The first video link in a GetInSaver answer (``items[].url``). A picture or audio item is never taken for the video; an item without a
    clear type counts only when its link looks like a video file."""
    if not isinstance(payload, dict) or payload.get("error") is True:
        return None
    for item in payload.get("items") or []:
        link = item.get("url") if isinstance(item, dict) else None
        if not (isinstance(link, str) and link.startswith("https://")):
            continue
        kind = str(item.get("type") or "").lower()
        path = link.lower().split("?")[0]
        if kind in {"image", "photo", "audio", "music"} or path.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".mp3", ".m4a")):
            continue
        if "video" in kind or kind in {"reel", "mp4", "clip"} or path.endswith((".mp4", ".mov", ".m4v", ".webm")):
            return link
    return None


def _shape(payload) -> str:
    """What the API answered, without any link or token: enough to see why no video was found."""
    if not isinstance(payload, dict):
        return type(payload).__name__
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    kinds = [str((i or {}).get("type") if isinstance(i, dict) else type(i).__name__) for i in items][:5]
    edge = f" edge={payload.get('error_name') or payload.get('error_code')}" if payload.get("error_code") or payload.get("error_name") else ""
    return f"ok={payload.get('ok')} code={payload.get('code')} items={kinds} message={str(payload.get('message') or payload.get('detail') or '')[:80]}{edge}"


def _getinsaver(url: str) -> dict:
    request = urllib.request.Request(
        GETINSAVER_URL, method="POST", data=json.dumps({"service": _service(url), "url": url, "max_results": 1}).encode(),
        headers={"authorization": "Bearer " + os.environ["GETINSAVER_API_KEY"], "content-type": "application/json", "accept": "application/json",
                 # The provider sits behind Cloudflare, which refuses Python's default signature ("Error 1010: browser_signature_banned").
                 "user-agent": BROWSER_UA})
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
            edge = payload.get("error_name") or payload.get("error_code")
            if not code and edge:
                code = f"EDGE_{edge}"                     # the provider's Cloudflare refused the request before the API saw it
            return None, GETINSAVER_REASONS.get(code) or (f"{code}: {_shape(payload)}" if code else f"no video in the answer ({_shape(payload)})")
        target = work / "video.mp4"
        size = 0
        with urllib.request.urlopen(urllib.request.Request(media, headers={"user-agent": BROWSER_UA}), timeout=60) as response, open(target, "wb") as out:
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
    return {"ok": True, "yt_dlp": yt_dlp.version.__version__, "getinsaver": bool(os.environ.get("GETINSAVER_API_KEY")), "js_runtime": bool(_node()),
            "cookies": bool(os.environ.get("YTDLP_COOKIES_B64"))}


PAGE_MAX = 12 * 1024 * 1024


def _public_host(url: str) -> bool:
    import ipaddress
    import socket
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        return False
    try:
        addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror:
        return False
    return bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)


class _Stay(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # redirects are followed by hand so every hop is checked
        return None


def _page(url: str, accept: str):
    """GET one public resource (redirects checked hop by hop, size capped) and send it back with its final address and status in headers."""
    opener = urllib.request.build_opener(_Stay)
    current = url
    for _ in range(6):
        if not _public_host(current):
            raise HTTPException(403, "host_not_allowed")
        request = urllib.request.Request(current, headers={"User-Agent": BROWSER_UA, "Accept": accept, "Accept-Language": "fa,en;q=0.8"})
        try:
            response = opener.open(request, timeout=25)
        except urllib.error.HTTPError as exc:
            target = exc.headers.get("Location") if exc.headers is not None else None
            if exc.code in {301, 302, 303, 307, 308} and target:
                current = urllib.parse.urljoin(current, target)
                continue
            response = exc
        except (urllib.error.URLError, OSError) as exc:
            raise HTTPException(502, f"fetch_failed: {type(exc).__name__}")
        data = response.read(PAGE_MAX + 1)
        if len(data) > PAGE_MAX:
            raise HTTPException(413, "too_large")
        status = int(getattr(response, "status", None) or getattr(response, "code", 200) or 200)
        return Response(content=data, media_type=response.headers.get("Content-Type", "application/octet-stream"),
                        headers={"x-final-url": urllib.parse.quote(current, safe=":/?&=%#@+,;~"), "x-upstream-status": str(status)})
    raise HTTPException(502, "too_many_redirects")


@app.post("/api/index")
@app.post("/api")
@app.post("/")
def fetch(body: Fetch, x_relay_secret: str | None = Header(default=None), x_relay_accept: str | None = Header(default=None)):
    if not _authorized(x_relay_secret):
        raise HTTPException(401, "unauthorized")
    if body.mode == "page":
        return _page(body.url, x_relay_accept or "text/html,application/xhtml+xml,*/*;q=0.8")
    if not _allowed(body.url):
        raise HTTPException(403, "host_not_allowed")
    work = Path(tempfile.mkdtemp(prefix="relay-", dir="/tmp"))
    # yt-dlp (with the logged-in cookies on Vercel) is always tried first; for Instagram the GetInSaver API is the fallback.
    path, info, ytdlp_error = _ytdlp_download(body.url, work)
    api_reason = ""
    if path is None and _instagram(body.url):
        path, api_reason = _api_download(body.url, work)
        if path is not None:
            info = {"extractor_key": "getinsaver"}
    if path is None:
        shutil.rmtree(work, ignore_errors=True)
        message = f"[yt-dlp] {ytdlp_error}" + (f"; [downloader api] {api_reason}" if api_reason else "")
        code = "no_file" if ytdlp_error.startswith("nothing was downloaded") else "download_failed"
        return JSONResponse({"error": code, "message": message[:600]}, status_code=502)
    original = path.stat().st_size
    path = _shrink(path)
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
               "x-source-ext": path.suffix.lstrip("."), "x-source-original-bytes": str(original)}
    return StreamingResponse(stream(), media_type=media.get(path.suffix.lstrip(".").lower(), "application/octet-stream"), headers=headers)
