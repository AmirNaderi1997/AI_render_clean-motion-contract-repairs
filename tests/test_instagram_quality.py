import subprocess

import pytest

from hermes.services.instagram_quality import evaluate, normalize_persian, words


def test_persian_zwnj_and_emoji_joiner_preserved():
    text = "مي‌توانيم 👩‍💻 يك متن فارسی بنویسیم."
    normalized = normalize_persian(text)
    assert normalized == "می‌توانیم 👩‍💻 یک متن فارسی بنویسیم."
    assert words("می‌توانیم بهتر بنویسیم") == ["می‌توانیم", "بهتر", "بنویسیم"]
    assert evaluate("humanize", text, "fa")["result"]["text"] == normalized


def test_persian_timing_is_nonzero_and_estimated():
    result = evaluate("beats", "این سه کلمه\nو این چهار کلمه", "fa", wpm=120)["result"]
    assert result["total_words"] == 7
    assert result["total_seconds"] == 3.5
    assert result["beats"][1]["start"] == 1.5
    assert result["timing_is_estimate"]


@pytest.mark.parametrize("number", ["۳", "3", "٣"])
def test_persian_hook_supports_all_numeric_keyboards(number):
    result = evaluate("hook", f"این {number} اشتباه رو نکن", "fa")["result"]
    assert not any(w["code"] == "REVIEW_SPECIFICITY" for w in result["warnings"])
    assert result["score"] is None  # Do not fabricate calibrated Persian scores.


def test_persian_caption_tags_and_single_ask():
    result = evaluate("caption", "این تمرین رو ذخیره کن\n#نیم‌فاصله #آموزش", "fa")["result"]
    assert result["hashtags"] == ["#نیم‌فاصله", "#آموزش"]
    assert result["asks"] == ["save"]


@pytest.mark.parametrize("operation,text", [
    ("hook", "I lost $18000 on one missing contract."),
    ("beats", "I lost money.\nHere is the contract.\nSave this contract."),
    ("caption", "Save this contract template.\n#contracts"),
    ("humanize", "We leverage robust systems."),
    ("audit_text", "I lost money. This is my contract."),
    ("swipe", "account\tmedian\tviews\thook\n@one\t100\t500\tI lost $18000 on one missing contract."),
])
def test_all_six_upstream_python_helpers_actually_run(operation, text):
    result = evaluate(operation, text, "en")
    assert result["result"]
    assert "heuristics" in result["disclaimer"]


@pytest.mark.parametrize("operation,text,language", [
    ("../../shell", "x", "en"), ("hook", "", "en"),
    ("hook", "x" * 20001, "en"), ("humanize", "می‌توانم", "en"),
    ("swipe", "متن", "fa"), ("hook", "x\x00y", "en"),
])
def test_invalid_or_unsupported_inputs_fail_closed(operation, text, language):
    with pytest.raises(ValueError):
        evaluate(operation, text, language)


def test_timeout_not_retried(monkeypatch):
    calls = []
    def timeout(*args, **kwargs):
        calls.append(args)
        raise subprocess.TimeoutExpired("check", 8)
    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        evaluate("hook", "Example hook", "en")
    assert len(calls) == 1
