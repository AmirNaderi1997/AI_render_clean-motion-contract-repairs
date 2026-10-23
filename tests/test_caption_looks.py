"""Caption looks (position, size, colour) applied to the ASS each style really builds."""
import pytest

from engine import caption_looks as looks

STYLE1 = "\n".join([
    "[V4+ Styles]",
    "Style: caption,Ray Black,62,&H00FFFFFF,&H000000FF,&H00000000,&H4D000000,-1,0,0,0,100,100,0,0,1,0,2,5,0,0,0,-1",
    "[Events]",
    r"Dialogue: 3,0:00:02.17,0:00:03.82,plain,,0,0,0,,{\an7\pos(339.1,1309.5)\1c&H000000&\1a&H00&\bord0\shad0\1a&H33&\p1}m 14.0 0 l 387.7 0 b 395.4 0 401.7 6.3 401.7 14.0 l 401.7 46.1 b 401.7 53.8 395.4 60.1 387.7 60.1 l 14.0 60.1 b 6.3 60.1 0 53.8 0 46.1 l 0 14.0 b 0 6.3 6.3 0 14.0 0{\p0}",
    r"Dialogue: 4,0:00:02.17,0:00:03.82,caption,,0,0,0,,{\an5\q2\pos(540,1337.6)\fs62}استرس  یعنی  چربی  بیشتر",
    r"Dialogue: 2,0:00:00.00,0:00:30.00,hook,,0,0,0,,{\an5\q2\pos(540,1420)}هوک ثابت",
])
STYLE2 = "\n".join([
    "[V4+ Styles]",
    "Style: key,Ray ExtraBlack,72,&H00FFFFFF,&H000000FF,&H64000000,&H64000000,-1,0,0,0,100,100,0,0,1,0.8,1.4,5,0,0,0,-1",
    "[Events]",
    r"Dialogue: 4,0:00:03.00,0:00:03.54,key,,0,0,0,,{\an5\q2\pos(540,960)\fscx108\fscy108\t(0,120,\fscx100\fscy100)}دور  شکممون  هم",
    r"Dialogue: 4,0:00:03.54,0:00:04.07,key,,0,0,0,,{\an5\q2\pos(540,960)\fscx108\fscy108\t(0,120,\fscx100\fscy100)}بیشتر  میشه",
])
CAPTIONS1 = [{"start": 2.17, "end": 3.82, "text": "استرس یعنی چربی بیشتر"}]
CAPTIONS2 = [{"start": 3.0, "end": 3.54, "lead": "دور", "key": "شکممون"}, {"start": 3.54, "end": 4.07, "lead": "", "key": "میشه"}]


def test_clean_look_validates_and_drops_unset_fields():
    assert looks.clean_look({"x": "300", "y": 1500.123, "scale": 1.5, "color": "#a8cf80", "junk": 1}) == {"x": 300.0, "y": 1500.12, "scale": 1.5, "color": "#A8CF80"}
    assert looks.clean_look({"x": None}) == {}
    for bad in ({"x": -1}, {"x": 2000}, {"y": 3000}, {"scale": 0.1}, {"scale": 9}, {"color": "red"}, {"x": "abc"}, {"scale": float("nan")}):
        with pytest.raises(ValueError):
            looks.clean_look(bad)


def test_geometry_reads_text_and_box_from_the_real_events():
    frame = looks.geometry(STYLE1, CAPTIONS1)[0]
    assert (frame["x"], frame["y"], frame["size"], frame["style"]) == (540.0, 1337.6, 62.0, "caption")
    assert frame["box"]["dx"] == pytest.approx(339.1 - 540) and frame["box"]["dy"] == pytest.approx(1309.5 - 1337.6)
    assert (frame["box"]["w"], frame["box"]["h"]) == pytest.approx((401.7, 60.1))
    plain = looks.geometry(STYLE2, CAPTIONS2)
    assert plain[0]["box"] is None and plain[0]["size"] == 72.0           # size comes from the style when the event has no \fs
    assert 1 in plain and plain[1]["y"] == 960.0


def test_style_one_text_and_box_move_and_scale_together():
    out = looks.apply(STYLE1, [{**CAPTIONS1[0], "look": {"x": 400, "y": 1000, "scale": 2.0, "color": "#FFD23F"}}])
    text = next(l for l in out.splitlines() if ",caption,," in l)
    box = next(l for l in out.splitlines() if ",plain,," in l)
    assert r"\pos(400.0,1000.0)" in text and r"\fs124" in text and r"\1c&H3FD2FF&" in text           # BGR of #FFD23F
    # the box keeps its place relative to the text, scaled: offset (-200.9, -28.1) x 2
    assert r"\pos(-1.8,943.8)" in box and r"\fscx200\fscy200" in box and r"\p1" in box
    assert next(l for l in out.splitlines() if ",hook,," in l) == next(l for l in STYLE1.splitlines() if ",hook,," in l)   # other events untouched


def test_style_two_adds_size_and_colour_without_breaking_the_pop_animation():
    out = looks.apply(STYLE2, [{**CAPTIONS2[0], "look": {"y": 800, "scale": 0.5, "color": "#00FF00"}}, CAPTIONS2[1]])
    first, second = [l for l in out.splitlines() if l.startswith("Dialogue")]
    assert r"\pos(540.0,800.0)" in first and r"\fs36" in first and r"\1c&H00FF00&" in first and r"\t(0,120,\fscx100\fscy100)" in first
    assert second == [l for l in STYLE2.splitlines() if l.startswith("Dialogue")][1]                  # the next caption is unchanged


def test_no_looks_means_byte_identical_ass_and_unmatched_events_are_ignored():
    assert looks.apply(STYLE1, CAPTIONS1) == STYLE1
    assert looks.apply(STYLE2, [{"start": 50, "end": 51, "key": "x", "look": {"x": 1}}]) == STYLE2


def test_effective_rect_follows_the_look():
    frame = looks.geometry(STYLE1, CAPTIONS1)[0]
    base = looks.effective_rect(frame, None)
    assert (base["x"], base["y"], base["w"], base["h"]) == pytest.approx((339.1, 1309.5, 401.7, 60.1))
    moved = looks.effective_rect(frame, {"x": 540, "y": 1000, "scale": 2})
    assert moved["w"] == pytest.approx(803.4) and moved["x"] == pytest.approx(540 + 2 * (339.1 - 540))


def test_backslash_tags_are_never_read_as_regex_escapes():
    """`\\fs` in a regex replacement string became a form feed and destroyed the caption line."""
    out = looks.apply(STYLE1, [{**CAPTIONS1[0], "look": {"scale": 2.0}}])
    assert "\x0c" not in out and "\x08" not in out and "\x07" not in out
    assert r"\fs124" in next(l for l in out.splitlines() if ",caption,," in l and l.startswith("Dialogue"))


def test_style_four_cues_carry_position_size_and_colour_into_the_tscaps_spec():
    from engine import tscaps_overlay as tso
    plan = type("P", (), {"hook": None, "captions": [
        {"start": 0.0, "end": 1.5, "lead": "", "key": "اول", "look": {"y": 960, "scale": 1.5, "color": "#FF0000"}},
        {"start": 1.6, "end": 3.0, "lead": "", "key": "دوم"}]})()
    spec = tso.build_spec(tso.reel_cues(plan, moments=False), 1080, 1920)
    names = [cue["kind"] for cue in spec["cues"]]
    assert names[1] == "caption" and names[0] == "caption_y50_s150_cff0000"        # the second caption keeps the role's own look
    variant = spec["kinds"][names[0]]
    assert variant["alignment"]["verticalOffset"] == 0.5 and variant["vars"]["--tscaps-primary-color"] == "#FF0000"
    assert variant["vars"]["--tscaps-font-size"] == "7.20cqh"                       # 4.8cqh x 1.5
    assert spec["kinds"]["caption"] == tso.ROLES["caption"]                         # the role itself is never mutated
    assert tso.ROLES["caption"]["vars"]["--tscaps-font-size"] == "4.8cqh"
