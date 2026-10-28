from engine.face_effects import CATALOG, clean_plan
from engine.face_effects import _fa
from engine.talking_styles import talking_5 as t5


def test_all_effects_are_in_the_catalog():
    from engine.face_effects import _fx
    assert {c["id"] for c in CATALOG} == set(_fx.EFFECTS)
    assert len(CATALOG) == 42 and all(c["title"] and c["use"] is not None for c in CATALOG)


def test_effect_text_is_kept_up_to_a_sentence():
    plan = clean_plan([{"fx": "lineup", "start": 1, "end": 3, "text": "اول|دوم|سوم"}])
    assert plan[0]["text"] == "اول|دوم|سوم"


def test_persian_shaping_joins_letters_and_keeps_numbers():
    shaped = _fa.shape("سلام ۴ ساعت")
    assert "۴" in shaped and shaped != "سلام ۴ ساعت" and all(ord(c) > 0xFB00 or c in " ۴" for c in shaped)


def test_slide_expression_is_zero_in_full_frame_and_drop_in_card():
    assert t5._slide(400, False, False, 3.0).endswith("400.00*ld(1)*ld(2)")
