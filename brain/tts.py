"""Text-to-speech providers for generated narration."""
from __future__ import annotations

import logging
import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)
from .lm_gateway import observe_specialized


@dataclass
class TTSResult:
    file_path: str
    duration_s: float
    cost_usd: float | None = None
    provider: str = ""


_ELEVENLABS_TIMEOUT_SECONDS = 10


def _get_audio_duration(path: str) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=10,
        )
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def _configured_provider(provider: str | None = None) -> str:
    """Installation policy: never silently switch speech providers."""
    return "disabled" if provider == "disabled" else "elevenlabs"


@observe_specialized("audio", "elevenlabs-vercel-relay")
def _generate_elevenlabs(
    text: str, output_path: str, voice_id: str = "", model_id: str = "",
) -> None:
    """Generate one MP3 through ElevenLabs with a bounded network timeout."""
    from . import lm_gateway
    if lm_gateway.configured():
        Path(output_path).write_bytes(lm_gateway.speech('narration',text,voice_id or os.environ.get('ELEVENLABS_VOICE_ID','')))
        return
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    voice_id = voice_id.strip() or os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    model_id = model_id.strip() or os.environ.get(
        "ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"
    ).strip()
    if not api_key or not voice_id:
        raise RuntimeError("ElevenLabs is not configured with API key and voice ID")
    try:
        import httpx
        from brain.elevenlabs_transport import url as elevenlabs_url

        response = httpx.post(
            elevenlabs_url(f"v1/text-to-speech/{voice_id}"),
            headers={"xi-api-key": api_key, "accept": "audio/mpeg"},
            json={"text": text, "model_id": model_id},
            # Short connect timeout to fail fast, longer read timeout because
            # ElevenLabs only responds after synthesizing the whole clip.
            timeout=httpx.Timeout(
                float(os.environ.get("ELEVENLABS_READ_TIMEOUT", "60")),
                connect=float(os.environ.get("ELEVENLABS_CONNECT_TIMEOUT", _ELEVENLABS_TIMEOUT_SECONDS)),
            ),
        )
        response.raise_for_status()
        Path(output_path).write_bytes(response.content)
    except Exception as exc:
        Path(output_path).unlink(missing_ok=True)
        response = getattr(exc, "response", None)
        if getattr(response, "status_code", None) == 402:
            try:
                detail = response.json().get("detail", {})
            except Exception:
                detail = {}
            if isinstance(detail, dict) and detail.get("code") == "paid_plan_required":
                raise RuntimeError(
                    "This Persian ElevenLabs voice requires a paid plan for API use. "
                    "Choose an API-enabled Persian ElevenLabs voice."
                ) from exc
            raise RuntimeError("ElevenLabs request failed (HTTP 402)") from exc
        raise RuntimeError(f"ElevenLabs request failed ({type(exc).__name__})") from exc


def generate_narration(
    text: str,
    output_dir: Path,
    voice_id: str = "",
    model_id: str = "",
    rate: str = "+0%",
    provider: str | None = None,
    fallback_voice_id: str = "",
) -> TTSResult:
    """Generate narration using the requested provider without silent substitution."""
    if not text.strip():
        raise ValueError("narration text is empty")

    provider = _configured_provider(provider)
    if provider == "disabled":
        log.info("narration skipped because TTS_PROVIDER=disabled")
        return TTSResult(file_path="", duration_s=0.0, cost_usd=0.0, provider="disabled")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"narration_{uuid.uuid4().hex[:12]}.mp3"
    from .localize import tts_voice, tts_model
    try:
        _generate_elevenlabs(text, str(out_file), voice_id=voice_id or tts_voice(), model_id=model_id or tts_model())
    except Exception:
        out_file.unlink(missing_ok=True)
        raise

    if not out_file.exists() or out_file.stat().st_size == 0:
        raise RuntimeError(f"{provider} returned empty audio")

    duration = _get_audio_duration(str(out_file))
    if duration <= 0:
        out_file.unlink(missing_ok=True)
        raise RuntimeError(f"{provider} returned audio with no playable duration")
    log.info("TTS generated with %s: %s (%.1fs)", provider, out_file.name, duration)
    return TTSResult(
        file_path=str(out_file), duration_s=duration,
        cost_usd=None, provider=provider,
    )
