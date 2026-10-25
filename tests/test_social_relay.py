"""The Vercel social relay: Instagram through the GetInSaver API (key stays on Vercel), yt-dlp as the fallback."""
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

SPEC = importlib.util.spec_from_file_location("social_relay", Path(__file__).resolve().parents[1] / "deploy/social-relay/api/index.py")
relay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(relay)
SECRET = "s" * 40
HEADERS = {"x-relay-secret": SECRET}
REEL = "https://www.instagram.com/reel/DefB-rxMrmo/"
KEY = "gis_live_" + "k" * 24


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("RELAY_SECRET", SECRET)
    monkeypatch.delenv("GETINSAVER_API_KEY", raising=False)
    return TestClient(relay.app)


ANSWER = {"ok": True, "service": "instagram", "item_count": 2, "items": [{"type": "image", "url": "https://cdn.example/cover.jpg"},
          {"type": "video", "url": "https://cdn.example/media.mp4"}], "metadata": {"author": "creator"}, "credits_used": 1}


def test_the_video_item_is_picked_and_pictures_audio_and_errors_are_not():
    assert relay._pick_video(ANSWER) == "https://cdn.example/media.mp4"
    assert relay._pick_video({"ok": True, "items": [{"type": "image", "url": "https://cdn.example/a.jpg"}, {"type": "audio", "url": "https://cdn.example/a.mp3"}]}) is None
    assert relay._pick_video({"error": True, "code": "UPSTREAM_REJECTED", "message": "private"}) is None
    assert relay._pick_video({"ok": True, "items": [{"type": "video", "url": "http://insecure.example/v.mp4"}]}) is None
    assert relay._pick_video({"ok": True, "items": []}) is None and relay._pick_video("nonsense") is None
    # answers that do not label the item exactly "video" are still understood when the link is clearly a video
    assert relay._pick_video({"items": [{"type": "reel", "url": "https://cdn.example/r"}]}) == "https://cdn.example/r"
    assert relay._pick_video({"items": [{"url": "https://cdn.example/clip.mp4?sig=1"}]}) == "https://cdn.example/clip.mp4?sig=1"
    assert relay._pick_video({"items": [{"url": "https://cdn.example/clip"}]}) is None             # no type and no video extension: not guessed


def test_the_answer_shape_is_reported_without_any_link():
    shape = relay._shape({"ok": True, "items": [{"type": "image", "url": "https://secret.example/x?token=abc"}], "message": "m"})
    assert "image" in shape and "secret.example" not in shape and "token" not in shape


def test_the_service_id_follows_the_kind_of_link():
    assert relay._service(REEL) == "instagram"
    assert relay._service("https://www.instagram.com/stories/neymarjr/3600632588760909700/") == "instagram-story"
    assert relay._service("https://www.instagram.com/stories/highlights/17900000000/") == "instagram-highlight"
    assert relay._instagram(REEL) and relay._instagram("https://instagram.com/p/x/") and not relay._instagram("https://evilinstagram.com/reel/x")


def test_the_request_follows_the_documented_contract(monkeypatch):
    monkeypatch.setenv("GETINSAVER_API_KEY", KEY)
    seen = {}

    class Response:
        def read(self, n): return json.dumps(ANSWER).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def urlopen(request, timeout=0):
        seen.update(url=request.full_url, method=request.get_method(), body=json.loads(request.data), auth=request.get_header("Authorization"), timeout=timeout)
        return Response()

    monkeypatch.setattr(relay.urllib.request, "urlopen", urlopen)
    assert relay._getinsaver(REEL)["ok"] is True
    assert seen["url"] == "https://developers.getinsaver.com/v1/resolve" and seen["method"] == "POST"
    assert seen["body"] == {"service": "instagram", "url": REEL, "max_results": 1} and seen["auth"] == "Bearer " + KEY and seen["timeout"] >= 130


def test_the_provider_is_called_with_a_browser_signature_not_pythons_default(monkeypatch):
    """Regression: Cloudflare answered Python-urllib with 'Error 1010: browser_signature_banned' and the relay saw an answer without any items."""
    monkeypatch.setenv("GETINSAVER_API_KEY", KEY)
    seen = {}

    class Response:
        def read(self, n): return json.dumps(ANSWER).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(relay.urllib.request, "urlopen", lambda request, timeout=0: (seen.update(ua=request.get_header("User-agent")), Response())[1])
    relay._getinsaver(REEL)
    assert seen["ua"].startswith("Mozilla/5.0") and "urllib" not in seen["ua"].lower()


def test_a_cloudflare_refusal_is_reported_as_such(monkeypatch, tmp_path):
    monkeypatch.setenv("GETINSAVER_API_KEY", KEY)
    monkeypatch.setattr(relay, "_getinsaver", lambda url: {"title": "Error 1010: Access denied", "status": 403, "error_code": 1010, "error_name": "browser_signature_banned"})
    media, reason = relay._api_download(REEL, tmp_path)
    assert media is None and "browser_signature_banned" in reason


def test_nothing_is_called_without_a_key(monkeypatch, tmp_path):
    monkeypatch.setattr(relay, "_getinsaver", lambda url: pytest.fail("no key, no call"))
    assert relay._api_download(REEL, tmp_path) == (None, "")


def _answer_and_file(monkeypatch, payload=ANSWER, body=b"x" * 5000):
    monkeypatch.setenv("GETINSAVER_API_KEY", KEY)
    monkeypatch.setattr(relay, "_getinsaver", lambda url: payload)

    class Response:
        def __init__(self): self.left = body
        def read(self, n): out, self.left = self.left[:n], self.left[n:]; return out
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(relay.urllib.request, "urlopen", lambda request, timeout=0: Response())


class YDL:
    """A fake yt-dlp whose behaviour each test chooses."""
    behaviour = "ok"
    seen: list = []

    def __init__(self, options): self.options = options
    def __enter__(self): return self
    def __exit__(self, *a): return False

    def extract_info(self, url, download=True):
        YDL.seen.append((url, self.options.get("cookiefile")))
        YDL.options = self.options
        if YDL.behaviour == "fail":
            raise RuntimeError("login required")
        (Path(self.options["outtmpl"]).parent / "video.mp4").write_bytes(b"y" * 3000)
        return {"title": "t", "duration": 9, "extractor_key": "Instagram"}


@pytest.fixture
def ytdlp(monkeypatch):
    YDL.behaviour, YDL.seen = "ok", []
    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=YDL, utils=types.SimpleNamespace(match_filter_func=lambda s: None),
                                                                 version=types.SimpleNamespace(__version__="9")))
    return YDL


def test_yt_dlp_goes_first_with_the_cookies_and_the_api_is_not_even_called(env, monkeypatch, ytdlp):
    import base64
    monkeypatch.setenv("YTDLP_COOKIES_B64", base64.b64encode(b"# Netscape HTTP Cookie File\n").decode())
    monkeypatch.setenv("GETINSAVER_API_KEY", KEY)
    monkeypatch.setattr(relay, "_getinsaver", lambda url: pytest.fail("the API is only the fallback"))
    response = env.post("/api/index", json={"url": REEL}, headers=HEADERS)
    assert response.status_code == 200 and response.headers["x-source-extractor"] == "Instagram" and len(response.content) == 3000
    assert ytdlp.seen and ytdlp.seen[0][1] is not None                       # the cookie file was handed to yt-dlp


def test_when_yt_dlp_fails_an_instagram_link_falls_back_to_getinsaver(env, monkeypatch, ytdlp):
    ytdlp.behaviour = "fail"
    _answer_and_file(monkeypatch)
    response = env.post("/api/index", json={"url": REEL}, headers=HEADERS)
    assert response.status_code == 200 and response.headers["x-source-extractor"] == "getinsaver" and len(response.content) == 5000


def test_other_sites_never_use_the_api_and_the_error_names_both_attempts_for_instagram(env, monkeypatch, ytdlp):
    ytdlp.behaviour = "fail"
    monkeypatch.setenv("GETINSAVER_API_KEY", KEY)
    calls = []
    monkeypatch.setattr(relay, "_getinsaver", lambda url: calls.append(url) or {"error": True, "code": "UPSTREAM_REJECTED"})
    tiktok = env.post("/api/index", json={"url": "https://www.tiktok.com/@a/video/1"}, headers=HEADERS)
    assert tiktok.status_code == 502 and calls == [] and "[yt-dlp] login required" in tiktok.json()["message"]
    reel = env.post("/api/index", json={"url": REEL}, headers=HEADERS)
    message = reel.json()["message"]
    assert reel.status_code == 502 and "[yt-dlp] login required" in message and "[downloader api] private, deleted or login-only content" in message


def test_a_broken_cookie_variable_is_reported_not_crashed_on(env, monkeypatch, ytdlp):
    monkeypatch.setenv("YTDLP_COOKIES_B64", "***not base64***")
    response = env.post("/api/index", json={"url": "https://www.youtube.com/watch?v=x"}, headers=HEADERS)
    assert response.status_code == 502 and "YTDLP_COOKIES_B64" in response.json()["message"]


def test_oversized_api_files_are_refused(monkeypatch, tmp_path):
    _answer_and_file(monkeypatch)
    monkeypatch.setattr(relay, "MAX_BYTES", 1000)
    assert relay._api_download(REEL, tmp_path) == (None, "file larger than max-filesize")


def test_the_secret_is_still_required_and_the_health_page_never_shows_the_key(env, monkeypatch):
    monkeypatch.setenv("GETINSAVER_API_KEY", KEY)
    assert env.post("/api/index", json={"url": REEL}).status_code == 401
    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(version=types.SimpleNamespace(__version__="9")))
    health = env.get("/api/index").json()
    assert health["getinsaver"] is True and KEY not in str(health)


def test_the_editor_explains_the_api_failure_reasons():
    from creative import reference
    assert "اعتبار" in reference.download_failure_reason("[downloader api] getinsaver credits exhausted; ERROR: x")
    assert "خصوصی" in reference.download_failure_reason("[downloader api] private, deleted or login-only content; ERROR: x")


def test_a_large_reference_is_shrunk_before_the_slow_trip_to_the_editor(monkeypatch, tmp_path):
    big = tmp_path / "video.mp4"
    big.write_bytes(b"x" * 3_000_000)
    seen = {}

    def run(command, **kw):
        seen["command"] = command
        Path(command[-1]).write_bytes(b"s" * 400_000)
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(relay, "_ffmpeg", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(relay.subprocess, "run", run)
    small = relay._shrink(big)
    assert small.name == "small.mp4" and small.stat().st_size == 400_000
    assert "-t" in seen["command"] and str(relay.SHRINK_SECONDS) in seen["command"] and "min(480,ih)" in " ".join(seen["command"])


def test_the_original_is_sent_when_shrinking_is_impossible_or_pointless(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * 3_000_000)
    monkeypatch.setattr(relay, "_ffmpeg", lambda: None)
    assert relay._shrink(video) == video
    monkeypatch.setattr(relay, "_ffmpeg", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(relay.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(relay.subprocess.SubprocessError("boom")))
    assert relay._shrink(video) == video
    tiny = tmp_path / "t.mp4"
    tiny.write_bytes(b"x" * 1000)
    assert relay._shrink(tiny) == tiny
    monkeypatch.setattr(relay.subprocess, "run", lambda c, **k: Path(c[-1]).write_bytes(b"y" * 9_000_000) or types.SimpleNamespace())
    assert relay._shrink(video) == video                 # a copy that is not smaller is not used


def test_yt_dlp_is_given_a_javascript_runtime_for_youtube(env, monkeypatch, ytdlp):
    monkeypatch.setattr(relay, "_node", lambda: "/opt/node/bin/node")
    assert env.post("/api/index", json={"url": "https://www.youtube.com/watch?v=x"}, headers=HEADERS).status_code == 200
    assert ytdlp.options["js_runtimes"] == {"node": {"path": "/opt/node/bin/node"}}


def test_without_a_runtime_yt_dlp_still_runs_and_health_says_so(env, monkeypatch, ytdlp):
    monkeypatch.setattr(relay, "_node", lambda: None)
    assert env.post("/api/index", json={"url": "https://www.youtube.com/watch?v=x"}, headers=HEADERS).status_code == 200
    assert "js_runtimes" not in ytdlp.options
    health = env.get("/api/index").json()
    assert health["js_runtime"] is False and health["cookies"] is False


def test_the_node_binary_from_the_wheel_is_found_and_made_executable(monkeypatch, tmp_path):
    monkeypatch.setattr(relay.shutil, "which", lambda name: None)
    package = tmp_path / "nodejs_wheel"
    (package / "bin").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "bin" / "node").write_text("#!/bin/sh\n")
    (package / "bin" / "node").chmod(0o644)                 # a read-only bundle without the executable bit
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "nodejs_wheel", raising=False)
    copies = []
    monkeypatch.setattr(relay.shutil, "copy2", lambda a, b: copies.append((str(a), str(b))))
    monkeypatch.setattr(relay.Path, "chmod", lambda self, mode: None)
    monkeypatch.setattr(relay.Path, "is_file", lambda self: self.name == "node" and "nodejs_wheel" in str(self))
    assert relay._node() == "/tmp/node-runtime" and copies and copies[0][1] == "/tmp/node-runtime"


class _Upstream:
    def __init__(self, body=b"<html>ok</html>", status=200, ctype="text/html; charset=utf-8", headers=None):
        self.status, self.code, self.body = status, status, body
        self.headers = types.SimpleNamespace(get=lambda k, d=None: {"Content-Type": ctype, **(headers or {})}.get(k, d))
    def read(self, n=-1): return self.body[:n]


def test_page_mode_needs_the_secret_and_a_public_address(env, monkeypatch):
    assert env.post("/api/index", json={"url": "https://store.example/p", "mode": "page"}).status_code == 401
    monkeypatch.setattr(relay, "_public_host", lambda url: False)
    assert env.post("/api/index", json={"url": "http://10.0.0.1/", "mode": "page"}, headers=HEADERS).status_code == 403


def test_page_mode_returns_the_page_with_its_final_address_and_status(env, monkeypatch):
    seen = []
    monkeypatch.setattr(relay, "_public_host", lambda url: seen.append(url) or True)

    class Opener:
        calls = 0
        def open(self, request, timeout=0):
            Opener.calls += 1
            if Opener.calls == 1:
                raise relay.urllib.error.HTTPError(request.full_url, 302, "found", types.SimpleNamespace(get=lambda k, d=None: "/final" if k == "Location" else d), None)
            return _Upstream(b"<h1>Hello</h1>")
    monkeypatch.setattr(relay.urllib.request, "build_opener", lambda *a: Opener())
    response = env.post("/api/index", json={"url": "https://store.example/start", "mode": "page"}, headers=HEADERS)
    assert response.status_code == 200 and response.content == b"<h1>Hello</h1>"
    assert response.headers["x-final-url"] == "https://store.example/final" and response.headers["x-upstream-status"] == "200"
    assert seen == ["https://store.example/start", "https://store.example/final"]          # every hop was checked


def test_the_editor_falls_back_to_the_relay_when_its_own_network_cannot_reach_the_host(monkeypatch):
    from app import studio_url
    monkeypatch.setenv("SOCIAL_RELAY_URL", "https://relay.example/api/index")
    monkeypatch.setenv("SOCIAL_RELAY_SECRET", SECRET)
    monkeypatch.setattr(studio_url, "_public_url", lambda url: url)
    studio_url._DIRECT_FAILED.clear()
    import http.client

    def direct(*a, **k): raise http.client.RemoteDisconnected("closed")
    monkeypatch.setattr(studio_url, "_fetch_direct", direct)
    sent = {}

    class Client:
        def __init__(self, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, json, headers):
            sent.update(url=url, json=json, headers=headers)
            return types.SimpleNamespace(status_code=200, content=b"<html>page</html>", headers={"x-upstream-status": "200", "x-final-url": "https://store.example/p", "content-type": "text/html; charset=utf-8"})
    import httpx
    monkeypatch.setattr(httpx, "Client", Client)
    data, final, ctype = studio_url._fetch("https://store.example/p", max_bytes=1000, accept="text/html")
    assert (data, final, ctype) == (b"<html>page</html>", "https://store.example/p", "text/html")
    assert sent["json"] == {"url": "https://store.example/p", "mode": "page"} and sent["headers"]["x-relay-secret"] == SECRET
    calls = []
    monkeypatch.setattr(studio_url, "_fetch_direct", lambda *a, **k: calls.append(1))
    studio_url._fetch("https://store.example/img.png", max_bytes=1000, accept="image/*")
    assert calls == []                                                                           # the host just failed: straight to the relay


def test_without_a_relay_the_direct_error_is_kept(monkeypatch):
    from app import studio_url
    monkeypatch.delenv("SOCIAL_RELAY_URL", raising=False)
    import http.client

    def direct(*a, **k): raise http.client.RemoteDisconnected("closed")
    monkeypatch.setattr(studio_url, "_fetch_direct", direct)
    with pytest.raises(http.client.RemoteDisconnected):
        studio_url._fetch("https://store.example/p", max_bytes=1000, accept="text/html")


def test_relayed_scripts_are_kept_so_only_the_first_reading_pays_for_them(monkeypatch, tmp_path):
    from app import studio_url
    monkeypatch.setenv("SOCIAL_RELAY_URL", "https://relay.example/api/index")
    monkeypatch.setenv("SOCIAL_RELAY_SECRET", SECRET)
    monkeypatch.setattr(studio_url, "_public_url", lambda url: url)
    monkeypatch.setattr(studio_url, "_static_cache_path", lambda url: tmp_path / "script.bin")
    studio_url._DIRECT_FAILED.clear()
    calls = []
    body = b"x" * 30_000

    class Client:
        def __init__(self, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, json, headers):
            calls.append(json["url"])
            return types.SimpleNamespace(status_code=200, content=body, headers={"x-upstream-status": "200", "x-final-url": json["url"], "content-type": "application/javascript"})
    import httpx
    monkeypatch.setattr(httpx, "Client", Client)
    first = studio_url._relay_fetch("https://store.example/assets/app-1a2b.js", max_bytes=10**7, accept="*/*", allow_http_error=False, with_status=True)
    second = studio_url._relay_fetch("https://store.example/assets/app-1a2b.js", max_bytes=10**7, accept="*/*", allow_http_error=False, with_status=True)
    assert first == second == (body, "https://store.example/assets/app-1a2b.js", "application/javascript", 200) and len(calls) == 1


def test_a_page_that_needs_a_browser_is_rendered_by_the_relay_when_the_host_is_unreachable(monkeypatch, tmp_path):
    import base64
    from app import studio_url, public_page_browser as ppb
    monkeypatch.setenv("SOCIAL_RELAY_URL", "https://relay.example/api/index")
    monkeypatch.setenv("SOCIAL_RELAY_SECRET", SECRET)
    monkeypatch.setattr(studio_url, "_public_url", lambda url: url)
    studio_url._DIRECT_FAILED["store.example"] = __import__("time").monotonic() + 100
    monkeypatch.setattr(ppb, "render_page", lambda *a, **k: pytest.fail("the local browser must not wait for an unreachable host"))
    assert ppb.relay_render_url() == "https://relay.example/api/render"
    sent = {}

    class Client:
        def __init__(self, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, json, headers):
            sent.update(url=url, json=json, headers=headers)
            return types.SimpleNamespace(status_code=200, json=lambda: {"title": "Product", "content": "Name\nPrice", "description": "d",
                                         "images": [{"url": "https://store.example/a.jpg", "alt": "a"}, {"url": ""}],
                                         "screenshots": [{"y": 0, "full_page": True, "body": base64.b64encode(b"jpegbytes").decode()}]})
    import httpx
    monkeypatch.setattr(httpx, "Client", Client)
    result = studio_url._render("https://store.example/p/1", tmp_path)
    assert sent["url"] == "https://relay.example/api/render" and sent["headers"]["x-relay-secret"] == SECRET
    assert result["title"] == "Product" and result["images"] == [{"url": "https://store.example/a.jpg", "alt": "a"}]
    assert Path(result["screenshots"][0]["file"]).read_bytes() == b"jpegbytes" and result["screenshots"][0]["full_page"] is True


def test_a_local_browser_failure_falls_back_to_the_relay_browser(monkeypatch, tmp_path):
    from app import studio_url, public_page_browser as ppb
    monkeypatch.setenv("SOCIAL_RELAY_URL", "https://relay.example/api/index")
    monkeypatch.setenv("SOCIAL_RELAY_SECRET", SECRET)
    studio_url._DIRECT_FAILED.clear()
    monkeypatch.setattr(ppb, "render_page", lambda *a, **k: (_ for _ in ()).throw(ValueError("page.goto: Timeout")))
    monkeypatch.setattr(ppb, "render_page_via_relay", lambda url, out: {"title": "from relay", "content": "", "images": [], "screenshots": []})
    assert studio_url._render("https://store.example/p", tmp_path)["title"] == "from relay"
    monkeypatch.delenv("SOCIAL_RELAY_URL")
    with pytest.raises(ValueError):
        studio_url._render("https://store.example/p", tmp_path)
