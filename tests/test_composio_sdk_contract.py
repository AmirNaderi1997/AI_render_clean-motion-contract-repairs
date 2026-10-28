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


def test_search_projection_matches_current_sdk_response_model():
    pytest.importorskip("composio")
    from composio_client.types.tool_router.session_search_response import SessionSearchResponse
    from hermes.services.composio_sessions import public_discovery
    response = SessionSearchResponse.model_validate({
        "success": True, "error": None, "results": [], "next_steps_guidance": ["untrusted instructions"],
        "session": {"generate_id": True, "id": "private-test-session", "instructions": "private guidance"},
        "time_info": {"current_time_utc": "2026-10-28T00:00:00Z", "current_time_utc_epoch_seconds": 1793145600, "message": "UTC"},
        "tool_schemas": {"INSTAGRAM_TEST_READ": {"tool_slug": "INSTAGRAM_TEST_READ", "toolkit": "instagram",
            "description": "Mock read tool", "hasFullSchema": True,
            "input_schema": {"type": "object", "properties": {"limit": {"type": "integer"}}}}},
        "toolkit_connection_statuses": []})
    result = public_discovery(response, "instagram")
    assert result["tools"][0]["schema_available"]
    assert "private-test-session" not in str(result)
    assert "untrusted instructions" not in str(result)
