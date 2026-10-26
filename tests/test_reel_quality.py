import re

from brain.talking_reel import default_highlight, normalize
from engine.persian_text import join_lam_alef


def test_lam_alef_is_joined_so_the_ray_fonts_do_not_draw_a_box():
    assert join_lam_alef("بالا") == "بال‍ا"
    assert join_lam_alef("اصلاً") == "اصل‍اً"
    assert join_lam_alef("الان") == "ال‍ان"
    assert join_lam_alef("سلام کلا") == "سل‍ام کل‍ا"
    assert join_lam_alef("لِ") == "لِ" and join_lam_alef("شیرینی") == "شیرینی"
    assert join_lam_alef(join_lam_alef("بالا")) == "بال‍ا"           # a second pass does not add more


def test_every_ass_escape_joins_lam_alef():
    from engine.captions import ass_text
    from engine.talking_styles.talking_1 import _esc
    from engine.localize import _escape
    for escape in (ass_text, _esc, _escape):
        assert "‍" in escape("میره بالا")


def test_the_hook_always_has_a_highlighted_word():
    assert default_highlight("چرا همش هوس شیرینی میکنیم؟!") == ["شیرینی"]
    assert default_highlight("من...") == []
    data = {"hook": "چرا همش هوس شیرینی میکنیم؟!", "hook_highlight": [], "captions": [{"i": 0, "text": "الف"}], "drop": [], "bw": [0], "notes": []}
    assert normalize(data, 1)["hook_highlight"] == ["شیرینی"]
    data["hook_highlight"] = ["هوس"]
    assert normalize(data, 1)["hook_highlight"] == ["هوس"]


def test_several_key_moments_and_notes_are_kept():
    data = {"hook": "هوک اصلی ما", "hook_highlight": ["هوک"], "captions": [{"i": i, "text": f"جمله {i}"} for i in range(12)], "drop": [],
            "bw": [1, 3, 5, 7, 9, 11, 0], "notes": [{"i": k, "text": "نکته کوتاه"} for k in (1, 3, 5, 7, 9, 11)]}
    result = normalize(data, 12)
    assert result["bw"] == [1, 3, 5, 7, 9, 11] and len(result["notes"]) == 5


def test_key_moment_phrases_are_not_coloured():
    from engine.talking_styles import talking_1
    events = talking_1.emphasis_events([{"start": 1.0, "end": 4.0, "text": "این طبیعیه"}], None)
    assert events and not any("\\1c" in event for event in events)
    assert "\\1c" in talking_1.hook_line("چرا همش هوس شیرینی", ["شیرینی"])          # the pinned hook keeps its yellow word
