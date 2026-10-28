"""Explicit HTTP smoke test against the isolated preview; no external calls.

Creates one clearly named local verification account. Prints no credentials.
Never run this against production or an existing shared database.
"""
import json
import secrets
import uuid

import httpx


def main():
    origin = "http://127.0.0.1:5187"
    with httpx.Client(base_url=origin, timeout=20, trust_env=False) as client:
        assert client.get("/api/hermes/composio").status_code == 401
        response = client.post("/api/auth/signup", json={
            "email": f"hermes-local-check-{uuid.uuid4().hex[:10]}@example.invalid",
            "name": "Local verification", "password": secrets.token_urlsafe(24)})
        assert response.status_code == 201, f"Signup: {response.status_code}"
        token = response.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        response = client.get("/api/hermes/composio")
        assert response.status_code == 200
        assert not response.json()["external_actions_enabled"]
        assert client.put("/api/hermes/composio", json={"enabled": True}).status_code == 200
        assert client.get("/api/hermes/composio").json()["enabled"] is True
        assert client.put("/api/hermes/composio", json={"enabled": False}).status_code == 200
        checked = client.post("/api/hermes/content-tools/check", json={
            "operation": "beats", "language": "fa", "text": "می‌توانیم بهتر بنویسیم"})
        assert checked.status_code == 200
        assert checked.json()["result"]["total_words"] == 3
        print(json.dumps({"frontend": origin, "signup": "passed", "authenticated_settings": "passed",
                          "settings_persistence": "passed", "persian_content_check": "passed",
                          "external_calls": 0}))


if __name__ == "__main__":
    main()
