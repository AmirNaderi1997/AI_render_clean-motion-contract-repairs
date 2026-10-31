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
