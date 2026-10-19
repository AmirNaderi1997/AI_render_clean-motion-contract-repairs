"""Shared routing helpers for direct or Vercel-relayed ElevenLabs calls."""
from __future__ import annotations

import os

DIRECT_BASE_URL = "https://api.elevenlabs.io"


def base_url() -> str:
    """Require the configured HTTPS relay; never bypass it on failures."""
    proxy = os.environ.get("ELEVENLABS_PROXY_URL", "").strip().rstrip("/")
    if not proxy or proxy == DIRECT_BASE_URL or not proxy.startswith("https://"):
        raise RuntimeError("ELEVENLABS_PROXY_URL must configure the HTTPS Vercel relay")
    return proxy


def url(path: str) -> str:
    return f"{base_url()}/{path.lstrip('/')}"
