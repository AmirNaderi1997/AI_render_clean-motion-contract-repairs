import importlib.util
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from hermes.routers.content_tools import router
from hermes.security import current_user

path = Path(__file__).parents[1] / "integrations/hermes/editor-instagram-tools/__init__.py"
spec = importlib.util.spec_from_file_location("instagram_bridge", path)
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


def args():
    return {"operation": "beats", "language": "fa", "text": "می‌توانیم بهتر بنویسیم"}


def test_authenticated_api_runs_real_check_and_rejects_extra_authority():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        assert client.post("/api/hermes/content-tools/check", json=args()).status_code == 401
        app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=1)
        response = client.post("/api/hermes/content-tools/check", json=args())
        assert response.status_code == 200
        assert response.json()["result"]["total_words"] == 3
        assert client.post("/api/hermes/content-tools/check", json={**args(), "user_id": "2"}).status_code == 422
        unsupported = {**args(), "operation": "audit_text"}
        assert client.post("/api/hermes/content-tools/check", json=unsupported).status_code == 422


def test_plugin_uses_current_profile_credentials_each_call(monkeypatch):
    profile = {"EDITORGPT_API_ORIGIN": "https://editor.example", "EDITORGPT_ACCESS_TOKEN": "alice-secret"}
    monkeypatch.setattr(plugin, "_secret", profile.get)
    requests = []
    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            return BytesIO(json.dumps({"result": {"words": 3}, "disclaimer": "heuristics"}).encode())
    monkeypatch.setattr(plugin, "build_opener", lambda *a: Opener())
    assert json.loads(plugin.check(args()))["result"]["words"] == 3
    profile["EDITORGPT_ACCESS_TOKEN"] = "bob-secret"
    plugin.check(args())
    assert requests[0].get_header("Authorization") == "Bearer alice-secret"
    assert requests[1].get_header("Authorization") == "Bearer bob-secret"
    assert requests[0].full_url == "https://editor.example/api/hermes/content-tools/check"
    assert "secret" not in plugin.check(args())


@pytest.mark.parametrize("origin", ["http://public.example", "https://evil@editor.example", "https://editor.example/path", "https://editor.example?token=x"])
def test_plugin_rejects_unsafe_origin_before_network(monkeypatch, origin):
    monkeypatch.setattr(plugin, "_secret", {"EDITORGPT_API_ORIGIN": origin, "EDITORGPT_ACCESS_TOKEN": "secret"}.get)
    monkeypatch.setattr(plugin, "build_opener", lambda *a: pytest.fail("network called"))
    assert json.loads(plugin.check(args()))["error"] == "EDITORGPT_PROFILE_CONNECTION_REQUIRED"


def test_plugin_does_not_forward_identity_or_leak_failure_details(monkeypatch):
    monkeypatch.setattr(plugin, "_secret", {"EDITORGPT_API_ORIGIN": "http://127.0.0.1:8001", "EDITORGPT_ACCESS_TOKEN": "secret"}.get)
    calls = []
    class Opener:
        def open(self, *a, **kw):
            calls.append(True)
            raise HTTPError("https://secret", 401, "private-secret", {}, None)
    monkeypatch.setattr(plugin, "build_opener", lambda *a: Opener())
    assert json.loads(plugin.check({**args(), "user_id": "bob"}))["error"] == "INVALID_ARGUMENTS"
    assert calls == []
    result = plugin.check(args())
    assert json.loads(result)["error"] == "EDITORGPT_AUTH_EXPIRED"
    assert "secret" not in result and len(calls) == 1


def test_native_registration_contract():
    registrations = []
    plugin.register(SimpleNamespace(register_tool=lambda **kwargs: registrations.append(kwargs)))
    assert registrations[0]["name"] == "editorgpt_instagram_check"
    assert registrations[0]["handler"] is plugin.check
    assert "user_id" not in registrations[0]["schema"]["parameters"]["properties"]
