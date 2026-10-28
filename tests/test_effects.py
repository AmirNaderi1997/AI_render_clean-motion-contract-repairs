import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from engine import face_effects as effects
from engine.face_effects.catalog import BY_ID, CATALOG, EffectsError, clean_plan


def test_every_catalog_effect_exists_in_the_core_and_is_described_in_persian():
    from engine.face_effects import _fx
    for spec in CATALOG:
        assert spec["id"] in _fx.EFFECTS, spec["id"]
        assert any("؀" <= ch <= "ۿ" for ch in spec["title"] + spec["description"])
        for option in spec["options"]:
            assert option["type"] in {"number", "choice", "color"}
    assert len(CATALOG) == 42 and len(BY_ID) == 42


def test_a_plan_keeps_only_known_effects_inside_their_limits():
    plan = clean_plan([{"fx": "orbit", "start": 1, "end": 3, "count": 99, "speed": "2", "bogus": 1},
                       {"fx": "spotlight", "start": "4", "end": 6, "text": "  سلام   دنیا ", "color": "#ff0000"}], duration=10)
    assert plan[0] == {"fx": "orbit", "start": 1.0, "end": 3.0, "count": 10.0, "speed": 2.0}
    assert plan[1]["text"] == "سلام دنیا" and plan[1]["color"] == "#FF0000"
    assert clean_plan(None) == [] and clean_plan([]) == []


@pytest.mark.parametrize("bad", [
    [{"fx": "nope", "start": 0, "end": 2}], [{"fx": "orbit", "start": 3, "end": 2}], [{"fx": "orbit", "start": 0, "end": 30}],
    [{"fx": "orbit", "start": 0, "end": 0.1}], [{"fx": "spotlight", "start": 0, "end": 2, "color": "red"}], [{"fx": "moody", "start": 0, "end": 2, "grade": "x"}],
    ["orbit"], "orbit", [{"fx": "orbit", "start": 0, "end": 1}] * 13])
def test_a_bad_plan_is_refused(bad):
    with pytest.raises(EffectsError):
        clean_plan(bad)


def test_an_effect_that_ends_after_the_video_is_cut_at_the_end():
    assert clean_plan([{"fx": "moody", "start": 8, "end": 12}], duration=10)[0]["end"] == 10.0
    with pytest.raises(EffectsError):
        clean_plan([{"fx": "moody", "start": 9.95, "end": 12}], duration=10)


def test_the_render_settings_carry_the_effects(tmp_path):
    from app import talking_reel
    settings = talking_reel._clean_render_settings({"effects": [{"fx": "orbit", "start": 1, "end": 3}]})
    assert settings["effects"] == [{"fx": "orbit", "start": 1.0, "end": 3.0}]
    assert talking_reel._clean_render_settings({"effects": [{"fx": "nope", "start": 1, "end": 3}]})["effects"] == []


def test_the_chat_can_add_and_remove_effects():
    from creative import revise
    ops = [revise.RevisionOp(op="add_effect", fx="orbit", start=3, end=6), revise.RevisionOp(op="add_effect", fx="spotlight", start=7, end=9, text="سلام"),
           revise.RevisionOp(op="add_effect", fx="nope", start=1, end=2), revise.RevisionOp(op="add_effect", fx="moody"),
           revise.RevisionOp(op="remove_effect", fx="orbit")]
    change = revise.apply_to_talking({"style": "talking_1", "render_settings": {"effects": []}}, ops, 10)
    assert change.changes["render_settings"]["effects"] == [{"fx": "spotlight", "start": 7.0, "end": 9.0, "text": "سلام"}]
    assert len(change.unsupported) == 2 and change.rerender
    system = revise._system()
    assert "orbit" in system and "{EFFECT_IDS}" not in system


def test_a_missing_runtime_is_reported_not_crashed(monkeypatch, tmp_path):
    monkeypatch.setattr(effects, "available", lambda: False)
    with pytest.raises(EffectsError):
        effects.apply(tmp_path / "a.mp4", tmp_path / "b.mp4", [{"fx": "orbit", "start": 1, "end": 3}], work=tmp_path / "w")


def test_the_runner_lays_effects_over_a_real_video(tmp_path):
    pytest.importorskip("mediapipe")
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is not installed")
    source = tmp_path / "in.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=540x960:r=30:d=3", "-f", "lavfi", "-i", "sine=f=440:d=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source)], check=True)
    out = effects.apply(source, tmp_path / "out.mp4", [{"fx": "moody", "start": 0.5, "end": 2.0}], work=tmp_path / "work")
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "json", str(out)], capture_output=True, text=True).stdout)
    kinds = {stream["codec_type"] for stream in probe["streams"]}
    assert kinds == {"video", "audio"}
