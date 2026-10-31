from pathlib import Path
import base64
import io

import pytest
from PIL import Image

from app.config import Settings
from brain import llm
from brain.ai_provider import ArvanProvider, get_provider
from brain.elevenlabs_transport import base_url
from brain.media_provider import get_provider as media_provider, list_providers
from brain.tts import _configured_provider, generate_narration


def test_stale_configuration_cannot_override_policy():
    settings = Settings(_env_file=None, APP_ENV="development", AI_PROVIDER="retired",
                        LLM_PROVIDER="retired", VISION_PROVIDER="retired",
                        CONTENT_TTS_PROVIDER="retired")
    assert settings.LLM_PROVIDER == settings.VISION_PROVIDER == "arvan"
    assert settings.CONTENT_TTS_PROVIDER == settings.TTS_PROVIDER == "elevenlabs"
    assert isinstance(get_provider("retired"), ArvanProvider)
    assert _configured_provider("retired") == "elevenlabs"


def test_text_has_no_external_fallback(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Arvan unavailable")
    monkeypatch.setattr(llm, "_arvan_call", fail)
    with pytest.raises(RuntimeError, match="Arvan unavailable"):
        llm.chat_json("system", "user", provider="retired")


def test_vision_routes_only_to_arvan(monkeypatch):
    calls = []
    def call(*args, **kwargs):
        calls.append(args)
        return '{"ok":true}', llm.LLMUsage(model="vision")
    monkeypatch.setattr(llm, "_arvan_vision_call", call)
    result, _ = llm.chat_vision("system", "user", images=[b"image"], return_json=True)
    assert result == {"ok": True}
    assert calls[0][2] == [b"image"]


def test_relay_is_required(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_PROXY_URL", raising=False)
    with pytest.raises(RuntimeError, match="relay"):
        base_url()
    monkeypatch.setenv("ELEVENLABS_PROXY_URL", "https://relay.vercel.app/api/elevenlabs/")
    assert base_url() == "https://relay.vercel.app/api/elevenlabs"


def test_all_narration_uses_localize_voice(monkeypatch, tmp_path):
    from brain import tts
    from brain.localize import tts_voice, tts_model
    calls = []
    def generate(text, output, **kwargs):
        calls.append(kwargs)
        Path(output).write_bytes(b"audio")
    monkeypatch.setattr(tts, "_generate_elevenlabs", generate)
    monkeypatch.setattr(tts, "_get_audio_duration", lambda path: 1.5)
    result = generate_narration("hello", tmp_path, provider="retired")
    assert result.provider == "elevenlabs"
    assert calls == [{"voice_id": tts_voice(), "model_id": tts_model()}]


def test_saved_media_provider_routes_to_arvan():
    assert media_provider("retired_image").name == "arvan_image"
    assert {item["name"] for item in list_providers()} == {"arvan_image", "local_fixture"}


def test_arvan_image_contract(monkeypatch, tmp_path):
    image = io.BytesIO()
    Image.new("RGB", (32, 32), "blue").save(image, format="PNG")
    data = "data:image/png;base64," + base64.b64encode(image.getvalue()).decode()
    calls = []
    def request(payload, **kwargs):
        calls.append(payload)
        return {"choices": [{"message": {"images": [{"image_url": {"url": data}}]}}]}
    monkeypatch.setattr(llm, "_arvan_request", request)
    monkeypatch.setattr(llm.settings, "ARVAN_AI_API_KEY", "test")
    result = media_provider("arvan_image").generate_image("blue circle", "9:16", tmp_path)
    assert result.source == "arvan_image"
    assert Path(result.file_path).is_file()
    assert calls[0]["modalities"] == ["image", "text"]


def test_provider_labels_do_not_introduce_direct_endpoints_outside_central_adapter():
    import re
    root = Path(__file__).parents[1]
    retired = ("sar" + "ovi", "jar" + "vis")
    for directory in ("app", "brain", "web/src"):
        for path in (root / directory).rglob("*"):
            if path.suffix in {".py", ".tsx", ".ts"}:
                if path == root / "brain" / "lm_direct.py":
                    # The one sanctioned place for direct provider endpoints: admin-controlled fallbacks used only
                    # after LM API fails (see docs/CREATIVE_ENGINE_DESIGN.md and the "Direct fallbacks" admin tab).
                    continue
                if path == root / "brain" / "lm_tasks.py":
                    # These providers are now allowed only as centrally scoped
                    # Gateway identities, never as direct network endpoints.
                    assert "https://" not in path.read_text()
                    continue
                # Provider names and Custom Endpoint group IDs are valid
                # gateway metadata, not direct connections. Guard literal
                # network origins instead of banning names in the admin UI.
                origins=re.findall(r'https?://[^\s\x27\x22<>]+',path.read_text().lower())
                assert not any(name in url for name in retired for url in origins), path
