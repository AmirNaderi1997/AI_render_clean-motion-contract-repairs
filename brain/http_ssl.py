"""Shared verified TLS context for stdlib HTTP clients."""
from __future__ import annotations

import ssl


def ssl_context() -> ssl.SSLContext:
    """Use certifi when framework Python cannot discover the macOS CA store."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()
