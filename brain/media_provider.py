"""Provider-neutral media generation adapter with registry and local fixture provider."""
from __future__ import annotations

import hashlib
import io
import logging
import math
import os
import random
import subprocess
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class MediaResult:
    file_path: str
    source: str
    cost_usd: Optional[float] = 0.0
    metadata: dict = field(default_factory=dict)
    generation_id: str = ""
    width: int = 0
    height: int = 0
    duration_s: float = 0.0
    fps: int = 0


class ProviderAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def generate_image(self, prompt: str, aspect: str, output_dir: Path) -> MediaResult:
        ...

    @abstractmethod
    def generate_video(self, prompt: str, duration: float, aspect: str, output_dir: Path) -> MediaResult:
        ...

    @property
    def capabilities(self) -> list[str]:
        return ["image", "video"]

    @property
    def has_key(self) -> bool:
        key_var = f"CONTENT_PROVIDER_{self.name.upper()}_KEY"
        return bool(os.environ.get(key_var))


def _retry_with_backoff(fn, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            if attempt == max_retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            log.warning("attempt %d failed (%s), retrying in %.1fs", attempt + 1, exc, wait)
            time.sleep(wait)


def _parse_resolution(aspect: str) -> tuple[int, int]:
    mapping = {
        "9:16": (1080, 1920),
        "1:1": (1080, 1080),
        "16:9": (1920, 1080),
        "4:5": (1080, 1350),
    }
    return mapping.get(aspect, (1080, 1920))


def still_to_motion_video(
    image_path: Path,
    output_dir: Path,
    duration: float,
    aspect: str,
    *,
    generation_id: str = "",
    cost_usd: Optional[float] = 0.0,
    source: str = "image_motion",
    metadata: Optional[dict] = None,
) -> MediaResult:
    """Turn a generated still into a bounded, editable H.264 timeline source."""
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) \
            or not math.isfinite(duration) or duration <= 0:
        raise ValueError("video duration must be a positive finite number")
    still = Path(image_path)
    if not still.is_file():
        raise FileNotFoundError(f"image source not found: {still}")
    duration_s = min(float(duration), 30.0)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generation_id = generation_id or uuid.uuid4().hex[:12]
    width, height = _parse_resolution(aspect)
    fps = 30
    frames = max(1, round(duration_s * fps))
    out_path = output_dir / f"motion_{generation_id}.mp4"
    zoom_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0xf4f4f1,"
        f"zoompan=z='min(1+0.0002*on,1.08)':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={width}x{height}:fps={fps},format=yuv420p"
    )
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(still),
        "-vf", zoom_filter, "-frames:v", str(frames),
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-movflags", "+faststart", str(out_path),
    ], capture_output=True, check=True, timeout=max(60, round(duration_s * 12)))
    return MediaResult(
        file_path=str(out_path),
        source=source,
        cost_usd=cost_usd,
        generation_id=generation_id,
        width=width,
        height=height,
        duration_s=round(frames / fps, 3),
        fps=fps,
        metadata={**(metadata or {}), "still_path": str(still), "motion": "subtle_zoompan"},
    )


class LocalFixtureProvider(ProviderAdapter):
    """Generates placeholder colored frames/video with ffmpeg. No API keys needed."""

    name = "local_fixture"

    @property
    def has_key(self) -> bool:
        return True

    def generate_image(self, prompt: str, aspect: str, output_dir: Path) -> MediaResult:
        w, h = _parse_resolution(aspect)
        gen_id = uuid.uuid4().hex[:12]
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"fixture_{gen_id}.png"

        color = "#{:06x}".format(random.randint(0x222222, 0xCCCCCC))
        label = prompt[:40].replace("'", "").replace('"', "")

        def _gen():
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c={color}:s={w}x{h}:d=1",
                "-vf", f"drawtext=text='{label}':fontsize=36:fontcolor=white:x=(w-tw)/2:y=(h-th)/2",
                "-frames:v", "1",
                str(out_path),
            ], capture_output=True, check=True, timeout=15)

        try:
            _retry_with_backoff(_gen, max_retries=2)
        except Exception:
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c={color}:s={w}x{h}:d=1",
                "-frames:v", "1",
                str(out_path),
            ], capture_output=True, check=True, timeout=15)

        return MediaResult(
            file_path=str(out_path),
            source="local_fixture",
            cost_usd=0.0,
            generation_id=gen_id,
            width=w, height=h,
            duration_s=0.0, fps=0,
            metadata={"prompt": prompt, "color": color},
        )

    def generate_video(self, prompt: str, duration: float, aspect: str, output_dir: Path) -> MediaResult:
        w, h = _parse_resolution(aspect)
        gen_id = uuid.uuid4().hex[:12]
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"fixture_{gen_id}.mp4"
        fps = 30

        color = "#{:06x}".format(random.randint(0x222222, 0xCCCCCC))
        dur = max(0.5, min(duration, 30.0))

        def _gen():
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i",
                f"color=c={color}:s={w}x{h}:d={dur}:r={fps}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-t", str(dur),
                str(out_path),
            ], capture_output=True, check=True, timeout=60)

        _retry_with_backoff(_gen, max_retries=3)

        return MediaResult(
            file_path=str(out_path),
            source="local_fixture",
            cost_usd=0.0,
            generation_id=gen_id,
            width=w,
            height=h,
            duration_s=round(dur, 2),
            fps=fps,
            metadata={"prompt": prompt, "color": color},
        )


class ArvanImageProvider(ProviderAdapter):
    """Generate stills with the configured OpenAI-compatible image endpoint.

    Reels and Stories use those generated stills as short, gently animated
    clips. This keeps the feature usable when no dedicated video model is
    configured and records the provider's image cost as unknown when its API
    response does not include billing data.
    """

    name = "arvan_image"

    @property
    def capabilities(self) -> list[str]:
        return ["image", "motion_video_from_image"]

    @property
    def has_key(self) -> bool:
        from app.config import settings
        return bool(settings.ARVAN_AI_API_KEY and settings.ARVAN_IMAGE_MODEL)

    @staticmethod
    def _client_config() -> tuple[str, Optional[str], str]:
        from app.config import settings
        api_key = settings.ARVAN_AI_API_KEY
        base_url = settings.ARVAN_AI_API_BASE.rstrip("/")
        model = settings.ARVAN_IMAGE_MODEL
        if not api_key or not model:
            raise RuntimeError("Arvan image generation requires ARVAN_IMAGE_MODEL and credentials; upload real images instead")
        return api_key, base_url, model

    def generate_image(self, prompt: str, aspect: str, output_dir: Path) -> MediaResult:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("image prompt must not be empty")
        output_dir.mkdir(parents=True, exist_ok=True)
        api_key, base_url, model = self._client_config()

        aspect_note = {
            "9:16": (
                "Create one continuous photograph composed for a central vertical 9:16 crop "
                "from this square image. Keep every essential face, hand, and action within "
                "the middle 55% of the image width. No side panels, borders, or seams."
            ),
            "4:5": "Compose for a portrait 4:5 crop, keeping the main subject near the center.",
            "1:1": "Compose for a square 1:1 frame.",
            "16:9": "Compose for a wide 16:9 crop, keeping the main subject near the center.",
        }.get(aspect, "Keep the main subject centered with safe space around it.")
        request_prompt = (
            f"{prompt.strip()}\n\n{aspect_note} Do not add captions, lettering, "
            "logos, or legible text on paper, clothing, signs, or screens."
        )
        from .llm import _arvan_request
        response = _arvan_request({
            "model": model,
            "messages": [{"role": "user", "content": request_prompt}],
            "modalities": ["image", "text"],
            "max_tokens": 1000,
        }, timeout_seconds=180)
        choices = response.get("choices") or []
        message = choices[0].get("message", {}) if choices else {}
        images = message.get("images") or []
        if not images and isinstance(message.get("content"), list):
            images = [part for part in message["content"] if part.get("type") == "image_url"]
        data_url = (images[0].get("image_url") or {}).get("url", "") if images else ""
        if not isinstance(data_url, str) or not data_url.startswith(("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,")):
            raise RuntimeError("Arvan returned no inline image; no placeholder was substituted")
        encoded = data_url.split(",", 1)[1]
        if len(encoded) > 40 * 1024 * 1024:
            raise RuntimeError("Arvan returned an oversized image")
        selected_model = model

        import base64
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
            from PIL import Image
            image = Image.open(io.BytesIO(image_bytes))
            image.load()
            width, height = image.size
            out_path = output_dir / f"arvan_{uuid.uuid4().hex[:12]}.png"
            image.convert("RGB").save(out_path, format="PNG")
        except Exception as exc:
            raise RuntimeError(f"image provider returned an invalid image: {exc}") from exc

        return MediaResult(
            file_path=str(out_path),
            source="arvan_image",
            cost_usd=None,
            generation_id=out_path.stem.removeprefix("arvan_"),
            width=width,
            height=height,
            metadata={"prompt": prompt, "model": selected_model,
                      "requested_model": model, "fallback_used": selected_model != model,
                      "aspect": aspect, "billing_reported": False},
        )

    def generate_video(self, prompt: str, duration: float, aspect: str,
                       output_dir: Path) -> MediaResult:
        still = self.generate_image(prompt, aspect, output_dir)
        return still_to_motion_video(
            still.file_path, output_dir, duration, aspect,
            generation_id=still.generation_id, cost_usd=still.cost_usd,
            source="arvan_image_motion", metadata=still.metadata,
        )


_registry: dict[str, ProviderAdapter] = {}


def register_provider(name: str, adapter: ProviderAdapter) -> None:
    adapter.name = name
    _registry[name] = adapter


def get_provider(name: str) -> ProviderAdapter:
    if name != "local_fixture":
        name = "arvan_image"
    if name not in _registry:
        raise KeyError(f"unknown provider: {name!r}. registered: {list(_registry.keys())}")
    return _registry[name]


def list_providers() -> list[dict]:
    return [
        {"name": name, "capabilities": adapter.capabilities,
         "has_key": adapter.has_key, "key_configured": adapter.has_key}
        for name, adapter in _registry.items()
    ]


register_provider("local_fixture", LocalFixtureProvider())
register_provider("arvan_image", ArvanImageProvider())
