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


def test_an_instagram_reel_is_downloaded_through_the_api_and_streamed(env, monkeypatch):
    _answer_and_file(monkeypatch)
    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=lambda o: pytest.fail("yt-dlp must not run when the API worked"), utils=None))
    response = env.post("/api/index", json={"url": REEL}, headers=HEADERS)
    assert response.status_code == 200 and response.headers["x-source-extractor"] == "getinsaver" and len(response.content) == 5000


def test_api_failures_fall_back_to_yt_dlp_and_the_reason_is_reported(env, monkeypatch):
    monkeypatch.setenv("GETINSAVER_API_KEY", KEY)
    monkeypatch.setattr(relay, "_getinsaver", lambda url: {"error": True, "code": "UPSTREAM_REJECTED", "message": "login only"})

    class YDL:
        def __init__(self, options): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download=True): raise RuntimeError("login required")

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=YDL, utils=types.SimpleNamespace(match_filter_func=lambda s: None)))
    response = env.post("/api/index", json={"url": REEL}, headers=HEADERS)
    assert response.status_code == 502 and "private, deleted or login-only content" in response.json()["message"]


def test_when_the_api_has_nothing_yt_dlp_can_still_deliver(env, monkeypatch):
    monkeypatch.setenv("GETINSAVER_API_KEY", KEY)
    monkeypatch.setattr(relay, "_getinsaver", lambda url: {"error": True, "code": "INSUFFICIENT_CREDITS"})

    class YDL:
        def __init__(self, options): self.options = options
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download=True):
            (Path(self.options["outtmpl"]).parent / "video.mp4").write_bytes(b"y" * 3000)
            return {"title": "t", "duration": 9, "extractor_key": "Instagram"}

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=YDL, utils=types.SimpleNamespace(match_filter_func=lambda s: None)))
    response = env.post("/api/index", json={"url": REEL}, headers=HEADERS)
    assert response.status_code == 200 and response.headers["x-source-extractor"] == "Instagram" and len(response.content) == 3000


def test_oversized_files_are_refused_and_other_sites_never_touch_the_api(env, monkeypatch, tmp_path):
    _answer_and_file(monkeypatch)
    monkeypatch.setattr(relay, "MAX_BYTES", 1000)
    assert relay._api_download(REEL, tmp_path) == (None, "file larger than max-filesize")
    calls = []
    monkeypatch.setattr(relay, "_getinsaver", lambda url: calls.append(url) or {})
    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=lambda o: (_ for _ in ()).throw(RuntimeError("no")), utils=types.SimpleNamespace(match_filter_func=lambda s: None)))
    assert env.post("/api/index", json={"url": "https://www.tiktok.com/@a/video/1"}, headers=HEADERS).status_code == 502 and calls == []


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
