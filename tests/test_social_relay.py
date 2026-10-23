import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("yt_dlp")
from fastapi.testclient import TestClient

SPEC = importlib.util.spec_from_file_location("social_relay", Path(__file__).parents[1] / "deploy" / "social-relay" / "api" / "index.py")
relay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(relay)
SECRET = "k" * 40


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("RELAY_SECRET", SECRET)
    return TestClient(relay.app)


def test_health_is_open_and_fetch_needs_the_secret(client):
    assert client.get("/api/index").json()["ok"] is True
    assert client.post("/api/index", json={"url": "https://www.tiktok.com/@a/video/1"}).status_code == 401
    assert client.post("/api/index", json={"url": "https://www.tiktok.com/@a/video/1"}, headers={"x-relay-secret": "wrong" * 10}).status_code == 401


def test_only_social_hosts_over_https_are_fetched(client):
    for url in ("https://evil.example/x.mp4", "http://www.instagram.com/reel/a/", "https://user:pw@www.youtube.com/watch?v=1",
                "https://instagram.com.evil.example/reel/a/", "file:///etc/passwd"):
        assert client.post("/api/index", json={"url": url}, headers={"x-relay-secret": SECRET}).status_code == 403, url


def test_a_short_or_missing_server_secret_never_authorises(monkeypatch):
    monkeypatch.setenv("RELAY_SECRET", "short")
    assert not relay._authorized("short") and not relay._authorized(None)
