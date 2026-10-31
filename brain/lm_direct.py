"""Direct AI providers: the transport behind `lm_gateway` (there is no remote LM API).

`lm_gateway.complete()` calls `complete_routed`, which turns a route's models into (provider, model) pairs
(`custom:<model>#jarvis-all-models` → Jarvis `<model>`, and so on), tries them in order, then each enabled
provider's default model, and returns the first answer. Text, vision and structured JSON use that
route policy; audio uses the single-attempt transport below. Images and video keep their specialist
paths. Jarvis and Sarovi are enabled by default; the others are opt-in.

Security and operations:
* API keys are write-only through the admin API: stored in `direct_keys.json` (mode 0600) next to the gateway
  state, never returned, never logged. `DIRECT_<PROVIDER>_API_KEY` environment variables also work.
* Base URLs must be https, without credentials/query, and must not point at loopback/private addresses.
* The master switch (and each provider's switch) is in *AI Models & Logs → Direct providers*.
* Gemini is reached through a proxy (Vercel AI Gateway by default, OpenAI-compatible; switch the format to
  "gemini" for a reverse proxy of the native Google API such as a Vercel-hosted relay).
"""
from __future__ import annotations

import ipaddress
import json
import re
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

# Priority order is the order of this list: Jarvis, Sarovi, Arvan, OpenAI, Gemini (Gemini is moved first for Google/Gemini models, see `usable`). Models are defaults; routes naming a model of the same provider win.
PROVIDERS: dict[str, dict[str, Any]] = {
    "jarvis": {"title": "Jarvis", "base_url": "https://api.jarvis.you/v1", "model": "CLAUDE_SONNET_5_5", "format": "openai", "group": "jarvis-all-models"},
    "sarovi": {"title": "Sarovi", "base_url": "https://api.sarovi.ir/v1", "model": "gpt-4.1-mini", "format": "openai", "group": "sarovi-all-models"},
    "arvan": {"title": "ArvanCloud", "base_url": "https://api.arvancloudai.ir/v1", "model": "GPT-5.6-Sol", "format": "openai", "group": "arvancloud-all-models", "auth": "apikey"},
    "openai": {"title": "OpenAI", "base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini", "format": "openai", "group": "openai-all-models"},
    "gemini": {"title": "Gemini (via Vercel proxy)", "base_url": "https://ai-gateway.vercel.sh/v1", "model": "gemini-3.5-flash", "format": "openai", "group": None},
}
FORMATS = ("openai", "gemini")
DEFAULT_ENABLED = {"jarvis", "sarovi"}      # the others carry legacy keys (e.g. ARVAN_AI_API_KEY) and are opt-in


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
            "id": pid, "title": base["title"], "enabled": bool(saved_p.get("enabled", pid in DEFAULT_ENABLED)),
            "base_url": saved_p.get("base_url") or _env_default(pid, "BASE_URL") or base["base_url"],
            "model": saved_p.get("model") or _env_default(pid, "LLM_MODEL") or _env_default(pid, "MODEL") or base["model"],
            "format": saved_p.get("format") if saved_p.get("format") in FORMATS else base["format"],
            "extra_header_name": saved_p.get("extra_header_name", ""),
            "prefer_stream": bool(saved_p.get("prefer_stream", False)),
        })
    return {"enabled": bool(saved.get("enabled", True)), "providers": providers,
            "stt": {"enabled": True, "model": "small", "improve_low_quality": True, **saved.get("stt", {})}}


def _env_default(provider: str, name: str) -> str:
    """`JARVIS_BASE_URL`, `JARVIS_MODEL`, `SAROVI_LLM_MODEL`, ...: installation defaults below saved admin overrides."""
    return os.environ.get(f"{provider.upper()}_{name}", "").strip()


def _env_key(provider: str) -> str:
    """Keys already configured for the legacy single-provider paths are reused, so nothing has to be entered twice."""
    legacy = {"arvan": settings.ARVAN_AI_API_KEY, "openai": settings.OPENAI_API_KEY, "gemini": settings.GEMINI_API_KEY}.get(provider, "")
    return (os.environ.get(f"DIRECT_{provider.upper()}_API_KEY") or os.environ.get(f"{provider.upper()}_API_KEY")
            or legacy or "").strip()


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


def save_config(enabled: bool, providers: list[dict], stt: dict | None = None) -> dict:
    seen, order, overrides = set(), [], {}
    previous = {p["id"]: p for p in config()["providers"]}
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
        overrides[pid] = {"enabled": bool(item.get("enabled", True)), "base_url": base, "model": model, "format": fmt, "extra_header_name": header,
                          "prefer_stream": previous[pid]["prefer_stream"] if item.get("prefer_stream") is None else bool(item["prefer_stream"])}
    stt = stt if stt is not None else config()["stt"]
    if stt.get('model') not in {'base','small','medium','large-v3'}:
        raise ValueError('Unsupported local Whisper model')
    _store().save("settings", {"direct": {"enabled": bool(enabled), "order": order, "providers": overrides, "stt": stt}})
    return status()


def apply_priority() -> dict:
    """Reset the direct-fallback order to Jarvis, Sarovi, Arvan, OpenAI, Gemini, keeping every override and the master switch."""
    cfg = config()
    ranked = sorted(cfg["providers"], key=lambda p: list(PROVIDERS).index(p["id"]))
    return save_config(cfg["enabled"], ranked, cfg["stt"])


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
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get('thought'))
    if not text:
        raise DirectError("Gemini returned no text")
    usage = data.get("usageMetadata") or {}
    finish = candidates[0].get('finishReason','STOP') if candidates else 'STOP'
    return {"model": model, "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": 'length' if finish=='MAX_TOKENS' else 'stop' if finish=='STOP' else finish.lower()}],
            "usage": {"prompt_tokens": usage.get("promptTokenCount"), "completion_tokens": usage.get("candidatesTokenCount")}}


def _post(url: str, headers: dict, body: dict, timeout: float) -> httpx.Response:
    from .http_ssl import ssl_context
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=min(timeout, 10)), verify=ssl_context(), follow_redirects=False) as client:
        return client.post(url, headers=headers, json=body)


def _prepare(provider: dict, messages: list[dict], *, model: str, tokens: int, temperature, extra, stream: bool):
    key = key_for(provider["id"])
    if not key:
        raise DirectError("No API key configured")
    base = validate_base_url(provider["base_url"])
    headers = {"Content-Type": "application/json"}
    name = provider.get("extra_header_name")
    if name and header_value_for(provider["id"]):
        headers[name] = header_value_for(provider["id"])
    if provider["format"] == "gemini":
        if extra and (extra.get("tools") or (extra.get("response_format") and extra['response_format'].get('type')!='json_object')):
            raise DirectError("Gemini native format does not carry tools or structured output")
        native = _to_gemini(messages, tokens, temperature)
        if (extra or {}).get('response_format',{}).get('type')=='json_object':
            native['generationConfig']['responseMimeType']='application/json'
        if model == 'gemini-3.5-flash':
            native['generationConfig']['thinkingConfig']={'thinkingLevel':'minimal' if tokens<=512 else 'low'}
        if base == 'https://rafiei-telegram-api-relay.vercel.app/api/gemini':
            # The approved relay owns the Google key; the client authenticates
            # with a separate relay secret and must not append native API paths.
            relay_secret = settings.GEMINI_RELAY_SECRET
            if not relay_secret:
                raise DirectError('Gemini relay secret is not configured')
            headers['x-relay-secret'] = relay_secret
            headers['x-gemini-model'] = model
            return relay_secret, base, headers, native
        headers["x-goog-api-key"] = key
        return key, f"{base}/models/{model}:generateContent", headers, native
    headers["Authorization"] = f"{PROVIDERS[provider['id']].get('auth', 'Bearer')} {key}"
    body = adapters.payload("chat", model, messages, tokens=tokens, temperature=temperature, extra=extra)
    if provider["id"] == "openai" and re.match(r"(gpt-5|o[134])", model or ""):
        # OpenAI's reasoning models take max_completion_tokens (thinking tokens count against it), no temperature, and a reasoning effort.
        body = {k: v for k, v in body.items() if k not in ("max_tokens", "temperature")}
        body["max_completion_tokens"] = max(int(tokens or 0) * 3, 2500)
        # Big structured jobs (scripts, concepts, plans: thousands of tokens) get real thinking; short answers stay quick.
        body.setdefault("reasoning_effort", "medium" if int(tokens or 0) >= 3500 else "low")
    if stream:
        body = {**body, "stream": True}
    return key, f"{base}/chat/completions", headers, body


def call(provider: dict, messages: list[dict], *, model: str, tokens: int, temperature=None, timeout: float = 90, extra=None) -> dict:
    """One request to one provider. Returns an OpenAI-shaped chat response or raises DirectError."""
    if provider.get("prefer_stream") and provider["format"] == "openai" and not any((extra or {}).get(k) for k in ("tools", "tool_choice", "functions", "function_call")):
        # Jarvis's tested transport accepts SSE while synchronous responses can
        # disconnect before headers. Collect SSE without replaying the request or
        # changing the selected provider/model; callers still validate the result.
        metadata = {}
        text = "".join(stream_call(provider, messages, model=model, tokens=tokens, temperature=temperature,
                                   timeout=timeout, extra=extra, _metadata=metadata))
        if not text.strip(): raise DirectError("Provider returned no text", 502)
        result = {"model": metadata.get("model", model), "choices": [{"message": {"role": "assistant", "content": text},
                   "finish_reason": metadata.get("finish_reason")} ]}
        if "usage" in metadata: result["usage"] = metadata["usage"]
        return result
    key, url, headers, body = _prepare(provider, messages, model=model, tokens=tokens, temperature=temperature, extra=extra, stream=False)
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


def stream_call(provider: dict, messages: list[dict], *, model: str, tokens: int, temperature=None, timeout: float = 60, extra=None, _metadata=None):
    """Real token streaming from one provider (OpenAI-compatible SSE). The native Gemini format has no stream here: its whole answer is yielded once."""
    if provider["format"] == "gemini":
        yield adapters.text("chat", call(provider, messages, model=model, tokens=tokens, temperature=temperature, timeout=timeout))
        return
    from .http_ssl import ssl_context
    key, url, headers, body = _prepare(provider, messages, model=model, tokens=tokens, temperature=temperature, extra=extra, stream=True)
    started = time.monotonic()
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=min(timeout, 10)), verify=ssl_context(), follow_redirects=False) as client:
            with client.stream("POST", url, headers=headers, json=body) as response:
                if not response.is_success:
                    response.read()
                    raise DirectError(f"HTTP {response.status_code}: {_scrub(response.text, key)}", response.status_code)
                done = False
                for line in response.iter_lines():
                    if time.monotonic() - started > timeout:
                        raise DirectError("stream deadline exceeded", 504)
                    if not line.startswith("data:"):
                        continue
                    value = line[5:].strip()
                    if value == "[DONE]":
                        done = True
                        break
                    try:
                        chunk = json.loads(value)
                    except ValueError:
                        continue
                    if chunk.get("error"):
                        raise DirectError("provider reported a stream error", 502)
                    if _metadata is not None:
                        if chunk.get("model"): _metadata["model"] = chunk["model"]
                        if chunk.get("usage"): _metadata["usage"] = chunk["usage"]
                    choices = chunk.get("choices") or []
                    delta = (choices[0].get("delta") or {}).get("content") if choices else None
                    if delta:
                        yield delta
                    if choices and choices[0].get("finish_reason"):
                        done = True
                        if _metadata is not None: _metadata["finish_reason"] = choices[0]["finish_reason"]
                if not done:
                    raise DirectError("stream ended before completion", 502)
    except httpx.TimeoutException as exc:
        raise DirectError(type(exc).__name__, 504) from exc
    except httpx.HTTPError as exc:
        raise DirectError(type(exc).__name__, 502) from exc


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


_REJECTED: dict[str, float] = {}      # provider id -> monotonic time until which a rejected key is not tried again
REJECTED_COOLDOWN_S = 600


def _note_failure(provider: dict, exc: "DirectError") -> None:
    """A key the provider rejected (401/403) will not start working by itself: do not spend a round trip on it for a while."""
    status = getattr(exc, "status", None)
    if status in (401, 403):
        _REJECTED[provider["id"]] = time.monotonic() + REJECTED_COOLDOWN_S
    elif status == 402:
        _REJECTED[provider["id"]] = time.monotonic() + 120          # no credit left on this key: do not retry it on every call


def usable(providers: list[dict] | None = None, *, google_first: bool = False) -> list[dict]:
    cfg = config()
    if not cfg["enabled"]:
        return []
    now = time.monotonic()
    found = [p for p in (providers or cfg["providers"]) if p["enabled"] and key_for(p["id"]) and _REJECTED.get(p["id"], 0) <= now]
    if google_first:
        # Gemini/Google models are asked of Google itself before any reseller.
        found.sort(key=lambda p: 0 if p["id"] == "gemini" else 1)
    return found


def complete_routed(messages: list[dict], *, candidates: list[str], tokens: int, temperature, timeout: float, extra,
                    attempts: list[dict], validate=None, only_candidates: bool = False,
                    deadline: float | None = None) -> tuple[dict, str, str] | None:
    """Try the route's (provider, model) pairs in order. Returns (response, provider_id, model) or None. Appends to `attempts`."""
    for provider, model in route_pairs(candidates, only_candidates=only_candidates):
        if deadline is not None and time.monotonic() >= deadline:
            break
        if _REJECTED.get(provider["id"], 0) > time.monotonic():
            continue                                                  # its key was just refused for an earlier model
        started = time.monotonic()
        try:
            provider_extra = extra
            # A structured caller wants JSON: Gemini and OpenAI are asked for JSON mode (OpenAI's plain answer was refused as "invalid structured output").
            if validate is not None and (provider['format']=='gemini' or provider['id']=='openai') and not (extra or {}).get('response_format'):
                provider_extra={**(extra or {}),'response_format':{'type':'json_object'}}
            response = call(provider, messages, model=model, tokens=tokens, temperature=temperature, timeout=min(timeout, 120), extra=provider_extra)
            if validate is not None:
                # Structured callers (JSON plans): an answer that does not parse is no answer; ask the next provider instead.
                try:
                    validate(adapters.text("chat", response))
                except (ValueError, TypeError, KeyError):
                    attempts.append({"model": f"direct:{provider['id']}:{model}", "http_status": 200, "error": "invalid structured output",
                                     "latency_ms": round((time.monotonic() - started) * 1000)})
                    continue
            attempts.append({"model": f"direct:{provider['id']}:{model}", "http_status": 200, "latency_ms": round((time.monotonic() - started) * 1000)})
            return response, provider["id"], model
        except DirectError as exc:
            _note_failure(provider, exc)
            log.warning("direct provider %s (%s) failed: %s", provider["id"], model, str(exc)[:160])
            attempts.append({"model": f"direct:{provider['id']}:{model}", "http_status": exc.status, "error": str(exc)[:240],
                             "latency_ms": round((time.monotonic() - started) * 1000)})
    return None


def route_pairs(candidates: list[str], *, only_candidates: bool = False) -> list[tuple[dict, str]]:
    """(provider, model) pairs in priority order: the route's own models first (as the route lists them), then each usable
    provider's default unless ``only_candidates`` (probes and routes without automatic fallback)."""
    providers = {p["id"]: p for p in usable(google_first=any(str(c).startswith("google:") for c in candidates[:1]))}
    by_group = {PROVIDERS[pid]["group"]: pid for pid in PROVIDERS if PROVIDERS[pid].get("group")}
    pairs: list[tuple[dict, str]] = []
    for candidate in candidates:
        candidate = str(candidate)
        if candidate.startswith("custom:") and "#" in candidate:
            raw, _, group = candidate[len("custom:"):].rpartition("#")
            provider = providers.get(by_group.get(group, ""))
            if provider and raw:
                pairs.append((provider, raw))
        elif candidate.startswith("google:") and "gemini" in providers:
            provider = providers["gemini"]
            raw = candidate.partition(":")[2]
            pairs.append((provider, raw if provider["format"] == "gemini" else f"google/{raw}"))
    if not only_candidates:
        for provider in providers.values():
            pairs.append((provider, model_for(provider, [])))
    seen, unique = set(), []
    for provider, model in pairs:
        if (provider["id"], model) not in seen:
            seen.add((provider["id"], model))
            unique.append((provider, model))
    return unique


def stream_fallback(messages: list[dict], *, candidates: list[str], tokens: int, temperature=None, timeout: float = 60, hedge_after: float = 2.5,
                    only_candidates: bool = False, info: dict | None = None):
    """Stream the answer from the direct providers, fast: the first attempt starts at once, the next one joins when no text has arrived after
    ``hedge_after`` seconds (the slow one keeps running), and the first attempt to produce text wins; the others are dropped. A winner is never mixed
    with another provider. Raises DirectError when no attempt produced anything. ``info``, when given, receives the winner's provider, model
    (as reported by the stream when it says) and usage."""
    import queue
    attempts = route_pairs(candidates, only_candidates=only_candidates)
    if not attempts:
        raise DirectError("no direct provider is configured")
    events: "queue.Queue" = queue.Queue()
    state = {"winner": None}
    metas: dict[int, dict] = {}

    def work(index: int, provider: dict, model: str) -> None:
        extra = {"_metadata": metas.setdefault(index, {})} if info is not None else {}
        try:
            for piece in stream_call(provider, messages, model=model, tokens=tokens, temperature=temperature, timeout=timeout, **extra):
                if state["winner"] not in (None, index):
                    return                                            # another attempt already won: let go of this stream
                events.put((index, "piece", piece))
            events.put((index, "done", None))
        except DirectError as exc:
            _note_failure(provider, exc)
            log.warning("direct stream %s (%s) failed: %s", provider["id"], model, str(exc)[:160])
            events.put((index, "error", exc))

    started = 0
    last_start = 0.0
    alive: set[int] = set()
    last_error: DirectError | None = None

    def launch() -> None:
        nonlocal started, last_start
        provider, model = attempts[started]
        alive.add(started)
        threading.Thread(target=work, args=(started, provider, model), daemon=True, name=f"direct-stream-{provider['id']}").start()
        started += 1
        last_start = time.monotonic()

    launch()
    while True:
        if state["winner"] is None and started < len(attempts) and (not alive or time.monotonic() - last_start >= hedge_after):
            launch()
        try:
            index, kind, value = events.get(timeout=0.1)
        except queue.Empty:
            if not alive and started >= len(attempts):
                raise last_error or DirectError("no direct provider answered")
            continue
        if kind == "piece":
            if state["winner"] is None:
                state["winner"] = index
                if info is not None:
                    info.update(provider=attempts[index][0]["id"], model=attempts[index][1])
            if state["winner"] == index:
                yield value
        elif kind == "done":
            alive.discard(index)
            if state["winner"] == index:
                if info is not None:
                    reported = metas.get(index, {})
                    info.update({k: reported[k] for k in ("model", "usage") if reported.get(k)})
                return
            if state["winner"] is None:
                last_error = DirectError("provider answered with no text", 200)
        else:
            alive.discard(index)
            last_error = value
            if state["winner"] == index:
                raise value                                           # failed after it started speaking: the answer cannot be completed elsewhere


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
# ── single-attempt audio transport ──────────────────────────────────────────

DEFAULT_NARRATION_TTS_ORDER = "sarovi:elevenlabs/eleven-v4,jarvis:TTS_ELEVEN_V3"
# Sarovi Eleven v4 was verified live to speak Persian; no v2 family supports fa.
PERSIAN_SPEECH_MODELS = {"jarvis": {"TTS_ELEVEN_V3"}, "sarovi": {"elevenlabs/eleven-v4"}}
SAROVI_ELEVEN_VOICES = frozenset("george sarah adam alice bella bill brian callum charlie chris daniel eric harry jessica laura liam lily matilda river roger will".split())


def narration_pairs(text: str, language: str = "") -> list[tuple[dict, str]]:
    from .speech_policy import persian
    providers = {p["id"]: p for p in usable()}
    pairs, seen = [], set()
    for entry in os.environ.get("NARRATION_TTS_ORDER", DEFAULT_NARRATION_TTS_ORDER).split(","):
        pid, sep, model = entry.strip().partition(":")
        pid, model = pid.strip().lower(), model.strip()
        # Reserve a provider's slot even if its first model is invalid. Never
        # retry it under a second alias after an ambiguous billed request.
        if pid in seen:
            continue
        seen.add(pid)
        if not sep or pid not in {"jarvis", "sarovi"} or not model or pid not in providers:
            continue
        if persian(text, language) and model not in PERSIAN_SPEECH_MODELS.get(pid, set()):
            continue
        pairs.append((providers[pid], model))
    return pairs


def _audio_post(provider: dict, path: str, *, body=None, data=None, file: Path | None = None, timeout: float = 200):
    """Exactly one POST; no SDK retries, redirects, hedging or alternate endpoint."""
    from .http_ssl import ssl_context
    key = key_for(provider["id"])
    if not key:
        raise DirectError("No API key configured")
    base = validate_base_url(provider["base_url"])
    headers = {"Authorization": f"{PROVIDERS[provider['id']].get('auth', 'Bearer')} {key}"}
    name = provider.get("extra_header_name")
    if name and header_value_for(provider["id"]):
        headers[name] = header_value_for(provider["id"])
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=min(timeout, 10)), verify=ssl_context(), follow_redirects=False) as client:
            if file is None:
                response = client.post(f"{base}/{path}", headers=headers, json=body)
            else:
                import mimetypes
                with file.open("rb") as stream:
                    response = client.post(f"{base}/{path}", headers=headers, data=data,
                                           files={"file": (file.name, stream, mimetypes.guess_type(file.name)[0] or "application/octet-stream")})
    except httpx.TimeoutException as exc:
        raise DirectError(type(exc).__name__, 504) from None
    except httpx.HTTPError as exc:
        raise DirectError(type(exc).__name__, 502) from None
    if not response.is_success:
        # HTTP bodies may contain credentials, reflected input or audio. Keep
        # them entirely out of public exceptions and application logs.
        raise DirectError(f"Audio provider returned HTTP {response.status_code}", response.status_code)
    return response


def speech(provider: dict, *, model: str, text: str, voice: str, language: str = "", timeout: float = 200) -> tuple[bytes, str]:
    """One synthesis. Return validated audio bytes and the real media type."""
    import base64
    from .lm_gateway import audio_attempt
    from .speech_policy import persian
    pid = provider["id"]
    if persian(text, language) and model not in PERSIAN_SPEECH_MODELS.get(pid, set()):
        raise DirectError("Speech model is not verified for Persian")
    native = pid == "sarovi"
    endpoint = "studio/audio" if native else "audio/speech"
    # Sarovi's actual published API uses named voices + JSON/Base64 audio,
    # not the OpenAI speech endpoint. Do not spend a failed create probing it.
    if native and model.startswith("elevenlabs/"):
        voice = os.environ.get("SAROVI_ELEVENLABS_VOICE", "george").strip().lower()
        if voice not in SAROVI_ELEVEN_VOICES:
            raise DirectError("Invalid SAROVI_ELEVENLABS_VOICE")
    if not voice:
        raise DirectError("Narration voice is not configured")
    body = {"model": model, "text" if native else "input": text, "voice": voice,
            "format" if native else "response_format": "mp3"}
    if not native and language:
        body["language_code"] = "fa" if persian(text, language) else language
    if native and model.startswith("google/"):
        # Explicit opt-in only, never inherited by the default ElevenLabs route.
        body["voice"] = os.environ.get("SAROVI_TTS_VOICE", "Sulafat")
        body["instructions"] = os.environ.get("SAROVI_TTS_INSTRUCTIONS", "")
    with audio_attempt("narration", pid, model, endpoint) as audit:
        response = _audio_post(provider, endpoint, body=body, timeout=timeout)
        audit["http_status"] = response.status_code
        try:
            if native:
                output = response.json()["output"]
                mime = output["mediaType"].split(";", 1)[0].strip().lower()
                audio = base64.b64decode(output["data"], validate=True)
            else:
                mime = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                audio = response.content
        except (ValueError, KeyError, TypeError, AttributeError):
            raise DirectError("Provider returned invalid audio response", 502) from None
        if not mime.startswith("audio/") or not 1024 <= len(audio) <= 50 * 1024 * 1024:
            raise DirectError("Provider returned invalid audio type or size", 502)
        return audio, mime


def narration(text: str, *, voice: str, language: str = "") -> tuple[bytes, str, str, str]:
    """First provider to answer, one attempt per provider including 5xx/timeouts."""
    for provider, model in narration_pairs(text, language):
        try:
            audio, mime = speech(provider, model=model, text=text, voice=voice, language=language)
            return audio, mime, provider["id"], model
        except DirectError as exc:
            _note_failure(provider, exc)
            log.warning("Narration %s failed (%s)", provider["id"], type(exc).__name__)
    raise DirectError("No configured narration provider returned valid audio")


def timed_words(data: dict) -> list[dict]:
    """Require genuine finite word timings; never fabricate segment timings."""
    import math
    if not isinstance(data, dict):
        raise DirectError("STT returned invalid JSON shape", 502)
    raw = data.get("words")
    if raw is None:
        segments = data.get("segments") or []
        raw = [w for segment in segments if isinstance(segment, dict) for w in segment.get("words", [])]
    if not isinstance(raw, list) or not raw:
        raise DirectError("STT returned no word timestamps", 502)
    words = []
    previous = 0.0
    for row in raw:
        try:
            text = str(row.get("word", row.get("text", row.get("w", "")))).strip()
            start, end = float(row["start"]), float(row["end"])
            if not text or not (math.isfinite(start) and math.isfinite(end) and start >= previous and end > start):
                raise ValueError
        except (TypeError, KeyError, ValueError, AttributeError):
            raise DirectError("STT returned invalid word timestamps", 502) from None
        words.append({"word": text, "start": start, "end": end})
        previous = start
    return words


def transcription(provider: dict, audio: Path, *, model: str, language: str | None = None, timeout: float = 200) -> dict:
    """One hosted STT attempt, accepted only with word-level timestamps.

    OpenAI-compatible multipart is supported; Sarovi's deployed API documents
    JSON/Base64 instead, so its mapping is selected before the single POST.
    """
    import base64
    import mimetypes
    from .lm_gateway import audio_attempt
    if provider["id"] != "sarovi":
        raise DirectError("Only Sarovi is enabled for hosted direct transcription")
    fields = {"model": model, "response_format": "verbose_json", "timestamp_granularities[]": "word"}
    if language:
        from .speech_policy import persian
        fields["language"] = "fa" if persian(language=language) else language
    with audio_attempt("transcription", provider["id"], model, "audio/transcriptions") as audit:
        if os.environ.get("SAROVI_STT_FORMAT", "json").lower() == "multipart":
            response = _audio_post(provider, "audio/transcriptions", data=fields, file=Path(audio), timeout=timeout)
        else:
            fields.update(audioBase64=base64.b64encode(Path(audio).read_bytes()).decode(),
                          mediaType=mimetypes.guess_type(str(audio))[0] or "audio/mpeg")
            response = _audio_post(provider, "audio/transcriptions", body=fields, timeout=timeout)
        audit["http_status"] = response.status_code
        try:
            data = response.json()
        except ValueError:
            raise DirectError("STT returned invalid JSON", 502) from None
        words = timed_words(data)
        return {**data, "model": model, "words": words}
