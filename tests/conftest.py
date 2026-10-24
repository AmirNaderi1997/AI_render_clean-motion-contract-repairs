"""Unit tests never consume live gateway credits or modify existing project state."""
import pytest


@pytest.fixture(autouse=True)
def isolated_ai_gateway(monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, "LMAPI_API_KEY", "")
    monkeypatch.setattr(settings, "LMAPI_API_KEY_FILE", str(tmp_path / "missing-key"))
    monkeypatch.setattr(settings, "JOBS_DIR", str(tmp_path / "jobs"))


@pytest.fixture(autouse=True)
def isolated_chat_store(monkeypatch, tmp_path):
    """No test may read or write the developer's real chats: the studio store, the long-video and motion-graphic folders all live in tmp for every test."""
    from app import studio_store
    monkeypatch.setattr(studio_store, "ROOT", tmp_path / "studio")
    monkeypatch.setattr(studio_store, "FALLBACK", tmp_path / "studio" / "studio.json")
    for name in ("app.long_video", "app.motion_graphic"):
        try:
            module = __import__(name, fromlist=["ROOT"])
            monkeypatch.setattr(module, "ROOT", tmp_path / "studio")
        except ImportError:
            pass
