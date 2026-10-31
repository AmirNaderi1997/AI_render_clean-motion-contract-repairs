import json
import math
import os
from pathlib import Path

import pytest

from brain import transcribe_gemini as g
from brain.mms_alignment import preflight


def test_chunking():
    assert g.chunk_boundaries(601, [(280, 282), (570, 572)]) == [
        (0, 281),
        (281, 571),
        (571, 601),
    ]
    with pytest.raises(g.RejectedTranscript, match="no_safe_chunk_boundary"):
        g.chunk_boundaries(301, [])
    assert g.chunk_boundaries(300, []) == [(0, 300)]


def test_safety():
    words = [{"w": "سلام", "start": 0.0, "end": 1.0}]
    assert g.validate("سلام", words, 2, words) == 1
    for text, rows, ref, reason in [
        ("hello", words, words, "text_not_persian"),
        ("سلام دنیا", words, words, "coverage"),
        ("سلام", [{"start": 0, "end": 4}], words, "timing"),
        ("سلام", [{"start": math.nan, "end": 1}], words, "timing"),
        ("سلام", words, [], "reference_empty"),
        ("سلام", words, [{"start": 2, "end": 9}], "uncovered_speech"),
        (
            "سلام",
            words,
            [{"start": i, "end": i + 0.5} for i in range(10)],
            "word_count",
        ),
    ]:
        with pytest.raises(g.RejectedTranscript, match=reason):
            g.validate(text, rows, 20, ref)


def test_cache_and_missing_model(monkeypatch, tmp_path):
    monkeypatch.setenv("SAROVI_TRANSCRIBE_MODEL", "one")
    a = g.cache_key("hash", "fa")
    monkeypatch.setenv("SAROVI_TRANSCRIBE_MODEL", "two")
    assert a != g.cache_key("hash", "fa")
    with pytest.raises(FileNotFoundError, match="cache missing"):
        preflight(str(tmp_path))


def test_chain_and_reason(monkeypatch, tmp_path):
    from brain import transcribe as t, transcribe_elevenlabs as e, lm_direct

    monkeypatch.setenv("SAROVI_TRANSCRIBE_ENABLED", "true")
    monkeypatch.setenv("ELEVENLABS_PROXY_URL", "https://example.test")
    monkeypatch.delenv("ASR_ENGINE", raising=False)
    monkeypatch.setenv("WHISPER_ENABLED", "true")
    calls = []

    def relay(*a, **k):
        calls.append("relay")
        raise RuntimeError()

    def gemini(*a, **k):
        calls.append("gemini")
        raise g.RejectedTranscript("aligner_cache_missing")

    def local(video, root, *a):
        calls.append("local")
        result = {
            "engine": "whisper",
            "words": [{"w": "سلام", "start": 0, "end": 1}],
            "sentences": [],
        }
        (root / "transcript.json").write_text(json.dumps(result))
        return result

    monkeypatch.setattr(e, "transcribe_elevenlabs", relay)
    monkeypatch.setattr(g, "transcribe_gemini", gemini)
    monkeypatch.setattr(t, "_transcribe_whisper", local)
    monkeypatch.setattr(
        lm_direct,
        "config",
        lambda: {
            "stt": {"enabled": True, "model": "small", "improve_low_quality": True}
        },
    )
    source = tmp_path / "audio"
    source.write_bytes(b"audio")
    t.transcribe(source, tmp_path / "out", language="fa")
    assert calls == ["relay", "gemini", "local"]
    attempts = json.loads((tmp_path / "out/asr_attempts.json").read_text())
    assert attempts[1]["reason"] == "aligner_cache_missing"


def test_provider_format_and_audit(monkeypatch):
    from brain import lm_direct, lm_gateway

    rows = []
    monkeypatch.setattr(lm_gateway, "_audit", rows.append)
    monkeypatch.setattr(lm_direct, "usable", lambda: [{"id": "sarovi"}])

    def call(p, m, **kw):
        assert kw["temperature"] == 0
        assert m[0]["content"][1]["input_audio"] == {"data": "d2F2", "format": "wav"}
        return {
            "choices": [{"finish_reason": "stop", "message": {"content": "سلام"}}],
            "usage": {"cost": 0.005},
        }

    monkeypatch.setattr(lm_direct, "call", call)
    assert g.hosted(b"wav") == ("سلام", 0.005)
    assert (
        len(rows) == 1
        and rows[0]["request_message"] is None
        and rows[0]["response_message"] is None
    )


@pytest.mark.skipif(
    not os.environ.get("MMS_ALIGNMENT_TEST_AUDIO"),
    reason="opt-in local model/audio integration",
)
def test_real_alignment():
    from brain.mms_alignment import align

    words = align(
        Path(os.environ["MMS_ALIGNMENT_TEST_AUDIO"]),
        os.environ["MMS_ALIGNMENT_TEST_TEXT"],
        os.environ["MMS_ALIGN_CACHE_DIR"],
    )
    assert words and all(w["end"] > w["start"] for w in words)


def test_mocked_alignment_pipeline(monkeypatch, tmp_path):
    import wave
    from types import SimpleNamespace
    from brain import mms_alignment as m

    words = [{"w": "سلام", "start": 0.0, "end": 0.8}]
    monkeypatch.setattr(m, "preflight", lambda p: None)
    monkeypatch.setattr(m, "align", lambda *a: words)
    monkeypatch.setattr(g, "whisper_reference", lambda a: words)
    calls = []
    monkeypatch.setattr(g, "hosted", lambda a: (calls.append(a) or ("سلام", 0.005)))

    def run(args, **kw):
        if "-y" in args:
            with wave.open(args[-1], "wb") as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(16000)
                f.writeframes(bytes(32000))
        return SimpleNamespace(stderr="")

    monkeypatch.setattr(g.subprocess, "run", run)
    result, cost = g.transcribe_gemini(
        tmp_path / "input", tmp_path, language="fa", file_digest="abc"
    )
    assert (
        result["engine"] == "gemini_aligned"
        and result["words"] == words
        and cost == 0.005
    )
    again, cost = g.transcribe_gemini(
        tmp_path / "input", tmp_path, language="fa", file_digest="abc"
    )
    assert again == result and cost == 0 and len(calls) == 1


def test_non_monotonic_and_out_of_range():
    reference = [{"start": 0, "end": 1}]
    for rows in (
        [{"start": 1, "end": 2}, {"start": 0.5, "end": 1}],
        [{"start": 0, "end": 21}],
    ):
        with pytest.raises(g.RejectedTranscript, match="timing"):
            g.validate("سلام دنیا", rows, 20, reference)
