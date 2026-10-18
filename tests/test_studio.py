from __future__ import annotations

import asyncio
import json
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import studio_store
from app.studio_orchestrator import _intent, _style
from app.studio_tools import TOOLS, list_tools
from app.studio_url import PageParser, _public_url, _structured_products, _walk_json_images
from app.routers.studio import _public_event, _public_project
from brain.content_creator import _default_elevenlabs_voice, _voice_provider
from brain.localize import default_voice_provider, tts_model, tts_voice
from app.jobs import Job, _job_from_local_payload


def test_url_parser_reads_visible_product_content_and_all_image_sources():
    parser = PageParser()
    parser.feed("""
      <html><head><title>Store shell title</title><meta name="description" content="A weak meta summary"></head>
      <body><h1>Pulse X Smart Watch</h1><p>Seven day battery and water resistance.</p>
      <picture><source srcset="/large.webp 1200w, /small.webp 600w"><img src="/hero.jpg" data-src="/lazy.jpg" alt="black watch"></picture>
      <script type="application/ld+json">{"@type":"Product","name":"Pulse X","image":["/gallery-1.jpg","/gallery-2.jpg"],"offers":{"price":"99"}}</script>
      </body></html>
    """)
    assert "Pulse X Smart Watch" in parser.text
    assert any(item["url"] == "/large.webp" for item in parser.images)
    assert any(item["url"] == "/lazy.jpg" for item in parser.images)
    assert _walk_json_images(parser.structured)[-2:] == ["/gallery-1.jpg", "/gallery-2.jpg"]
    assert _structured_products(parser.structured)[0]["name"] == "Pulse X"


def test_public_url_rejects_private_and_credentials(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))])
    with pytest.raises(ValueError): _public_url("http://internal.example/product")
    with pytest.raises(ValueError): _public_url("https://user:pass@example.com/product")


def test_tool_registry_is_typed_and_has_no_shell_tool():
    names = {item["name"] for item in list_tools()}
    assert {"inspect_media", "inspect_url", "localize_video", "analyze_talking_reel", "create_storyboard", "check_render_status", "cancel_operation"} <= names
    assert "shell" not in names
    for spec in TOOLS.values():
        assert spec.input_model.model_json_schema()["additionalProperties"] is False


def test_public_payloads_never_expose_server_paths():
    project = _public_project({"state": {
        "source_assets": ["/srv/private/product.png"],
        "url_inspection": {"images": [{"file": "/srv/private/download.png", "url": "https://example.com/image.png"}]},
    }})
    assert project["state"]["source_assets"] == [{"index": 0, "name": "product.png"}]
    assert "file" not in project["state"]["url_inspection"]["images"][0]
    event = _public_event({"data": {"images": [{"file": "/srv/private/download.png", "name": "download.png"}]}})
    assert event["data"]["images"] == [{"name": "download.png"}]


def test_intent_routing_and_real_talking_style_selection():
    video = [{"kind": "video"}]
    assert _intent("این ویدیو رو فارسی کن", video, None) == "localize"
    assert _intent("یک ادیت حرفه‌ای اینستاگرامی بزن", video, None) == "talking"
    assert _intent("از این عکس‌ها یک تیزر بساز", [{"kind": "image"}], None) == "motion"
    assert _style("سبک صحبتی ۳") == "talking_3"


def test_every_tts_surface_uses_localize_elevenlabs(monkeypatch):
    monkeypatch.setenv("CONTENT_TTS_PROVIDER", "sarovi")
    monkeypatch.setenv("TTS_PROVIDER", "edge-tts")
    monkeypatch.setenv("LOCALIZE_TTS_PROVIDER", "sarovi")
    monkeypatch.setenv("LOCALIZE_VOICE_ID", "localize-voice")
    monkeypatch.setenv("LOCALIZE_TTS_MODEL", "eleven-v3-test")

    assert _voice_provider() == "elevenlabs"
    assert default_voice_provider() == "elevenlabs"
    assert _default_elevenlabs_voice("fa") == tts_voice() == "localize-voice"
    assert _default_elevenlabs_voice("en") == "localize-voice"
    assert tts_model() == "eleven-v3-test"


def test_narration_cache_records_source_text():
    source = Path(__file__).parents[1].joinpath("brain/content_creator.py").read_text()
    assert 'cached_narration[scene.index].get("narration_text")' in source
    assert '"narration_text": scene.narration_text' in source


def test_local_job_registry_keeps_generated_motion_plan(tmp_path, monkeypatch):
    from app import jobs
    monkeypatch.setattr(jobs, "JOBS_ROOT", tmp_path)
    original = Job(id="motion-job", dir=tmp_path / "motion-job", plan_data={"content_type": "reel", "segments": []})
    restored = _job_from_local_payload(original.id, original.to_dict())
    assert restored.plan_data == original.plan_data


def test_fallback_store_persists_conversation_project_version_and_event(tmp_path, monkeypatch):
    monkeypatch.setattr(studio_store, "DB_AVAILABLE", False)
    monkeypatch.setattr(studio_store, "ROOT", tmp_path)
    monkeypatch.setattr(studio_store, "FALLBACK", tmp_path / "studio.json")

    async def scenario():
        conversation = await studio_store.repo.create_conversation("user-a", "تست")
        message = await studio_store.repo.add_message(conversation["id"], "user-a", "user", "سلام")
        project = await studio_store.repo.create_project(conversation["id"], "user-a", "motion", "ویدیو", {"storyboard": {"scenes": []}})
        await studio_store.repo.update_project(project["id"], "user-a", state={"storyboard": {"scenes": [{"duration_s": 5}]}}, source="user_ui")
        event = await studio_store.repo.emit(conversation["id"], "storyboard.ready", {"project_id": project["id"]})
        restored = await studio_store.repo.get_conversation(conversation["id"], "user-a")
        events = await studio_store.repo.events(conversation["id"], "user-a", 0)
        assert message["content"] == "سلام"
        assert restored["projects"][0]["current_version"] == 2
        assert events[0]["seq"] == event["seq"] == 1
        with pytest.raises(KeyError): await studio_store.repo.get_conversation(conversation["id"], "user-b")

    asyncio.run(scenario())
