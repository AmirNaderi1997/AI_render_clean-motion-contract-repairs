"""Direct provider fallbacks: policy, secrecy, wire formats and the gateway hook."""
import json
import os
import stat

import httpx
import pytest

from brain import lm_direct as direct
from brain import lm_gateway as gateway
from brain.lm_gateway import GatewayError


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(direct.settings, "JOBS_DIR", str(tmp_path))
    for name in list(os.environ):
        if name.startswith("DIRECT_"):
            monkeypatch.delenv(name)
    for legacy in ("ARVAN_AI_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setattr(direct.settings, legacy, "")
    return tmp_path


def ok(text="hi"):
    return {"model": "m", "choices": [{"message": {"role": "assistant", "content": text}}], "usage": {"prompt_tokens": 3, "completion_tokens": 2}}


def test_base_url_policy():
    assert direct.validate_base_url("https://api.jarvis.you/v1/") == "https://api.jarvis.you/v1"
    for bad in ("http://api.jarvis.you/v1", "https://user:pw@x.com/v1", "https://x.com/v1?key=1", "https://localhost/v1", "https://127.0.0.1/v1", "https://10.0.0.5/v1", "ftp://x.com"):
        with pytest.raises(ValueError):
            direct.validate_base_url(bad)


def test_keys_are_write_only_and_stored_privately(isolated):
    direct.set_secret("jarvis", "sk-live-1234567890abcd")
    path = isolated / "ai_gateway" / "direct_keys.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    status = direct.status()
    jarvis = next(p for p in status["providers"] if p["id"] == "jarvis")
    assert jarvis["configured"] and jarvis["key_hint"] == "…abcd" and jarvis["key_source"] == "saved"
    assert "sk-live-1234567890abcd" not in json.dumps(status)           # never returned
    direct.set_secret("jarvis", "")                                      # empty deletes
    assert not next(p for p in direct.status()["providers"] if p["id"] == "jarvis")["configured"]
    with pytest.raises(ValueError):
        direct.set_secret("nope", "x")
    with pytest.raises(ValueError):
        direct.set_secret("jarvis", "line\nbreak")


def test_legacy_env_keys_are_reused_so_nothing_is_entered_twice(monkeypatch):
    monkeypatch.setattr(direct.settings, "ARVAN_AI_API_KEY", "arvan-legacy-key-9999")
    arvan = next(p for p in direct.status()["providers"] if p["id"] == "arvan")
    assert arvan["configured"] and arvan["key_source"] == "environment"


def test_config_defaults_order_and_validation():
    cfg = direct.config()
    assert cfg["enabled"] is True and [p["id"] for p in cfg["providers"]] == ["jarvis", "sarovi", "arvan", "openai", "gemini"]
    saved = direct.save_config(False, [{"id": "gemini", "enabled": True, "base_url": "https://relay.example.vercel.app/v1beta", "model": "gemini-3.5-flash", "format": "gemini"},
                                       {"id": "jarvis", "enabled": False, "base_url": "https://api.jarvis.you/v1", "model": "X"}])
    assert saved["enabled"] is False and [p["id"] for p in saved["providers"]][:2] == ["gemini", "jarvis"]   # order kept, rest appended
    with pytest.raises(ValueError):
        direct.save_config(True, [{"id": "evil", "base_url": "https://x.com"}])
    with pytest.raises(ValueError):
        direct.save_config(True, [{"id": "jarvis", "base_url": "http://insecure.example"}])


def test_auth_schemes_and_paths(monkeypatch):
    seen = []

    def fake_post(url, headers, body, timeout):
        seen.append((url, headers, body))
        return httpx.Response(200, json=ok())

    monkeypatch.setattr(direct, "_post", fake_post)
    direct.set_secret("arvan", "arvan-key-0000"); direct.set_secret("jarvis", "jarvis-key-0000")
    cfg = {p["id"]: p for p in direct.config()["providers"]}
    direct.call(cfg["arvan"], [{"role": "user", "content": "x"}], model="GPT-5.6-Sol", tokens=50)
    direct.call(cfg["jarvis"], [{"role": "user", "content": "x"}], model="CLAUDE_SONNET_5_5", tokens=50)
    assert seen[0][0] == "https://aiapi.rafiei.co/v1/chat/completions" and seen[0][1]["Authorization"] == "apikey arvan-key-0000"
    assert seen[1][1]["Authorization"] == "Bearer jarvis-key-0000" and seen[1][2]["model"] == "CLAUDE_SONNET_5_5"


def test_gemini_native_format_round_trip(monkeypatch):
    captured = {}

    def fake_post(url, headers, body, timeout):
        captured.update(url=url, headers=headers, body=body)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "سلام"}]}}], "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2}})

    monkeypatch.setattr(direct, "_post", fake_post)
    direct.save_config(True, [{"id": "gemini", "base_url": "https://relay.example.vercel.app/v1beta", "model": "gemini-3.5-flash", "format": "gemini", "extra_header_name": "x-relay-secret"}])
    direct.set_secret("gemini", "g-key-12345678"); direct.set_secret("gemini:header", "relay-secret")
    provider = next(p for p in direct.config()["providers"] if p["id"] == "gemini")
    data = direct.call(provider, [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}], model="gemini-3.5-flash", tokens=100, temperature=0.3)
    assert captured["url"] == "https://relay.example.vercel.app/v1beta/models/gemini-3.5-flash:generateContent"
    assert captured["headers"]["x-goog-api-key"] == "g-key-12345678" and captured["headers"]["x-relay-secret"] == "relay-secret"
    assert captured["body"]["systemInstruction"]["parts"][0]["text"] == "be brief" and captured["body"]["contents"][0]["role"] == "user"
    assert data["choices"][0]["message"]["content"] == "سلام" and data["usage"]["prompt_tokens"] == 5


def test_model_selection_prefers_the_routes_own_model_for_that_provider():
    cfg = {p["id"]: p for p in direct.config()["providers"]}
    candidates = ["google:gemini-3.5-flash", "custom:DeepSeek-V4-Flash#arvancloud-all-models", "custom:CLAUDE_OPUS_5_5#jarvis-all-models"]
    assert direct.model_for(cfg["jarvis"], candidates) == "CLAUDE_OPUS_5_5"
    assert direct.model_for(cfg["arvan"], candidates) == "DeepSeek-V4-Flash"
    assert direct.model_for(cfg["gemini"], candidates) == "google/gemini-3.5-flash"      # Vercel gateway naming
    assert direct.model_for(cfg["openai"], candidates) == "gpt-4.1-mini"                  # provider default


def test_fallback_walks_providers_in_order_and_skips_failures(monkeypatch):
    calls = []

    def fake_post(url, headers, body, timeout):
        calls.append(url)
        if "jarvis" in url:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json=ok("from sarovi"))

    monkeypatch.setattr(direct, "_post", fake_post)
    direct.set_secret("sarovi", "s-key-00000000"); direct.set_secret("jarvis", "j-key-00000000")
    attempts = []
    found = direct.try_fallback([{"role": "user", "content": "x"}], candidates=[], tokens=100, temperature=None, timeout=30, extra=None, attempts=attempts)
    assert found and found[1] == "sarovi" and len(calls) == 2          # Jarvis is asked first, then Sarovi
    assert [a["http_status"] for a in attempts] == [503, 200] and attempts[0]["model"].startswith("direct:jarvis")


def test_gemini_models_ask_google_first(monkeypatch):
    calls = []
    monkeypatch.setattr(direct, "_post", lambda url, headers, body, timeout: (calls.append(url), httpx.Response(200, json=ok("g")))[1])
    for name in ("jarvis", "gemini"):
        direct.set_secret(name, name + "-key-0000000")
    found = direct.try_fallback([{"role": "user", "content": "x"}], candidates=["google:gemini-3.5-flash"], tokens=10, temperature=None, timeout=30, extra=None, attempts=[])
    assert found[1] == "gemini" and "ai-gateway" in calls[0]
    calls.clear()
    found = direct.try_fallback([{"role": "user", "content": "x"}], candidates=["custom:CLAUDE_OPUS_5_5#jarvis-all-models"], tokens=10, temperature=None, timeout=30, extra=None, attempts=[])
    assert found[1] == "jarvis"


def test_master_switch_and_missing_keys_disable_fallback(monkeypatch):
    monkeypatch.setattr(direct, "_post", lambda *a, **k: pytest.fail("must not be called"))
    assert direct.try_fallback([], candidates=[], tokens=1, temperature=None, timeout=1, extra=None, attempts=[]) is None   # no keys
    direct.set_secret("jarvis", "j-key-00000000")
    direct.save_config(False, [{"id": "jarvis", "base_url": "https://api.jarvis.you/v1", "model": "X"}])
    assert direct.try_fallback([], candidates=[], tokens=1, temperature=None, timeout=1, extra=None, attempts=[]) is None   # master off


def test_error_text_never_contains_the_key(monkeypatch):
    monkeypatch.setattr(direct, "_post", lambda *a, **k: httpx.Response(401, text="invalid key j-key-00000000 for account"))
    direct.set_secret("jarvis", "j-key-00000000")
    with pytest.raises(direct.DirectError) as err:
        direct.call(next(p for p in direct.config()["providers"] if p["id"] == "jarvis"), [], model="m", tokens=1)
    assert "j-key-00000000" not in str(err.value) and "[REDACTED]" in str(err.value)


def test_gateway_uses_direct_fallback_only_after_lm_api_fails(monkeypatch):
    """complete(): LM API 503 → direct provider answers, and the audit record says so."""
    cfg = {"enabled": True, "endpoint": "chat", "models": ["custom:CLAUDE_SONNET_5_5#jarvis-all-models"], "automatic_fallback": True,
           "max_retries": 0, "timeout": 30, "temperature": None, "max_tokens": 1000, "streaming": False}
    monkeypatch.setattr(gateway, "defaults", lambda: {"editing_agent": cfg})
    monkeypatch.setattr(gateway, "gateway_settings", lambda: {"enabled": True, "capture_messages": False, "log_char_limit": 100})
    real_records = gateway.store.records
    models = {"custom:CLAUDE_SONNET_5_5#jarvis-all-models": {"enabled": True, "available": True, "verified": ["chat"], "declared": []}}
    monkeypatch.setattr(gateway.store, "records", lambda table: models if table == "models" else real_records(table))
    audits = []
    monkeypatch.setattr(gateway, "_audit", audits.append)

    def lm_down(*args, **kwargs):
        raise GatewayError("LM API HTTP 503: exhausted", 503, True)

    monkeypatch.setattr(gateway, "_wire", lm_down)
    monkeypatch.setattr(gateway.time, "sleep", lambda s: None)
    monkeypatch.setattr(direct, "_post", lambda *a, **k: httpx.Response(200, json=ok("direct answer")))
    direct.set_secret("jarvis", "j-key-00000000")
    response, record = gateway.complete("editing_agent", [{"role": "user", "content": "hi"}])
    assert response["choices"][0]["message"]["content"] == "direct answer"
    assert record["routed_via"] == "direct:jarvis" and record["provider"] == "jarvis" and record["actual_model"] == "CLAUDE_SONNET_5_5"
    assert record["status"] == "success" and audits and any(a["model"].startswith("direct:") for a in record["fallback_history"])

    # master switch off → the original LM API error is raised, nothing is sent to providers
    direct.save_config(False, [{"id": "jarvis", "base_url": "https://api.jarvis.you/v1", "model": "X"}])
    with pytest.raises(GatewayError):
        gateway.complete("editing_agent", [{"role": "user", "content": "hi"}])
