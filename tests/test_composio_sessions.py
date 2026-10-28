import asyncio
from contextlib import contextmanager
from types import SimpleNamespace as Obj

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from hermes.routers.connected_apps import router
from hermes.security import current_user
from hermes.services import composio_sessions as service


@pytest.fixture
def setup(monkeypatch):
    rows, calls = {}, []
    monkeypatch.setattr(service.settings, "COMPOSIO_INSTANCE_ID", "test-installation")
    monkeypatch.setattr(service.settings, "COMPOSIO_API_KEY", "private-api-key")
    monkeypatch.setattr(service.settings, "COMPOSIO_TOOLKITS", "instagram")
    monkeypatch.setattr(service.settings, "COMPOSIO_CALLBACK_URL", "https://editor.example/hermes/settings")
    monkeypatch.setattr(service.settings, "HERMES_ENCRYPTION_KEY", "stable-test-key")

    async def get(table, key):
        return rows.get(key)
    async def save(table, row):
        rows[row["id"]] = row
    monkeypatch.setattr(service, "get_row", get)
    monkeypatch.setattr(service, "save_row", save)

    class Session:
        session_id = "session-private-reference"
        def toolkits(self, **kwargs):
            calls.append(("toolkits", kwargs))
            return Obj(items=[Obj(slug="instagram", name="Instagram", connection=None)])
        def authorize(self, toolkit, **kwargs):
            calls.append(("authorize", toolkit, kwargs))
            return Obj(redirect_url="https://connect.composio.dev/authorization")
    class Sessions:
        def create(self, **kwargs):
            calls.append(("create", kwargs))
            return Session()
        def use(self, ref):
            calls.append(("use", ref))
            return Session()
    @contextmanager
    def sdk():
        yield Obj(sessions=Sessions())
    monkeypatch.setattr(service, "sdk", sdk)
    return rows, calls


def test_persistent_session_reused_and_secrets_not_returned(setup):
    rows, calls = setup
    async def scenario():
        await service.set_enabled("1", True)
        await service.connections("1")
        await service.connections("1")
        return await service.status("1")
    result = asyncio.run(scenario())
    assert len([c for c in calls if c[0] == "create"]) == 1
    policy = next(c[1] for c in calls if c[0] == "create")
    assert policy["sandbox"] == {"enable": False}
    assert policy["proxy_execute"] is False
    assert policy["manage_connections"] is False
    assert policy["toolkits"] == {"enable": ["instagram"]}
    assert policy["tags"] == {"enable": ["readOnlyHint"]}
    assert "session-private-reference" not in str(rows)
    assert "private-api-key" not in str(rows) + str(result)
    assert "session_id" not in result
    assert result["external_actions_enabled"] is False


def test_disabled_user_cannot_use_other_users_session(setup):
    async def scenario():
        await service.set_enabled("1", True)
        await service.session_id("1")
        with pytest.raises(HTTPException) as error:
            await service.connections("2")
        assert error.value.status_code == 409
    asyncio.run(scenario())
    assert service.identity("1") != service.identity("2")


def test_unknown_application_is_never_authorized(setup):
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.connect("1", "arbitrary"))
    assert error.value.status_code == 422
    assert not setup[1]


def test_remote_error_is_sanitized_and_not_retried(setup):
    calls = []
    def fail():
        calls.append(True)
        raise RuntimeError("private-api-key session-secret https://secret")
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.remote(fail))
    assert error.value.detail == {"code": "COMPOSIO_CONNECTION_FAILED"}
    assert len(calls) == 1


def test_callback_does_not_mark_connection_successful(setup):
    async def scenario():
        await service.set_enabled("1", True)
        return await service.connect("1", "instagram")
    assert asyncio.run(scenario())["status"] == "AUTHORIZATION_REQUIRED"


def test_authenticated_routes_reject_client_identity_and_arbitrary_actions(setup):
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        assert client.get("/api/hermes/composio").status_code == 401
        app.dependency_overrides[current_user] = lambda: Obj(id=1)
        assert client.put("/api/hermes/composio", json={"enabled": True, "user_id": "2"}).status_code == 422
        assert client.post("/api/hermes/composio/execute", json={"tool": "DELETE"}).status_code == 404
        assert client.get("/api/hermes/composio").json()["external_actions_enabled"] is False


def test_changed_policy_fails_closed(setup, monkeypatch):
    async def scenario():
        await service.set_enabled("1", True)
        await service.session_id("1")
        monkeypatch.setattr(service.settings, "COMPOSIO_TOOLKITS", "")
        with pytest.raises(HTTPException) as error:
            await service.session_id("1")
        assert error.value.status_code == 409
    asyncio.run(scenario())
