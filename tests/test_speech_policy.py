import pytest

from brain import speech_policy as policy


def voice(vid, language="fa", use_case="narration"):
    return {"voice_id": vid, "provider": "elevenlabs", "languages": [language], "labels": {"use_case": use_case}}


def test_language_and_native_casting():
    assert policy.persian("این یک تست است")
    assert policy.persian("Hello", "fa-IR")
    assert not policy.persian("Hello", "en")
    assert not policy.persian("مرحبا بالعالم")
    voices = [voice("english", "en"), voice("teacher"), voice("sales", use_case="commercial energetic")]
    assert policy.choose_voice(voices, "تبلیغ محصول") == "sales"
    assert policy.choose_voice(voices, "آموزشی") == "teacher"
    assert policy.choose_voice(voices, preferred="english") != "english"
    with pytest.raises(ValueError, match="فارسی"):
        policy.choose_voice([voice("english", "en")])


def test_native_persian_never_uses_v2(monkeypatch):
    monkeypatch.setattr(policy, "eleven_voices", lambda: [voice("native")])
    assert policy.eleven_cast("سلام", "Liam", "eleven_multilingual_v2", language="fa") == ("native", "eleven_v3")


def test_google_model_metadata_and_voice(monkeypatch):
    item = {"id": "registered-google-tts", "speech_provider": "google", "supported_languages": ["fa"],
            "voices": [{"voice_id": "registered-voice", "labels": {"use_case": "narration"}}]}
    assert policy.gateway_cast(item, "برای شما", "elevenlabs-id") == {"voice": "registered-voice"}
    item["supported_languages"] = ["en"]
    with pytest.raises(ValueError):
        policy.gateway_cast(item, "برای شما", "elevenlabs-id")


def test_gateway_skips_incompatible_before_any_submission(monkeypatch):
    from app import lm_store
    from brain import lm_gateway
    monkeypatch.setattr(lm_store, "records", lambda table: {})
    monkeypatch.setattr(lm_gateway, "model_allowed", lambda mid: True)
    models = {
        "old": {"id": "old", "enabled": True, "verified": ["speech"], "speech_provider": "elevenlabs", "supported_languages": ["en"]},
        "good": {"id": "good", "enabled": True, "verified": ["speech"], "speech_provider": "google", "supported_languages": ["fa"], "voices": [voice("google") ]},
    }
    mid, body = policy.gateway_choice({"models": ["old", "good"]}, models, "سلام", "Liam", language="fa")
    assert mid == "good" and body["voice"] == "google"
    with pytest.raises(ValueError, match="Routing"):
        policy.gateway_choice({"models": ["old"]}, models, "سلام", "Liam", language="fa")


def test_no_paid_attempt_when_casting_invalid(monkeypatch):
    from brain import lm_gateway
    monkeypatch.setattr(lm_gateway, "defaults", lambda: {"narration": {"enabled": True, "models": ["v2"]}})
    monkeypatch.setattr(lm_gateway, "gateway_settings", lambda: {"enabled": True, "capture_messages": False, "log_char_limit": 6000})
    monkeypatch.setattr(lm_gateway.store, "records", lambda table: {})
    monkeypatch.setattr(lm_gateway, "_audit", lambda record: None)
    monkeypatch.setattr(lm_gateway, "_client", lambda *a: pytest.fail("must not submit media"))
    with pytest.raises(ValueError):
        lm_gateway.speech("narration", "متن فارسی", "Liam")


def test_casting_cache_identity_changes_with_voice(monkeypatch):
    from brain import lm_gateway
    monkeypatch.setattr(lm_gateway, "configured", lambda: False)
    monkeypatch.setattr(policy, "eleven_voices", lambda: [voice("first"), voice("second")])
    first = policy.identity("سلام", "first", "eleven_multilingual_v2", language="fa")
    second = policy.identity("سلام", "second", "eleven_multilingual_v2", language="fa")
    assert first != second
    assert "eleven_v3" in first and "eleven_multilingual_v2" not in first


def test_admin_registration_does_not_bless_untested_model(monkeypatch):
    from app.routers import lm_admin
    from fastapi import HTTPException
    monkeypatch.setattr(lm_admin.store, "records", lambda table: {"untested": {"declared": ["speech"]}})
    body = lm_admin.SpeechCasting(models={"untested": {"speech_provider": "google", "supported_languages": ["fa"]}})
    with pytest.raises(HTTPException) as exc:
        lm_admin.save_speech_casting(body)
    assert exc.value.status_code == 422


def test_admin_casting_uses_existing_admin_permission():
    from app.routers import lm_admin
    routes = [r for r in lm_admin.router.routes if r.path.endswith("/speech-casting")]
    assert len(routes) == 2
    assert all(any(dep.call is lm_admin.admin for dep in route.dependant.dependencies) for route in routes)
