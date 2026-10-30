"""The loopback dev user ("local_dev") must not crash database persistence."""
import asyncio
from pathlib import Path

from app import jobs, style_store


class _FakeSession:
    def __init__(self):
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, model, key):
        return None

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        pass


def _persist(monkeypatch, tmp_path, user_id):
    session = _FakeSession()
    monkeypatch.setattr(jobs, "AsyncSessionLocal", lambda: session)
    job = jobs.Job(id="job-local", dir=tmp_path, user_id=user_id)
    asyncio.run(jobs._persist_job(job))
    return session.added[0]


def test_db_user_id_accepts_only_numeric_ids():
    assert jobs._db_user_id("42") == 42
    assert jobs._db_user_id("local_dev") is None
    assert jobs._db_user_id(None) is None


def test_local_dev_job_is_saved_unowned(monkeypatch, tmp_path):
    assert _persist(monkeypatch, tmp_path, "local_dev").user_id is None


def test_numeric_owner_is_still_saved(monkeypatch, tmp_path):
    assert _persist(monkeypatch, tmp_path, "7").user_id == 7


def test_local_dev_style_profile_uses_files_when_db_is_up(monkeypatch, tmp_path):
    monkeypatch.setattr(style_store, "DB_AVAILABLE", True)
    monkeypatch.setattr(style_store, "LEARNED_PROFILES_DIR", Path(tmp_path))

    def no_db(*_args, **_kwargs):
        raise AssertionError("local_dev must not reach PostgreSQL")

    monkeypatch.setattr(style_store, "AsyncSessionLocal", no_db)
    style_store.save_profile("local_dev", {"pace": "fast"})
    assert style_store.load_profile("local_dev") == {"pace": "fast"}
    style_store.add_reference("local_dev", "abc123", {"source_file": "a.mp4"})
    assert [item["_file"] for item in style_store.list_references("local_dev")] == ["abc123"]
    assert style_store.delete_reference("local_dev", "abc123") is True
    style_store.delete_profile("local_dev")
    assert style_store.load_profile("local_dev") is None
    assert style_store._use_db("12") is True
