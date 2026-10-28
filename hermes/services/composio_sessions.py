"""Server-only Composio Sessions boundary. No external action execution yet.

Identity and session references are never accepted from a browser or model.
Encrypted Hermes settings are the persistence layer, not another user database.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import hashlib
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from hermes.config import settings, settings_row_id
from hermes.database import get_row, save_row
from hermes.security import decrypt_setting, encrypt_setting, utcnow


def identity(user_id: str) -> str:
    if not settings.COMPOSIO_INSTANCE_ID:
        raise HTTPException(503, detail={"code": "COMPOSIO_INSTANCE_ID_REQUIRED"})
    digest = hashlib.sha256(f"{settings.COMPOSIO_INSTANCE_ID}:{user_id}".encode()).hexdigest()
    return f"editorgpt_{digest}"


def allowed_toolkits() -> list[str]:
    return sorted({slug.strip().lower() for slug in settings.COMPOSIO_TOOLKITS.split(",")
                   if slug.strip() and slug.strip().isascii() and slug.strip().replace("_", "").isalnum()})


@contextmanager
def sdk():
    if not settings.COMPOSIO_API_KEY:
        raise HTTPException(503, detail={"code": "COMPOSIO_NOT_CONFIGURED"})
    try:
        from composio import Composio
    except ImportError as exc:
        raise HTTPException(503, detail={"code": "COMPOSIO_SDK_NOT_INSTALLED"}) from exc
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        yield Composio(api_key=settings.COMPOSIO_API_KEY, timeout=20, max_retries=0,
                       allow_tracking=False, http_client=client, file_upload_dirs=False,
                       dangerously_allow_auto_upload_download_files=False)


async def state(user_id: str) -> dict:
    row = await get_row("settings", settings_row_id(user_id, "composio"))
    if row and str(row["user_id"]) != user_id:
        raise HTTPException(404, detail={"code": "COMPOSIO_SETTINGS_NOT_FOUND"})
    return {key: decrypt_setting(value) for key, value in
            (row or {}).get("encrypted_credentials", {}).items()}


async def save_state(user_id: str, values: dict):
    row_id = settings_row_id(user_id, "composio")
    row = await get_row("settings", row_id)
    if row and str(row["user_id"]) != user_id:
        raise HTTPException(404, detail={"code": "COMPOSIO_SETTINGS_NOT_FOUND"})
    now = utcnow()
    await save_row("settings", {"id": row_id,
        "user_id": int(user_id) if user_id.isdigit() else user_id, "provider": "composio",
        "encrypted_credentials": {key: encrypt_setting(value) for key, value in values.items()},
        "created_at": row["created_at"] if row else now, "updated_at": now})


async def status(user_id: str) -> dict:
    values = await state(user_id)
    return {"configured": bool(settings.COMPOSIO_API_KEY and settings.COMPOSIO_INSTANCE_ID),
            "enabled": values.get("enabled") == "true", "applications": allowed_toolkits(),
            "session_saved": bool(values.get("session_id")), "external_actions_enabled": False}


async def set_enabled(user_id: str, enabled: bool):
    values = await state(user_id)
    values["enabled"] = "true" if enabled else "false"
    await save_state(user_id, values)
    return await status(user_id)


async def session_id(user_id: str) -> str:
    values = await state(user_id)
    if values.get("enabled") != "true":
        raise HTTPException(409, detail={"code": "COMPOSIO_DISABLED"})
    if values.get("session_id"):
        # Fail closed after an administrator changes namespace or tool policy.
        if values.get("identity") != identity(user_id) or values.get("policy") != ",".join(allowed_toolkits()):
            raise HTTPException(409, detail={"code": "COMPOSIO_POLICY_CHANGED_RECONNECT_REQUIRED"})
        return values["session_id"]

    def create():
        with sdk() as client:
            return client.sessions.create(user_id=identity(user_id),
                toolkits={"enable": allowed_toolkits()}, sandbox={"enable": False},
                proxy_execute=False, manage_connections=False,
                tags={"enable": ["readOnlyHint"]}).session_id
    reference = await remote(create)
    values.update(session_id=reference, identity=identity(user_id), policy=",".join(allowed_toolkits()))
    await save_state(user_id, values)
    return reference


async def remote(call):
    try:
        return await asyncio.to_thread(call)
    except HTTPException:
        raise
    except Exception:
        # Never send raw SDK exception text, URLs, headers or response bodies.
        raise HTTPException(502, detail={"code": "COMPOSIO_CONNECTION_FAILED"}) from None


async def connections(user_id: str) -> dict:
    reference = await session_id(user_id)
    def inspect():
        with sdk() as client:
            result = client.sessions.use(reference).toolkits(toolkits=allowed_toolkits(), limit=50)
            items = []
            for item in result.items:
                if item.slug not in allowed_toolkits():
                    continue
                account = item.connection.connected_account if item.connection else None
                items.append({"application": item.slug, "name": item.name,
                              "connected": bool(item.connection and item.connection.is_active),
                              "status": account.status if account else "NOT_CONNECTED"})
            return {"applications": items}
    return await remote(inspect)


async def connect(user_id: str, toolkit: str) -> dict:
    if toolkit not in allowed_toolkits():
        raise HTTPException(422, detail={"code": "COMPOSIO_APPLICATION_NOT_ALLOWED"})
    callback = settings.COMPOSIO_CALLBACK_URL
    parsed = urlsplit(callback)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(503, detail={"code": "COMPOSIO_HTTPS_CALLBACK_REQUIRED"})
    reference = await session_id(user_id)
    def authorize():
        with sdk() as client:
            request = client.sessions.use(reference).authorize(toolkit, callback_url=callback)
            url = urlsplit(request.redirect_url or "")
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise HTTPException(502, detail={"code": "COMPOSIO_INVALID_AUTHORIZATION_URL"})
            # This is a provider-hosted authorization link, never the session MCP URL.
            return {"redirect_url": request.redirect_url, "status": "AUTHORIZATION_REQUIRED"}
    return await remote(authorize)
