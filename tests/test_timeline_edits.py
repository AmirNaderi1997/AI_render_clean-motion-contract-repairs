"""Timeline edits: caption text/timing/hide applied to the render plan, validated, id-stable."""
import pytest

from app import timeline_edits as layer
from engine.talking_styles import talking_1 as t1, talking_2 as t2

SENTENCES = [{"start": 0.0, "end": 4.0, "text": "اول"}, {"start": 4.0, "end": 9.0, "text": "دوم"}]


def split_plan():
    shots = [t2.Shot(0.0, 9.0, split=True, out_start=0.0)]
    captions = [{"start": 0.2, "end": 1.6, "lead": "این", "key": "اولیه"}, {"start": 1.8, "end": 3.5, "lead": "", "key": "دومی"},
                {"start": 4.4, "end": 6.0, "lead": "و", "key": "سومی"}]
    return t2.ReelPlan(shots=shots, captions=captions, duration=9.0)


def talking1_plan():
    shots = [t1.Shot(0.0, 9.0, out_start=0.0)]
    captions = [{"start": 0.2, "end": 1.6, "text": "متن اول"}, {"start": 1.8, "end": 3.5, "text": "متن دوم"}]
    return t1.ReelPlan(shots=shots, captions=captions, duration=9.0)


def test_ids_come_from_the_sentence_and_do_not_depend_on_text():
    plan = split_plan()
    before = layer.caption_ids(plan, SENTENCES)
    assert before == ["caption:s0:0", "caption:s0:1", "caption:s1:0"]
    plan.captions[0]["key"] = "کاملاً متفاوت"
    assert layer.caption_ids(plan, SENTENCES) == before


def test_text_edit_keeps_each_styles_caption_shape():
    split, one = split_plan(), talking1_plan()
    layer.apply(split, SENTENCES, {"caption:s0:0": {"text": "یک متن تازه"}})
    assert (split.captions[0]["lead"], split.captions[0]["key"]) == ("یک متن", "تازه")
    assert "text" not in split.captions[0]
    layer.apply(one, SENTENCES, {"caption:s0:1": {"text": "اصلاح‌شده"}})
    assert one.captions[1]["text"] == "اصلاح‌شده" and "key" not in one.captions[1]


def test_timing_edit_and_hide_and_stale_ids():
    plan = split_plan()
    layer.apply(plan, SENTENCES, {"caption:s0:0": {"start": 0.5, "end": 1.7}, "caption:s0:1": {"deleted": True},
                                  "caption:s9:0": {"text": "یتیم"}})
    assert [(c["key"], c["start"], c["end"]) for c in plan.captions] == [("اولیه", 0.5, 1.7), ("سومی", 4.4, 6.0)]


def test_clean_rejects_bad_shapes():
    assert layer.clean({"caption:s0:0": {"text": "  سلام   دنیا ", "extra": 1}}) == {"caption:s0:0": {"text": "سلام دنیا"}}
    for bad in ({"hook": {"text": "x"}}, {"caption:s0:0": {"text": ""}}, {"caption:s0:0": {"start": -1}},
                {"caption:s0:0": {"start": "abc"}}, {"caption:s0:0": {"text": "x" * 500}}, [1]):
        with pytest.raises(layer.EditError):
            layer.clean(bad)


def test_validate_checks_ids_length_bounds_and_neighbours():
    plan = split_plan()
    ok = {"caption:s0:0": {"start": 0.3, "end": 1.7}}
    layer.validate(plan, SENTENCES, ok, 9.0)
    for bad, why in (({"caption:s7:0": {"text": "x"}}, "وجود ندارد"),
                     ({"caption:s0:0": {"start": 1.0, "end": 1.1}}, "۰.۳"),
                     ({"caption:s0:0": {"end": 9.5}}, "مدت ویدیو"),
                     ({"caption:s0:0": {"end": 2.5}}, "هم‌پوشانی")):
        with pytest.raises(layer.EditError) as error:
            layer.validate(plan, SENTENCES, bad, 9.0)
        assert why in str(error.value) or why == "۰.۳"
    layer.validate(plan, SENTENCES, {"caption:s0:1": {"deleted": True}, "caption:s0:0": {"end": 3.4}}, 9.0)  # hiding frees the space
