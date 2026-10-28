"""Native Hermes plugin; delegates bounded work to existing authenticated APIs.

No provider keys, user IDs, shell commands or arbitrary URLs are model arguments.
Credentials resolve on every call under Hermes' active profile scope.
"""
import json
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

SCHEMA = {
    "name": "editorgpt_instagram_check",
    "description": "Check supplied Instagram text with EditorGPT. Persian/mixed Persian supports hook, beats, caption, humanize; English also audit_text and swipe. Preserves Persian ZWNJ. Does not generate scripts, research, publish or message. Scores are heuristics, not virality predictions.",
    "parameters": {"type": "object", "additionalProperties": False,
        "properties": {
            "operation": {"type": "string", "enum": ["hook", "beats", "caption", "humanize", "audit_text", "swipe"]},
            "language": {"type": "string", "enum": ["fa", "en"]},
            "text": {"type": "string", "minLength": 1, "maxLength": 20000},
            "wpm": {"type": "number", "minimum": 60, "maximum": 300},
            "target": {"type": "number", "minimum": 1, "maximum": 600}},
        "required": ["operation", "language", "text"]},
}

DISCOVERY_SCHEMA = {
    "name": "editorgpt_discover_app_tools",
    "description": "Discover up to six tools for one specific use case in an administrator-allowed connected app. Prefer an English query. Returns schemas only, not account data or authorization to execute. Do not include credentials or private message contents. No publishing, messaging or arbitrary execution.",
    "parameters": {"type": "object", "additionalProperties": False,
        "properties": {"application": {"type": "string", "maxLength": 64, "pattern": "^[a-z0-9_]+$"},
                       "query": {"type": "string", "minLength": 1, "maxLength": 1000}},
        "required": ["application", "query"]},
}


def _secret(name):
    from agent.secret_scope import get_secret
    return get_secret(name)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _call(args, schema, endpoint, required):
    try:
        origin = _secret("EDITORGPT_API_ORIGIN") or ""
        token = _secret("EDITORGPT_ACCESS_TOKEN") or ""
        parsed = urlsplit(origin)
        secure = parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"})
        if not token or not secure or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            return json.dumps({"error": "EDITORGPT_PROFILE_CONNECTION_REQUIRED"})
        if not isinstance(args, dict) or set(args) - set(schema["parameters"]["properties"]):
            return json.dumps({"error": "INVALID_ARGUMENTS"})
        payload = json.dumps(args, ensure_ascii=False, allow_nan=False).encode()
        if len(payload) > 100_000:
            return json.dumps({"error": "INPUT_TOO_LARGE"})
        request = Request(origin.rstrip("/") + endpoint, data=payload,
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="POST")
        # Never forward bearer credentials to a redirected host or ambient proxy.
        opener = build_opener(NoRedirect(), ProxyHandler({}))
        with opener.open(request, timeout=45) as response:
            raw = response.read(1_048_577)
        if len(raw) > 1_048_576:
            return json.dumps({"error": "RESPONSE_TOO_LARGE"})
        result = json.loads(raw)
        if not isinstance(result, dict) or not set(required).issubset(result):
            return json.dumps({"error": "INVALID_RESPONSE"})
        return json.dumps(result, ensure_ascii=False)
    except HTTPError as exc:
        return json.dumps({"error": "EDITORGPT_AUTH_EXPIRED" if exc.code == 401 else "EDITORGPT_CHECK_REJECTED", "status": exc.code})
    except Exception:
        return json.dumps({"error": "EDITORGPT_CHECK_UNAVAILABLE"})


def check(args, **kwargs):
    return _call(args, SCHEMA, "/api/hermes/content-tools/check", ("result", "disclaimer"))


def discover(args, **kwargs):
    return _call(args, DISCOVERY_SCHEMA, "/api/hermes/composio/discover", ("tools", "notice"))


def register(ctx):
    ctx.register_tool(name=SCHEMA["name"], toolset="editorgpt_instagram",
                      schema=SCHEMA, handler=check)
    ctx.register_tool(name=DISCOVERY_SCHEMA["name"], toolset="editorgpt_instagram",
                      schema=DISCOVERY_SCHEMA, handler=discover)
