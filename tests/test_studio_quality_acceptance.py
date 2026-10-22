import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import studio
from app import talking_reel


def test_accept_existing_output_does_not_render(tmp_path, monkeypatch):
    exports = tmp_path / 'exports'
    exports.mkdir()
    (exports / 'v2.mp4').write_bytes(b'existing-render')
    state = {'status': 'error', 'candidate_output': 'exports/v2.mp4',
             'creative_review': {'status': 'needs_attention', 'findings': ['visible defect']}}
    saved = []
    async def get_project(*args):
        return {'engine': 'talking', 'external_ref': 'job', 'conversation_id': 'chat'}
    async def noop(*args, **kwargs): pass
    monkeypatch.setattr(studio.repo, 'get_project', get_project)
    monkeypatch.setattr(studio.repo, 'add_message', noop)
    monkeypatch.setattr(studio, 'sync_conversation', noop)
    monkeypatch.setattr(studio.jobstore, 'get', lambda _: SimpleNamespace(dir=tmp_path))
    monkeypatch.setattr(talking_reel, 'load', lambda _: dict(state))
    monkeypatch.setattr(talking_reel, 'save', lambda _, value: saved.append(value))
    request = SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id='owner')))
    result = asyncio.run(studio.accept_output(request, 'project', studio.AcceptOutputRequest(candidate='exports/v2.mp4')))
    assert result == {'accepted': True}
    assert saved[0]['output'] == 'exports/v2.mp4'
    assert saved[0]['creative_review']['status'] == 'needs_attention'
    assert saved[0]['quality_accepted_by_user'] is True
    with pytest.raises(HTTPException) as stale:
        asyncio.run(studio.accept_output(request, 'project', studio.AcceptOutputRequest(candidate='exports/v1.mp4')))
    assert stale.value.status_code == 409
    state['status'] = 'running'
    with pytest.raises(HTTPException):
        asyncio.run(studio.accept_output(request, 'project', studio.AcceptOutputRequest(candidate='exports/v2.mp4')))


def test_accept_output_checks_ownership(monkeypatch):
    async def missing(*args): raise KeyError('not owned')
    monkeypatch.setattr(studio.repo, 'get_project', missing)
    request = SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id='other')))
    with pytest.raises(HTTPException) as denied:
        asyncio.run(studio.accept_output(request, 'private', studio.AcceptOutputRequest(candidate='exports/v2.mp4')))
    assert denied.value.status_code == 404
