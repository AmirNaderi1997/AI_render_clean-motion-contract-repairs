"""Direct provider fallbacks for when LM API (the gateway) fails.

Order of operations in `lm_gateway.complete()`: the gateway tries the route's models first. Only if that
fails does it call `try_fallback`, which walks the configured providers in priority order and returns the first
answer. Text (chat) only: media routes keep their own provider paths.

Security and operations:
* API keys are write-only through the admin API: stored in `direct_keys.json` (mode 0600) next to the gateway
  state, never returned, never logged. `DIRECT_<PROVIDER>_API_KEY` environment variables also work.
* Base URLs must be https, without credentials/query, and must not point at loopback/private addresses.
* The master switch (and each provider's switch) is in *AI Models & Logs → Direct fallbacks*.
* Gemini is reached through a proxy (Vercel AI Gateway by default, OpenAI-compatible; switch the format to
  "gemini" for a reverse proxy of the native Google API such as a Vercel-hosted relay).
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings
from . import lm_adapters as adapters

log = logging.getLogger(__name__)
_lock = threading.Lock()

# Priority order is the order of this list. Models are defaults; routes naming a model of the same provider win.
PROVIDERS: dict[str, dict[str, Any]] = {
    "sarovi": {"title": "Sarovi", "base_url": "https://api.sarovi.ir/v1", "model": "gpt-4.1-mini", "format": "openai", "group": "sarovi-all-models"},
    "jarvis": {"title": "Jarvis", "base_url": "https://api.jarvis.you/v1", "model": "CLAUDE_SONNET_5_5", "format": "openai", "group": "jarvis-all-models"},
    "arvan": {"title": "ArvanCloud", "base_url": "https://aiapi.rafiei.co/v1", "model": "GPT-5.6-Sol", "format": "openai", "group": "arvancloud-all-models", "auth": "apikey"},
    "openai": {"title": "OpenAI", "base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini", "format": "openai", "group": "openai-all-models"},
    "gemini": {"title": "Gemini (via Vercel proxy)", "base_url": "https://ai-gateway.vercel.sh/v1", "model": "gemini-3.5-flash", "format": "openai", "group": None},
}
FORMATS = ("openai", "gemini")


class DirectError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


# ── configuration ────────────────────────────────────────────────────────────

def _store():
    from app import lm_store
    return lm_store


def _secret_path() -> Path:
    return Path(settings.JOBS_DIR).expanduser() / "ai_gateway" / "direct_keys.json"


def _read_secrets() -> dict[str, str]:
    path = _secret_path()
    try:
        return json.loads(path.read_text()) if path.is_file() else {}
    except (OSError, ValueError):
        return {}


def _write_secrets(values: dict[str, str]) -> None:
    path = _secret_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(values, handle)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def validate_base_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Base URL must be an https address without credentials or query")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith((".local", ".internal")):
        raise ValueError("Base URL must be a public host")
    try:
        address = ipaddress.ip_address(host)
        if not address.is_global:
            raise ValueError("Base URL must be a public host")
    except ValueError as exc:
        if "public host" in str(exc):
            raise
    return url.strip().rstrip("/")


def config() -> dict:
    """Effective settings (no secrets): master switch plus ordered providers with their overrides applied."""
    saved = _store().records("settings").get("direct", {}) or {}
    overrides = saved.get("providers", {}) or {}
    order = [pid for pid in saved.get("order", []) if pid in PROVIDERS] + [pid for pid in PROVIDERS if pid not in saved.get("order", [])]
    providers = []
    for pid in order:
        base, saved_p = PROVIDERS[pid], overrides.get(pid, {})
        providers.append({
            "id": pid, "title": base["title"], "enabled": bool(saved_p.get("enabled", True)),
            "base_url": saved_p.get("base_url") or base["base_url"], "model": saved_p.get("model") or base["model"],
            "format": saved_p.get("format") if saved_p.get("format") in FORMATS else base["format"],
            "extra_header_name": saved_p.get("extra_header_name", ""),
        })
    return {"enabled": bool(saved.get("enabled", True)), "providers": providers}


def _env_key(provider: str) -> str:
    """Keys already configured for the legacy single-provider paths are reused, so nothing has to be entered twice."""
    legacy = {"arvan": settings.ARVAN_AI_API_KEY, "openai": settings.OPENAI_API_KEY, "gemini": settings.GEMINI_API_KEY}.get(provider, "")
    return (os.environ.get(f"DIRECT_{provider.upper()}_API_KEY") or legacy or "").strip()


def key_for(provider: str) -> str:
    return (_read_secrets().get(provider, "") or _env_key(provider)).strip()


def header_value_for(provider: str) -> str:
    return _read_secrets().get(f"{provider}:header", "").strip()


def status() -> dict:
    """Admin view: configuration plus whether a key exists (and its last 4 characters). Never the key."""
    result = config()
    secrets = _read_secrets()
    for item in result["providers"]:
        pid = item["id"]
        key = key_for(pid)
        item.update(configured=bool(key), key_hint=("…" + key[-4:]) if len(key) >= 8 else ("set" if key else ""),
                    key_source="saved" if secrets.get(pid) else ("environment" if _env_key(pid) else None),
                    extra_header_set=bool(secrets.get(f"{pid}:header")))
    return result


def save_config(enabled: bool, providers: list[dict]) -> dict:
    seen, order, overrides = set(), [], {}
    for item in providers:
        pid = item.get("id")
        if pid not in PROVIDERS or pid in seen:
            raise ValueError(f"Unknown or duplicate provider: {pid}")
        seen.add(pid); order.append(pid)
        base = validate_base_url(item.get("base_url") or PROVIDERS[pid]["base_url"])
        model = " ".join(str(item.get("model") or PROVIDERS[pid]["model"]).split())[:200]
        fmt = item.get("format") if item.get("format") in FORMATS else PROVIDERS[pid]["format"]
        header = str(item.get("extra_header_name") or "").strip()[:60]
        if header and not all(c.isalnum() or c in "-_" for c in header):
            raise ValueError("Header names may contain letters, digits, - and _ only")
        overrides[pid] = {"enabled": bool(item.get("enabled", True)), "base_url": base, "model": model, "format": fmt, "extra_header_name": header}
    _store().save("settings", {"direct": {"enabled": bool(enabled), "order": order, "providers": overrides}})
    return status()


def set_secret(name: str, value: str | None) -> None:
    """`name` is a provider id (API key) or "<id>:header" (extra header value). Empty value deletes it."""
    provider = name.split(":")[0]
    if provider not in PROVIDERS:
        raise ValueError("Unknown provider")
    with _lock:
        values = _read_secrets()
        value = (value or "").strip()
        if value:
            if len(value) > 4000 or any(c in value for c in "\r\n"):
                raise ValueError("Invalid value")
            values[name] = value
        else:
            values.pop(name, None)
        _write_secrets(values)


# ── wire formats ─────────────────────────────────────────────────────────────

def _to_gemini(messages: list[dict], tokens: int, temperature) -> dict:
    system = [m["content"] for m in messages if m["role"] == "system" and isinstance(m["content"], str)]
    contents = []
    for message in messages:
        if message["role"] == "system":
            continue
        parts = []
        content = message["content"]
        for part in content if isinstance(content, list) else [{"type": "text", "text": content}]:
            if part.get("type") == "text":
                parts.append({"text": part.get("text", "")})
            elif part.get("type") == "image_url":
                url = (part.get("image_url") or {}).get("url", "")
                if url.startswith("data:") and ";base64," in url:
                    mime, _, data = url[5:].partition(";base64,")
                    parts.append({"inlineData": {"mimeType": mime, "data": data}})
        contents.append({"role": "model" if message["role"] == "assistant" else "user", "parts": parts or [{"text": ""}]})
    body: dict[str, Any] = {"contents": contents, "generationConfig": {"maxOutputTokens": tokens}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": "\n".join(system)}]}
    if temperature is not None:
        body["generationConfig"]["temperature"] = temperature
    return body


def _from_gemini(data: dict, model: str) -> dict:
    candidates = data.get("candidates") or []
    parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    if not text:
        raise DirectError("Gemini returned no text")
    usage = data.get("usageMetadata") or {}
    return {"model": model, "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": usage.get("promptTokenCount"), "completion_tokens": usage.get("candidatesTokenCount")}}


def _post(url: str, headers: dict, body: dict, timeout: float) -> httpx.Response:
    from .http_ssl import ssl_context
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=min(timeout, 10)), verify=ssl_context(), follow_redirects=False) as client:
        return client.post(url, headers=headers, json=body)


def call(provider: dict, messages: list[dict], *, model: str, tokens: int, temperature=None, timeout: float = 90, extra=None) -> dict:
    """One request to one provider. Returns an OpenAI-shaped chat response or raises DirectError."""
    key = key_for(provider["id"])
    if not key:
        raise DirectError("No API key configured")
    base = validate_base_url(provider["base_url"])
    headers = {"Content-Type": "application/json"}
    name = provider.get("extra_header_name")
    if name and header_value_for(provider["id"]):
        headers[name] = header_value_for(provider["id"])
    if provider["format"] == "gemini":
        if extra and (extra.get("tools") or extra.get("response_format")):
            raise DirectError("Gemini native format does not carry tools or structured output")
        headers["x-goog-api-key"] = key
        url, body = f"{base}/models/{model}:generateContent", _to_gemini(messages, tokens, temperature)
    else:
        headers["Authorization"] = f"{PROVIDERS[provider['id']].get('auth', 'Bearer')} {key}"
        url, body = f"{base}/chat/completions", adapters.payload("chat", model, messages, tokens=tokens, temperature=temperature, extra=extra)
    try:
        response = _post(url, headers, body, timeout)
    except httpx.TimeoutException as exc:
        raise DirectError(f"{type(exc).__name__}", 504) from exc
    except httpx.HTTPError as exc:
        raise DirectError(f"{type(exc).__name__}", 502) from exc
    if not response.is_success:
        raise DirectError(f"HTTP {response.status_code}: {_scrub(response.text, key)}", response.status_code)
    try:
        data = response.json()
    except ValueError as exc:
        raise DirectError("Provider returned invalid JSON", 502) from exc
    return _from_gemini(data, model) if provider["format"] == "gemini" else data


def _scrub(text: str, key: str, limit: int = 240) -> str:
    return " ".join((text or "").replace(key, "[REDACTED]").split())[:limit]


# ── fallback policy ──────────────────────────────────────────────────────────

def model_for(provider: dict, candidates: list[str]) -> str:
    """Prefer a model the route already names for this provider; otherwise the provider's configured default."""
    base = PROVIDERS[provider["id"]]
    for candidate in candidates:
        if base["group"] and candidate.startswith("custom:") and candidate.endswith("#" + base["group"]):
            return candidate[len("custom:"):-len("#" + base["group"])]
        if provider["id"] == "gemini" and candidate.startswith("google:"):
            raw = candidate.partition(":")[2]
            return raw if provider["format"] == "gemini" else f"google/{raw}"
    model = provider["model"]
    if provider["id"] == "gemini" and provider["format"] == "openai" and "/" not in model:
        return f"google/{model}"
    return model


def usable(providers: list[dict] | None = None) -> list[dict]:
    cfg = config()
    if not cfg["enabled"]:
        return []
    return [p for p in (providers or cfg["providers"]) if p["enabled"] and key_for(p["id"])]


def try_fallback(messages: list[dict], *, candidates: list[str], tokens: int, temperature, timeout: float, extra,
                 attempts: list[dict]) -> tuple[dict, str, str] | None:
    """Walk enabled providers with keys, in order. Returns (response, provider_id, model) or None. Appends to `attempts`."""
    for provider in usable():
        model = model_for(provider, candidates)
        started = time.monotonic()
        try:
            response = call(provider, messages, model=model, tokens=tokens, temperature=temperature, timeout=min(timeout, 120), extra=extra)
            attempts.append({"model": f"direct:{provider['id']}:{model}", "http_status": 200, "latency_ms": round((time.monotonic() - started) * 1000)})
            return response, provider["id"], model
        except DirectError as exc:
            log.warning("direct fallback %s failed: %s", provider["id"], str(exc)[:160])
            attempts.append({"model": f"direct:{provider['id']}:{model}", "http_status": exc.status, "error": str(exc)[:240],
                             "latency_ms": round((time.monotonic() - started) * 1000)})
    return None


def probe(provider_id: str) -> dict:
    """Admin 'Test' button: one tiny request to one provider, regardless of the master switch."""
    item = next((p for p in config()["providers"] if p["id"] == provider_id), None)
    if item is None:
        raise ValueError("Unknown provider")
    model = model_for(item, [])
    started = time.monotonic()
    try:
        data = call(item, [{"role": "user", "content": "Reply with the single word: ok"}], model=model, tokens=16, timeout=40)
        reply = adapters.text("chat", data)
        return {"ok": True, "model": model, "latency_ms": round((time.monotonic() - started) * 1000), "reply": reply[:40]}
    except DirectError as exc:
        return {"ok": False, "model": model, "latency_ms": round((time.monotonic() - started) * 1000), "error": str(exc)[:240]}
