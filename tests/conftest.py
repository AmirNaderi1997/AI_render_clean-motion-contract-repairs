"""Unit tests never consume live gateway credits or modify existing project state."""
import pytest


@pytest.fixture(autouse=True)
def isolated_ai_gateway(monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, "LMAPI_API_KEY", "")
    monkeypatch.setattr(settings, "LMAPI_API_KEY_FILE", str(tmp_path / "missing-key"))
    monkeypatch.setattr(settings, "JOBS_DIR", str(tmp_path / "jobs"))
