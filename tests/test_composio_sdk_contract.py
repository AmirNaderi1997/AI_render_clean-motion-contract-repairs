"""Real optional SDK, fake HTTP transport: no credentials or live API calls."""
import json

import httpx
import pytest


def test_current_sdk_accepts_restricted_session_policy_without_live_network():
    composio = pytest.importorskip("composio")
    requests = []
    def handler(request):
        requests.append(request)
        # Deliberately stop at the server boundary; no fake connected state.
        return httpx.Response(400, json={"message": "contract-test-stop"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        sdk = composio.Composio(api_key="test-only", http_client=transport,
            timeout=20, max_retries=0, allow_tracking=False, file_upload_dirs=False,
            dangerously_allow_auto_upload_download_files=False)
        with pytest.raises(Exception):
            sdk.sessions.create(user_id="test-owned-user",
                toolkits={"enable": ["instagram"]}, sandbox={"enable": False},
                proxy_execute=False, manage_connections=False,
                tags={"enable": ["readOnlyHint"]})
    assert len(requests) == 1, "The SDK must reach the mock boundary once, without retries"
    body = json.loads(requests[0].content)
    assert body["user_id"] == "test-owned-user"
    assert body["toolkits"] == {"enable": ["instagram"]}
    # SDK 0.30 maps its public sandbox option to the API's workbench field.
    assert body["workbench"]["enable"] is False
    assert body["proxy_execute"] == {"enable": False}
    assert body["manage_connections"]["enable"] is False
