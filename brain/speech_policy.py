"""Language-aware casting. Metadata is evidence, not a claim of subjective quality.

No synthesis, retries or provider fallbacks happen here. Unsupported voices fail
before a billable request. Gateway routes still own execution and permissions.
"""
from __future__ import annotations

import os
import json
import hashlib
import re
import threading
import time

_cache: tuple[str, float, list[dict]] = ("", 0, [])
_lock = threading.Lock()
FA = {"fa", "fas", "per", "persian", "farsi", "fa-ir", "iranian persian"}


def persian(text: str = "", language: str = "") -> bool:
    if language:
        return language.strip().lower().replace("_", "-") in FA
    # Arabic script alone is not evidence of Persian. Persian-specific letters
    # or common Persian function words provide a conservative text fallback.
    return bool(re.search(r"[پچژگکی]|(?:^|\s)(?:این|برای|است|را|می)(?:\s|‌|$)", text))


def languages(row: dict) -> set[str]:
    values = row.get("languages", row.get("supported_languages", [])) or []
    if isinstance(values, str):
        values = [values]
    result = {str(v.get("language_id", v.get("language", "")) if isinstance(v, dict) else v).lower().replace("_", "-") for v in values}
    labels = row.get("labels") or {}
    result.add(str(labels.get("language", row.get("language", ""))).lower())
    result.update(str(v.get("language", "")).lower() for v in row.get("verified_languages", []) if isinstance(v, dict))
    return result


def choose_voice(voices: list[dict], context: str = "", preferred: str = "") -> str:
    """Rank native Persian voices by explicit use-case metadata; never by name."""
    eligible = [v for v in voices if languages(v) & FA and (v.get("voice_id") or v.get("id"))
                and v.get("available", True) and v.get("enabled", True)]
    if not eligible:
        raise ValueError("هیچ صدای فارسیِ تأییدشده‌ای موجود نیست؛ یک گویندهٔ فارسی در تنظیمات صدا ثبت کنید.")
    context = context.casefold()
    for pattern, tags in ((r"product|commercial|تبلیغ|محصول|فروش", " advertisement commercial energetic"),
                          (r"explain|localiz|document|آموزش|توضیح|مستند", " narration educational informative calm"),
                          (r"female|زن|خانم", " female"), (r"male|مرد|آقا", " male")):
        if re.search(pattern, context):
            context += tags
    def score(v):
        labels = v.get("labels") or {}
        tags = " ".join(str(labels.get(k, "")) for k in ("use_case", "description", "accent", "gender")).casefold()
        # A user's explicit, language-compatible choice wins. Otherwise match
        # the creative brief without guessing the speaker's gender from a name.
        tokens = set(re.findall(r"\w+", context))
        return (int((v.get("voice_id") or v.get("id")) == preferred),
                sum(token in tags for token in tokens if len(token) > 2),
                int(any(str(x.get("language", "")).lower() in FA for x in v.get("verified_languages", []) if isinstance(x, dict))))
    selected = max(eligible, key=score)
    return str(selected.get("voice_id") or selected["id"])


def eleven_voices() -> list[dict]:
    """Read-only voice discovery via the existing mandatory relay, cached 5 min."""
    global _cache
    # An operator-reviewed catalog can be used when the relay does not expose
    # voice discovery. It contains public IDs/metadata only, never credentials.
    from app import lm_store
    configured = lm_store.records("settings").get("speech_casting", {}).get("voices", [])
    native = [v for v in configured if v.get("provider") == "elevenlabs"]
    if native:
        return native
    if not os.environ.get("ELEVENLABS_PROXY_URL", "").strip():
        return []  # Resellers do not expose the account's ElevenLabs catalog.
    with _lock:
        import httpx
        from .elevenlabs_transport import url
        key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        if not key:
            raise ValueError("برای کشف گویندهٔ فارسی، کلید و پراکسی ElevenLabs را تنظیم کنید.")
        endpoint = url("v1/voices")
        scope = hashlib.sha256(f"{endpoint}|{key}".encode()).hexdigest()
        if scope == _cache[0] and time.monotonic() < _cache[1]:
            return _cache[2]
        response = httpx.get(endpoint, headers={"xi-api-key": key}, timeout=20)
        if response.status_code == 404:
            raise ValueError("پراکسی فهرست صداها را ارائه نمی‌کند؛ کاتالوگ گویندگان فارسی را در تنظیمات AI ثبت کنید.")
        response.raise_for_status()
        voices = response.json().get("voices", [])
        if not isinstance(voices, list):
            raise ValueError("Invalid ElevenLabs voice catalog")
        _cache = (scope, time.monotonic() + 300, voices)
        return voices


def eleven_cast(text: str, voice: str = "", model: str = "", *, language: str = "", context: str = "") -> tuple[str, str]:
    if not persian(text, language):
        return voice, model
    # v2/Flash/Turbo do not support Persian. v3's fa support is documented;
    # newer models must be verified before being added to this allow-list.
    model = "eleven_v3"
    preferred = os.environ.get("PERSIAN_ELEVENLABS_VOICE_ID", "").strip() or voice
    voices = eleven_voices()
    if not voices and not os.environ.get("ELEVENLABS_PROXY_URL", "").strip() and preferred:
        return preferred, model
    return choose_voice(voices, context, preferred), model


def identity(text: str, voice: str, model: str, *, language: str = "", context: str = "") -> str:
    """Actual casting belongs in the cache key, not the old English default."""
    if not persian(text, language):
        return f"{voice}|{model}"
    selected, model = eleven_cast(text, voice, model, language=language, context=context)
    return json.dumps(["casting-v1", model, selected, "fa"], ensure_ascii=False)
