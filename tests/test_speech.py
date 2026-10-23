import json
from pathlib import Path

from creative import speech


def test_estimator_matches_real_elevenlabs_clips_within_planning_error():
    sample = Path(__file__).parent / "fixtures" / "narration_samples.json"
    rows = json.loads(sample.read_text())
    errors = [abs(speech.speech_seconds(text) - seconds) for text, seconds in rows]
    assert len(rows) == 18 and sum(errors) / len(errors) < 0.5      # fitted at 0.36 s
    assert max(errors) < 1.4


def test_word_count_is_not_the_measure():
    assert speech.speech_seconds("دو نوع کار هست.") < speech.speech_seconds("کارتو می‌گیره؟ بستگی داره.")


def test_budget_headroom_and_fit():
    short = ["تدوین دستی تمام شد."]
    assert speech.fits(short, 5)
    long_line = ["این یک جملهٔ بسیار بلند است که برای یک ویدیوی پانزده ثانیه‌ای هرگز در زمان مناسب گفته نمی‌شود، چون پر از توضیحات است."] * 3
    assert not speech.fits(long_line, 15)
    assert speech.max_letters(3.0) < speech.max_letters(6.0)


def test_check_audio_flags_drift():
    assert speech.check_audio(10.0, 10.8)["ok"] and not speech.check_audio(10.0, 14.0)["ok"]
