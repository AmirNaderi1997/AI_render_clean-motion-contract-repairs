"""Shared routing helpers for direct or Vercel-relayed ElevenLabs calls."""
from __future__ import annotations

import os

DIRECT_BASE_URL = "https://api.elevenlabs.io"


def base_url() -> str:
    """Return the configured API root, preserving direct access as fallback."""
    return os.environ.get("ELEVENLABS_PROXY_URL", "").strip().rstrip("/") or DIRECT_BASE_URL


def url(path: str) -> str:
    return f"{base_url()}/{path.lstrip('/')}"
