"""Tscaps overlay: cue planning, the spec sent to the engine, and the fall-back to built-in captions."""
import dataclasses
import shutil
from pathlib import Path

import pytest

from engine import tscaps_overlay as tso
from engine.talking_styles import talking_2, talking_4


def make_plan(captions=None, hook=True):
    captions = captions if captions is not None else [
        {"start": 3.0 + i * 1.5, "end": 4.4 + i * 1.5, "lead": "ولی", "key": f"کلمه{i}"} for i in range(8)]
    return talking_2.ReelPlan(shots=[], captions=captions, hook={"start": 0.0, "end": 3.0, "text": "خدمات ثروت نمی‌سازه"} if hook else None,
                              duration=20.0)


def test_words_are_spread_in_order_inside_the_window_and_emphasis_is_tagged():
    words = tso.words_for("ولی خدمات ثروت", 1.0, 4.0, emphasize="ثروت")
    assert [w.t for w in words] == ["ولی", "خدمات", "ثروت"]
    assert words[0].s == 1.0 and words[-1].e <= 4.0 and all(a.e <= b.s + 1e-6 for a, b in zip(words, words[1:]))
    assert [w.tag for w in words] == [None, None, "emphasis"]


def test_reveal_limits_how_long_words_take_to_arrive():
    words = tso.words_for("یک دو سه چهار", 0.0, 10.0, reveal=1.4)
    assert words[-1].e <= 1.4 + 1e-6


def test_reel_cues_have_a_hook_captions_and_every_fifth_phrase_as_a_moment():
    cues = tso.reel_cues(make_plan())
    kinds = [c.kind for c in cues]
    assert kinds[0] == "hook" and kinds.count("moment") == 1 and kinds.count("caption") == 7
    assert all(a.end <= b.start + 1e-6 for a, b in zip(cues, cues[1:]))            # never overlap


def test_captions_under_the_hook_window_are_dropped():
    plan = make_plan([{"start": 0.5, "end": 2.5, "lead": "", "key": "زیر هوک"}, {"start": 3.2, "end": 4.5, "lead": "", "key": "بعد"}])
    assert [c.kind for c in tso.reel_cues(plan)] == ["hook", "caption"]


def test_spec_only_contains_the_roles_in_use_and_our_fonts():
    spec = tso.build_spec(tso.reel_cues(make_plan()), 1080, 1920)
    assert set(spec["kinds"]) == {"hook", "caption", "moment"}
    assert {f["family"] for f in spec["fonts"]} >= {"RayBlack", "Vazir"}
    assert all(k["template"] in {"loki", "noor", "elio"} for k in spec["kinds"].values())
    assert all(f.exists() for f in (tso.TOOL / "templates" / f"{name}.css" for name in ("loki", "noor", "elio")))


def test_templates_are_vendored_with_their_licence():
    assert (tso.TOOL / "templates" / "LICENSE").read_text().startswith("MIT License")
    assert "AGPL" in (tso.TOOL / "NOTICE.md").read_text()


def test_empty_cues_are_reported_as_unavailable(tmp_path):
    with pytest.raises(tso.OverlayUnavailable):
        tso.render_overlay([], tmp_path / "o.webm", width=1080, height=1920, fps=30, duration=5, work_dir=tmp_path)


def test_talking_4_falls_back_to_built_in_captions_when_the_overlay_fails(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(talking_4.base, "probe_fps", lambda video: "30/1")
    monkeypatch.setattr(tso, "render_overlay", lambda *a, **k: (_ for _ in ()).throw(tso.OverlayUnavailable("no chrome")))
    monkeypatch.setattr(talking_4.base, "render_plain", lambda video, plan, out, **k: seen.append((plan, k.get("overlay"))) or out)
    plan = make_plan()
    talking_4.render(tmp_path / "v.mp4", plan, tmp_path / "o.mp4", work_dir=tmp_path)
    assert seen[0][0].captions and seen[0][0].hook and seen[0][1] is None        # ASS captions kept, no overlay


def test_talking_4_hands_ass_nothing_to_draw_when_the_overlay_exists(tmp_path, monkeypatch):
    seen = []
    fake = tmp_path / "ov.webm"
    fake.write_bytes(b"x" * 2000)
    monkeypatch.setattr(talking_4.base, "probe_fps", lambda video: "30/1")
    monkeypatch.setattr(tso, "render_overlay", lambda *a, **k: fake)
    monkeypatch.setattr(talking_4.base, "render_plain", lambda video, plan, out, **k: seen.append((plan, k.get("overlay"))) or out)
    talking_4.render(tmp_path / "v.mp4", make_plan(), tmp_path / "o.mp4", work_dir=tmp_path)
    assert seen[0][0].captions == [] and seen[0][0].hook is None and seen[0][1] == fake


def test_a_failed_overlay_composite_is_retried_with_built_in_captions(tmp_path, monkeypatch):
    calls = []
    fake = tmp_path / "ov.webm"
    fake.write_bytes(b"x" * 2000)
    monkeypatch.setattr(talking_4.base, "probe_fps", lambda video: "30/1")
    monkeypatch.setattr(tso, "render_overlay", lambda *a, **k: fake)

    def render(video, plan, out, **k):
        calls.append(k.get("overlay"))
        if k.get("overlay"):
            raise RuntimeError("ffmpeg failed")
        return out
    monkeypatch.setattr(talking_4.base, "render_plain", render)
    talking_4.render(tmp_path / "v.mp4", make_plan(), tmp_path / "o.mp4", work_dir=tmp_path)
    assert calls == [fake, None]


@pytest.mark.skipif(not tso.available() or not shutil.which("ffprobe") or not __import__("os").environ.get("RUN_TSCAPS_E2E"),
                    reason="slow: set RUN_TSCAPS_E2E=1 (needs node, Chrome and the installed engine)")
def test_engine_renders_a_transparent_overlay_of_the_requested_size(tmp_path):
    import subprocess
    cues = tso.reel_cues(make_plan())[:2]
    out = tso.render_overlay(cues, tmp_path / "o.webm", width=540, height=960, fps=30, duration=6.0, work_dir=tmp_path)
    probe = subprocess.run(["ffprobe", "-v", "error", "-c:v", "libvpx-vp9", "-show_entries", "stream=width,height,pix_fmt", "-of", "csv=p=0", str(out)],
                           capture_output=True, text=True).stdout.strip()
    assert probe.startswith("vp9,540,960") or "540,960" in probe and "yuva" in probe


# ── hook / moment layers for the other talking styles ────────────────────────
def test_vertical_overrides_become_their_own_kind_in_the_spec():
    cues = [tso.Cue("hook", 0, 2, tso.words_for("الف ب", 0, 2), y=0.27), tso.Cue("hook", 3, 5, tso.words_for("ج د", 3, 5))]
    spec = tso.build_spec(cues, 1080, 1920)
    assert set(spec["kinds"]) == {"hook_y27", "hook"}
    assert spec["kinds"]["hook_y27"]["alignment"]["verticalOffset"] == 0.27 and spec["kinds"]["hook"]["alignment"]["verticalOffset"] == 0.62
    assert [c["kind"] for c in spec["cues"]] == ["hook_y27", "hook"]


def test_title_hook_and_note_cues():
    titles = tso.title_cues([{"start": 5, "end": 7.5, "text": "بازی عوض شد"}], y_for=lambda t: 0.34)
    assert titles[0].kind == "moment" and titles[0].y == 0.34 and titles[0].words[0].tag == "emphasis"
    hook = tso.hook_cue({"start": 0, "end": 3, "text": "سه کلمه اینجاست"}, accent_first=True)
    assert hook[0].kind == "hook" and hook[0].words[0].tag == "emphasis" and hook[0].start == 0.1
    notes = tso.note_cues([{"start": 10, "end": 12, "text": "این، مهمترین نکته"}])
    assert [w.t for w in notes[0].words] == ["این", "مهمترین", "نکته"] and notes[0].words[-1].tag == "emphasis"
    assert tso.hook_cue(None) == [] and tso.title_cues([]) == []


def _styled_plan():
    plan = make_plan()
    plan.titles = [{"start": 8.0, "end": 10.0, "text": "نکته کلیدی"}]
    return plan


@pytest.mark.parametrize("module_name", ["talking_2", "talking_3"])
def test_split_styles_draw_only_hook_and_titles_with_the_overlay(module_name, tmp_path, monkeypatch):
    import importlib
    module = importlib.import_module(f"engine.talking_styles.{module_name}")
    fake = tmp_path / "ov.webm"
    fake.write_bytes(b"x" * 2000)
    seen = []
    monkeypatch.setattr(module, "probe_fps", lambda video: "30/1")
    monkeypatch.setattr(tso, "render_overlay", lambda cues, *a, **k: seen.append([c.kind for c in cues]) or fake)
    calls = []
    monkeypatch.setattr(module, "render_plain", lambda video, plan, out, **k: calls.append((plan, k.get("overlay"))) or out)
    plan = _styled_plan()
    plan.full_pictures = set() if not hasattr(plan, "full_pictures") else plan.full_pictures
    module.render(tmp_path / "v.mp4", plan, tmp_path / "o.mp4", work_dir=tmp_path)
    assert calls[0][1] == fake and calls[0][0].hook is None and calls[0][0].captions and calls[0][0].captions[0]["start"] >= 3.0                    # captions stay with ASS
    assert seen[0][0] == "hook" and ("moment" in seen[0]) == (module_name == "talking_3")


def test_talking_1_hands_only_the_emphasis_phrases_to_the_overlay(tmp_path, monkeypatch):
    from engine.talking_styles import talking_1
    fake = tmp_path / "ov.webm"
    fake.write_bytes(b"x" * 2000)
    monkeypatch.setattr(tso, "render_overlay", lambda cues, *a, **k: fake if all(c.kind == "moment" for c in cues) else None)
    calls = []
    monkeypatch.setattr(talking_1, "render_plain", lambda video, plan, out, **k: calls.append(k) or out)
    plan = talking_1.ReelPlan(shots=[], captions=[{"start": 1, "end": 2, "text": "الف"}],
                              notes=[{"start": 5.0, "end": 7.0, "text": "نکته مهم"}], duration=20.0)
    talking_1.render(tmp_path / "v.mp4", plan, tmp_path / "o.mp4", hook="هوک", highlight=[], name="", title="", work_dir=tmp_path)
    assert calls[0]["overlay"] == fake and calls[0]["hook"] == "هوک"


def test_talking_1_keeps_the_old_ass_emphasis_when_there_is_no_overlay():
    from engine.talking_styles import talking_1
    plan = talking_1.ReelPlan(shots=[], captions=[], notes=[{"start": 5.0, "end": 7.0, "text": "نکته مهم"}], duration=20.0)
    with_ass = talking_1.build_ass(plan, "هوک", [], "", "", None)
    without = talking_1.build_ass(plan, "هوک", [], "", "", None, moments=False)
    assert ",emph,," in with_ass and ",emph,," not in without
