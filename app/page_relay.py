"""Backend-only page relay configuration; never included in public settings."""
import json
import os
from pathlib import Path
from app.config import settings


def config():
    url = os.getenv('SOCIAL_RELAY_URL', '')
    secret = os.getenv('SOCIAL_RELAY_SECRET', '')
    if not url or not secret:
        try:
            saved = json.loads((Path(settings.JOBS_DIR)/'ai_gateway'/'page_relay.json').read_text())
            url = url or saved.get('url', '')
            secret = secret or saved.get('secret', '')
        except (OSError, ValueError):
            pass
    if url != 'https://editorgpt-social-relay.vercel.app/api/index' or len(secret) < 32:
        return '', ''
    return url, secret
