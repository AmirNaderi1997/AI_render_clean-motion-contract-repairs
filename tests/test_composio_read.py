import asyncio
from contextlib import contextmanager
from types import SimpleNamespace as Obj

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from hermes.routers.connected_apps import router
from hermes.security import current_user
from hermes.services import composio_read as reads, composio_sessions as sessions


@pytest.fixture
def backend(monkeypatch):
    calls = []
    tool = Obj(slug="INSTAGRAM_TEST_READ", toolkit=Obj(slug="instagram"), tags=["readOnlyHint"],
               is_deprecated=False, input_parameters={"type": "object", "additionalProperties": False,
                    "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "required": ["limit"]})
    response = Obj(result_type="completed", data={"name": "Result", "access_token": "private-token",
        "nested": {"authorization": "private-auth", "text": "server-key"}})
    monkeypatch.setattr(reads.settings, "COMPOSIO_TOOLKITS", "instagram")
    monkeypatch.setattr(reads.settings, "COMPOSIO_READ_TOOLS", tool.slug)
    monkeypatch.setattr(reads.settings, "COMPOSIO_API_KEY", "server-key")
    async def session_id(user):
        calls.append(("identity", user))
        if user != "1":
            raise HTTPException(409, detail={"code": "COMPOSIO_DISABLED"})
        return "owned-session"
    monkeypatch.setattr(sessions, "session_id", session_id)

    def retrieve(slug):
        calls.append(("metadata", slug))
        return tool
    class Session:
        def execute(self, slug, **kwargs):
            calls.append(("execute", slug, kwargs))
            return response
    class Sessions:
        def use(self, reference):
            calls.append(("session", reference))
            assert reference == "owned-session"
            return Session()
    @contextmanager
    def sdk():
        yield Obj(tools=Obj(get_raw_composio_tool_by_slug=retrieve), sessions=Sessions())
    monkeypatch.setattr(sessions, "sdk", sdk)
    return tool, response, calls


def run(arguments=None, user="1"):
    return asyncio.run(reads.execute(user, "instagram", "INSTAGRAM_TEST_READ", arguments if arguments is not None else {"limit": 5}))


def test_valid_read_executes_once_in_owned_session_and_redacts_secrets(backend):
    result = run()
    assert result["status"] == "completed"
    assert "private-token" not in str(result) and "server-key" not in str(result)
    assert ("identity", "1") in backend[2]
    assert len([call for call in backend[2] if call[0] == "execute"]) == 1


@pytest.mark.parametrize("tags", [[], ["createHint"], ["readOnlyHint", "destructiveHint"], ["readOnlyHint", "updateHint"]])
def test_backend_rejects_missing_or_conflicting_read_metadata_even_if_admin_listed(backend, tags):
    backend[0].tags = tags
    with pytest.raises(HTTPException) as error:
        run()
    assert error.value.status_code == 403
    assert not any(call[0] == "execute" for call in backend[2])


def test_admin_allowlist_empty_means_no_execution(backend, monkeypatch):
    monkeypatch.setattr(reads.settings, "COMPOSIO_READ_TOOLS", "")
    with pytest.raises(HTTPException) as error:
        run()
    assert error.value.status_code == 403
    assert backend[2] == []


@pytest.mark.parametrize("arguments", [{"limit": 100}, {"limit": "five"}, {"limit": 2, "account": "other"}, {"data": "x" * 20001}])
def test_invalid_arguments_never_execute(backend, arguments):
    with pytest.raises(HTTPException) as error:
        run(arguments)
    assert error.value.status_code == 422
    assert not any(call[0] == "execute" for call in backend[2])


def test_remote_schema_refs_are_rejected_without_fetching(backend):
    backend[0].input_parameters = {"$ref": "http://127.0.0.1/private"}
    with pytest.raises(HTTPException) as error:
        run()
    assert error.value.status_code == 422
    assert not any(call[0] == "execute" for call in backend[2])


def test_unknown_user_cannot_reuse_connection(backend):
    with pytest.raises(HTTPException) as error:
        run(user="2")
    assert error.value.status_code == 409
    assert backend[2] == [("identity", "2")]


@pytest.mark.parametrize("result_type", ["failed", "blocked"])
def test_unsuccessful_execution_not_reported_as_success_or_retried(backend, result_type):
    backend[1].result_type = result_type
    with pytest.raises(HTTPException) as error:
        run()
    assert error.value.detail["code"] == "COMPOSIO_READ_FAILED"
    assert len([call for call in backend[2] if call[0] == "execute"]) == 1


def test_read_route_uses_authenticated_identity_and_forbids_identity_override(backend):
    app = FastAPI()
    app.include_router(router)
    body = {"application": "instagram", "tool": "INSTAGRAM_TEST_READ", "arguments": {"limit": 1}}
    with TestClient(app) as client:
        assert client.post("/api/hermes/composio/read", json=body).status_code == 401
        app.dependency_overrides[current_user] = lambda: Obj(id=1)
        assert client.post("/api/hermes/composio/read", json={**body, "user_id": "2"}).status_code == 422
        assert client.post("/api/hermes/composio/read", json={**body, "approved": True}).status_code == 422
        assert client.post("/api/hermes/composio/read", json=body).status_code == 200
