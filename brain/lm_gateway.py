"""Central, bounded AI router used by the existing editor adapters.

There is no remote LM API: routes, their model order, the audit log and the admin panel stay here, and every
request goes straight to a direct provider (brain/lm_direct.py; Jarvis, then Sarovi by default). Chat, vision
and structured JSON are served. Speech, transcription and images keep their own specialist providers.
"""
from __future__ import annotations
import contextvars
import functools
import json
import logging
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from app.config import settings
from app import lm_store as store
from . import lm_adapters as adapters

log = logging.getLogger(__name__)
user_context = contextvars.ContextVar("ai_user", default=None)
job_context = contextvars.ContextVar("ai_job", default=None)
route_context = contextvars.ContextVar("ai_route", default=None)
conversation_context = contextvars.ContextVar("ai_conversation", default=None)
_slots = threading.BoundedSemaphore(4)
ROUTES = {
    "general_chat": ("General Chat", "chat"), "editing_agent": ("Video Editing Agent", "chat"),
    "video_understanding": ("Video Understanding", "vision"), "transcription": ("Transcription", "transcription"),
    "subtitles": ("Subtitle Processing", "chat"), "script": ("Script Generation", "chat"),
    "image": ("Image Generation", "image"), "audio": ("Audio Generation", "speech"),
    "video": ("Video Generation", "video"), "embeddings": ("Embeddings", "embeddings"),
}


class GatewayError(RuntimeError):
    def __init__(self, message, status=502, retryable=False):
        super().__init__(message); self.status = status; self.retryable = retryable


def configured():
    """True when at least one enabled direct provider has a key."""
    from . import lm_direct
    return bool(lm_direct.usable())


def _secrets():
    from . import lm_direct
    return [lm_direct.key_for(pid) for pid in lm_direct.PROVIDERS]


def safe(value, limit=6000):
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    for key in (*_secrets(), settings.ARVAN_AI_API_KEY, settings.ELEVENLABS_API_KEY):
        if key: text = text.replace(key, "[REDACTED]")
    text = re.sub(r'data:[^;\s]+;base64,[A-Za-z0-9+/=]+', '[media omitted]', text)
    text = re.sub(r'("b64_json"\s*:\s*")[^"]*', r'\1[media omitted]', text)
    text = re.sub(r'(?i)(bearer\s+|(?:api[_-]?key|token|secret)[=:]\s*)[^\s"&]+', r'\1[REDACTED]', text)
    text = re.sub(r'\b(?:sk-|freellmapi-)[A-Za-z0-9_.-]+', '[REDACTED]', text)
    return text[:limit]


def gateway_settings():
    value = store.records("settings").get("global", {})
    return {"enabled": True, "capture_messages": True, "log_char_limit": 6000, **value}


def defaults():
    existing = store.records("routes")
    new = {}
    for key, (title, capability) in ROUTES.items():
        if key not in existing:
            specialized = capability in {"image", "speech", "transcription", "video"}
            new[key] = {"id": key, "title": title, "capability": capability, "enabled": not specialized,
                "models": ["auto"], "endpoint": "embeddings" if key == "embeddings" else "chat",
                "timeout": 120, "max_retries": 1, "temperature": None, "max_tokens": 16000,
                "streaming": False, "automatic_fallback": True, "specialized_fallback": specialized}
    from .lm_tasks import TASKS, prioritize
    pending = [key for key in TASKS if key not in existing and key not in new]
    if pending:
        register_task_models()          # preferred models must exist in the catalog before a route can list them
    catalog = store.records("models") if pending else {}
    for key, spec in TASKS.items():
        if key not in existing and key not in new:
            parent = {**existing, **new}[spec["parent"]]
            # Operator priority (Jarvis, Sarovi, Arvan; Google first for Gemini) ahead of whatever the parent route uses.
            preferred = prioritize([p["id"] for p in spec["preferences"] if p["id"] in catalog])
            models = (preferred + [m for m in parent["models"] if m not in preferred])[:8]
            new[key] = {**parent, "id":key, "title":spec["title"], "capability":spec["capability"],
                        "models":models, "task_id":key}
    if new: store.save("routes", new)
    return {**existing, **new}


def sync_models():
    """No remote catalog any more: register the task models the routes name and rebuild missing routes."""
    registered = register_task_models()["registered"]
    defaults()
    store.save("settings", {"discovery": {"paths": [], "synced_at": datetime.now(timezone.utc).isoformat(),
                                          "models": len(store.records("models")), "source": "local task table"}})
    return {"models": len(store.records("models")), "registered": registered, "paths": []}


def capabilities(model):
    if model.get("scope_registered"): return set(model.get("verified", []))
    return set(model.get("verified", [])) | set(model.get("declared", []))


def register_task_models():
    """Register the task table's provider models as Untested; never infer capability."""
    from .lm_tasks import TASKS
    previous=store.records("models"); rows={}
    for task in TASKS.values():
        for pair in task["preferences"]:
            mid=pair["id"]
            if mid not in previous:
                rows[mid]={"id":mid,"name":pair["model_id"],"provider":pair["provider"],
                    "enabled":True,"available":True,"verified":[],"declared":[],"status":"Untested",
                    "scope_registered":True,"metadata":{"registration_source":"task table"}}
    if rows: store.save("models",rows)
    return {"registered":len(rows)}


def model_allowed(mid):
    # User explicitly disabled this provider. Also guard saved legacy selections.
    return not (mid.endswith("#vercel-all-models") or mid.startswith("vercel:"))


def _audit(record):
    try: store.log(record)
    except Exception: log.exception("AI audit persistence failed request=%s", record["id"])


def _record(route, endpoint, requested, started, attempts, response=None, error=None, request=None):
    cfg = gateway_settings(); response = response or {}
    return {"id": str(uuid.uuid4()), "media": [], "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_context.get(), "job_id": job_context.get(), "route": route,
        "conversation_id": conversation_context.get(), "task_id":route,
        "endpoint": adapters.PATHS[endpoint], "requested_model": requested, "actual_model": response.get("model"),
        "provider": None, "routed_via": None,
        "status": "failed" if error else "success", "latency_ms": round((time.monotonic()-started)*1000),
        **adapters.usage(response), "http_status": attempts[-1].get("http_status") if attempts else None,
        "retry_count": 0, "fallback_history": attempts, "fallback_count": max(0, len(attempts)-1),
        "gateway_fallback_attempts": None, "gateway_fallback_history": None,
        "error": safe(str(error), 500) if error else None,
        "correlation_id": __import__("request_context").current_request_id(),
        "request_message": safe(request, cfg["log_char_limit"]) if cfg["capture_messages"] else None,
        "response_message": safe(response, cfg["log_char_limit"]) if cfg["capture_messages"] else None}


def _failure(attempts):
    """Summarise what the providers answered, so 'no answer' says which key or model failed."""
    last = next((a for a in reversed(attempts) if a.get("error")), None)
    if not last:
        return GatewayError("No direct AI provider is configured for this route; add a Jarvis or Sarovi key in "
                            "AI Models & Logs → Direct providers", 503)
    status = last.get("http_status") or 502
    return GatewayError(f"No direct provider answered; last {last['model']}: {str(last['error'])[:200]}",
                        status, status in {408, 429, 500, 502, 503, 504})


from app.studio_activity import observe_request


@observe_request
def complete(route, messages, *, required=None, tokens=None, extra=None, endpoint=None, model_override=None, probe=False, validate_response=None, stream=False):
    """One answer for a route. ``required`` and ``stream`` are kept for callers; providers are chosen by route order."""
    cfg = defaults().get(route)
    if not cfg or not gateway_settings()["enabled"] or (not cfg["enabled"] and not probe):
        raise GatewayError("This AI route is disabled", 503)
    endpoint = endpoint or cfg["endpoint"]
    candidates = [model_override] if model_override else cfg["models"]
    if not cfg["automatic_fallback"]: candidates = candidates[:1]
    started = time.monotonic(); attempts = []
    if not _slots.acquire(timeout=2): raise GatewayError("AI request queue is busy", 429)
    try:
        if endpoint != "chat":
            raise GatewayError(f"The {endpoint} endpoint has no direct provider; only chat routes are served", 422)
        from . import lm_direct
        found = lm_direct.complete_routed(messages, candidates=list(candidates[:8]),
            tokens=min(tokens or cfg["max_tokens"], cfg["max_tokens"]), temperature=cfg["temperature"],
            timeout=cfg["timeout"], extra=extra, attempts=attempts, validate=validate_response,
            only_candidates=probe or not cfg["automatic_fallback"], deadline=started + min(300, cfg["timeout"]*2))
        if not found: raise _failure(attempts)
        response, provider_id, model = found
        record = _record(route, endpoint, candidates[0] if candidates else "", started, attempts, response, request=messages)
        record.update(provider=provider_id, routed_via=f"direct:{provider_id}", actual_model=response.get("model") or model)
        _audit(record)
        return response, record
    except Exception as exc:
        _audit(_record(route, endpoint if endpoint in adapters.PATHS else "chat", candidates[0] if candidates else "",
                       started, attempts, error=exc, request=messages))
        raise
    finally:
        _slots.release()


def stream_chat(route, messages, model_override=None, probe=False, *, tokens=None, timeout_seconds=None):
    """Stream a chat answer from the direct providers (real SSE; the first provider to speak wins). If none produces
    a token, ask the same route for one bounded non-streamed answer; never splice two providers' text."""
    cfg = defaults()[route]
    if not cfg["enabled"] or not gateway_settings()["enabled"]: raise GatewayError("Route disabled", 503)
    candidates = [model_override] if model_override else cfg["models"]
    from . import lm_direct
    started = time.monotonic(); text = []; info = {}
    budget = min(300, max(1, timeout_seconds)) if timeout_seconds is not None else 120
    limit = 256 if probe else min(max((tokens or 0) * 3, 1500), cfg["max_tokens"])
    try:
        for piece in lm_direct.stream_fallback(messages, candidates=list(candidates), tokens=limit,
                                               temperature=cfg["temperature"], timeout=budget, only_candidates=probe, info=info):
            text.append(piece)
            yield piece
    except lm_direct.DirectError as exc:
        error = GatewayError(f"Direct stream failed: {exc}", getattr(exc, "status", None) or 502)
        if text or probe:
            _audit(_record(route, "chat", candidates[0] if candidates else "", started,
                           [{"model": "direct:stream", "http_status": error.status}], error=error, request=messages))
            raise error from exc
        # Some upstreams accept chat but disconnect SSE before its first token.
        try:
            response, _ = complete(route, messages, tokens=tokens, model_override=model_override)
            answer = adapters.text("chat", response)
            if answer:
                yield answer
                return
        except Exception:
            pass
        raise error from exc
    provider = info.get("provider")
    record = _record(route, "chat", candidates[0] if candidates else "", started,
                     [{"model": f"direct:{provider}:{info.get('model')}" if provider else "direct:stream", "http_status": 200}],
                     {"output_text": "".join(text), "model": info.get("model"), "usage": info.get("usage")}, request=messages)
    record.update(provider=provider, routed_via=f"direct:{provider}" if provider else "direct:stream")
    _audit(record)


def probe_model(mid, capability="chat"):
    models = store.records("models")
    if mid not in models: raise GatewayError("Unknown catalog model", 404)
    allowed = {"chat", "vision", "structured", "tools", "streaming"}
    if capability not in allowed: raise GatewayError("Unsupported probe; direct providers serve chat, vision, structured, tools and streaming", 422)
    messages = [{"role": "user", "content": 'Return only {"ok":true}.'}]
    extra = None
    if capability == "vision":
        import base64, io
        from PIL import Image
        buffer = io.BytesIO(); Image.new("RGB", (32,32), "blue").save(buffer, format="PNG")
        messages = [{"role":"user","content":[{"type":"text","text":"What is the dominant color? Answer one word."},
                    {"type":"image_url","image_url":{"url":"data:image/png;base64,"+base64.b64encode(buffer.getvalue()).decode()}}]}]
    if capability == "structured": extra = {"response_format":{"type":"json_object"}}
    if capability == "tools":
        extra = {"tools":[{"type":"function","function":{"name":"ping","description":"Connectivity test","parameters":{"type":"object","properties":{}}}}],"tool_choice":"required"}
    started = time.monotonic()
    probe_record = None
    try:
        if capability == "streaming":
            output = "".join(stream_chat("general_chat", messages, mid, probe=True))
            if not output: raise GatewayError("Empty streamed response")
        else:
            data, probe_record = complete("general_chat", messages, tokens=120, extra=extra, model_override=mid, probe=True)
            output = adapters.text("chat", data)
            if capability == "tools":
                if not (data.get("choices") or [{}])[0].get("message", {}).get("tool_calls"): raise GatewayError("Tool call not returned")
            elif capability == "vision":
                if "blue" not in output.lower(): raise GatewayError("Vision test failed semantic check")
            elif capability == "structured": json.loads(output)
            elif not output: raise GatewayError("Empty model response")
        row = {"verified": [capability],
               "status":"Healthy", "last_test":datetime.now(timezone.utc).isoformat(), "test_latency_ms":round((time.monotonic()-started)*1000), "last_error":None}
    except Exception as exc:
        if probe_record:
            probe_record.update(status="failed",error=safe(str(exc),500),probe_capability=capability)
            _audit(probe_record)
        store.patch("models",mid,{"status":"Degraded" if models[mid].get("verified") else "Failed", "last_test":datetime.now(timezone.utc).isoformat(), "last_error":safe(str(exc),500)})
        raise
    if probe_record:
        probe_record["probe_capability"] = capability; _audit(probe_record)
    return store.patch("models",mid,row,union=("verified",))


def job_scope(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        obj = args[0] if args else kwargs.get("job_id")
        token = job_context.set(str(getattr(obj, "id", obj)) if obj is not None else job_context.get())
        owner = getattr(obj,"user_id",None)
        if owner is None and isinstance(obj,str):
            from app.jobs import get
            job = get(obj)
            owner = getattr(job,"user_id",None) if job else None
        user = user_context.set(str(owner) if owner is not None else user_context.get())
        try: return function(*args, **kwargs)
        finally: job_context.reset(token); user_context.reset(user)
    return wrapped


def conversation_scope(function):
    @functools.wraps(function)
    def wrapped(conversation_id, user_key, *args, **kwargs):
        user=user_context.set(str(user_key)); conversation=conversation_context.set(conversation_id)
        try:return function(conversation_id,user_key,*args,**kwargs)
        finally:user_context.reset(user);conversation_context.reset(conversation)
    return wrapped


def observe_specialized(route, provider, endpoint=None):
    """Audit specialist calls (images, speech) that do not go through the router."""
    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            if not configured(): return function(*args,**kwargs)
            started=time.monotonic(); error=None
            is_audio=route=="audio"
            from .localize import tts_model
            model=(kwargs.get("model_id") or (args[3] if len(args)>3 else "") or tts_model()) if is_audio else settings.ARVAN_IMAGE_MODEL
            prompt=args[0] if is_audio else (args[1] if len(args)>1 else kwargs.get("prompt",""))
            try:return function(*args,**kwargs)
            except Exception as exc:error=exc;raise
            finally:
                try: cfg=gateway_settings()
                except Exception: cfg={"capture_messages":False,"log_char_limit":256}
                _audit({"id":str(uuid.uuid4()),"timestamp":datetime.now(timezone.utc).isoformat(),
                    "user_id":user_context.get(),"job_id":job_context.get(),"conversation_id":conversation_context.get(),
                    "route":route,"endpoint":endpoint or ("v1/text-to-speech" if is_audio else "chat/completions"),
                    "requested_model":model,"actual_model":None,"provider":provider,"transport":"preserved-specialist",
                    "status":"failed" if error else "success","latency_ms":round((time.monotonic()-started)*1000),
                    "input_tokens":None,"output_tokens":None,"cost":None,"http_status":None,
                    "retry_count":0,"fallback_history":[],"error":safe(str(error),500) if error else None,
                    "request_message":safe(prompt,cfg["log_char_limit"]) if cfg["capture_messages"] else None,
                    "response_message":"Binary media omitted" if not error else None})
        return wrapped
    return decorate
