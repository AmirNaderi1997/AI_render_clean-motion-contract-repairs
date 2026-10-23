"""B-roll edits: one source per slot, applied before picture resolution; AI images are never made while only reading."""
import json
from pathlib import Path

import pytest

from app import broll_edits as layer, talking_reel

DECISIONS = {"broll": [{"i": 2, "visual": "a compass on a map", "label": "قطب‌نما", "media": "", "items": []},
                       {"i": 5, "visual": "a coin stack", "label": "سکه", "media": "mine.png", "items": []},
                       {"i": 8, "visual": "a ladder", "label": "نردبان", "media": "", "items": []}],
             "chips": [], "hook": "x"}


def test_clean_accepts_exactly_one_source_per_slot_and_rejects_the_rest():
    ok = layer.clean({"2": {"source": "ai", "visual": "  a   red   door ", "x": 1}, "5": {"source": "upload", "media": "a.png"},
                      "8": {"source": "hidden"}, "9": {"source": "library", "library": "assets/pics/a.png"}})
    assert ok["2"] == {"source": "ai", "visual": "a red door"} and ok["8"] == {"source": "hidden"}
    for bad in ({"x": {"source": "ai", "visual": "abc"}}, {"2": {"source": "magic"}}, {"2": {"source": "ai", "visual": "a"}},
                {"2": {"source": "upload", "media": "../../etc/passwd"}}, {"2": {"source": "library", "library": "/etc/passwd"}},
                {"2": {"source": "library", "library": "assets/../secret"}}, {"2": "ai"}, [1]):
        with pytest.raises(layer.EditError):
            layer.clean(bad)


def test_validate_only_allows_planned_slots_and_existing_files():
    edits = layer.clean({"2": {"source": "upload", "media": "mine.png"}})
    layer.validate(DECISIONS, edits, uploads={"mine.png"}, library=set())
    with pytest.raises(layer.EditError):
        layer.validate(DECISIONS, edits, uploads=set(), library=set())                       # file missing
    with pytest.raises(layer.EditError):
        layer.validate(DECISIONS, layer.clean({"7": {"source": "hidden"}}), uploads=set(), library=set())   # slot never planned
    with pytest.raises(layer.EditError):
        layer.validate(DECISIONS, layer.clean({"2": {"source": "library", "library": "assets/x.png"}}), uploads=set(), library={"assets/y.png"})


def test_apply_changes_only_the_edited_slots_and_never_the_input():
    original = json.loads(json.dumps(DECISIONS))
    edits = layer.clean({"2": {"source": "ai", "visual": "an old key, Iranian style"}, "5": {"source": "hidden"},
                         "8": {"source": "library", "library": "assets/pics/ladder.png", "label": "پله"}})
    out = layer.apply(DECISIONS, edits)
    assert DECISIONS == original                                                  # pure
    assert [b["i"] for b in out["broll"]] == [2, 8]                               # slot 5 hidden
    assert out["broll"][0]["visual"] == "an old key, Persian style"               # same prompt cleanup the planner applies
    assert out["broll"][1]["library"] == "assets/pics/ladder.png" and out["broll"][1]["visual"] == "" and out["broll"][1]["label"] == "پله"
    assert layer.apply(DECISIONS, {}) is DECISIONS
    assert layer.apply(DECISIONS, layer.clean({"99": {"source": "hidden"}}))["broll"] == DECISIONS["broll"]   # stale slot ignored


@pytest.fixture
def job(tmp_path, monkeypatch):
    (tmp_path / talking_reel.MEDIA_DIR).mkdir()
    (tmp_path / talking_reel.MEDIA_DIR / "mine.png").write_bytes(b"png")
    monkeypatch.setattr(talking_reel, "load", lambda _: {"status": "ready"})
    monkeypatch.setattr(talking_reel, "_library_pictures", lambda: [])
    return tmp_path


def test_resolve_pictures_follows_the_edits_and_makes_nothing_when_only_reading(job, monkeypatch):
    made = []
    monkeypatch.setattr("brain.media_provider.get_provider", lambda name: (_ for _ in ()).throw(AssertionError("must not generate")))
    edits = layer.clean({"2": {"source": "ai", "visual": "a brand new idea"}, "5": {"source": "upload", "media": "mine.png"}})
    decisions = layer.apply(DECISIONS, edits)
    pictures, slots = talking_reel.resolve_pictures(job, decisions, "talking_2", generate_missing=False)
    by_slot = {s["i"]: s for s in slots}
    assert by_slot[2]["source"] == "ai_planned" and 2 in pictures and not Path(pictures[2]).exists()   # planned, not generated
    assert by_slot[5]["source"] == "upload" and Path(pictures[5]).name == "mine.png"
    assert by_slot[8]["source"] == "ai_planned"                                                     # untouched slot: the AI's own prompt
    # editing the prompt changes the cache key, so the old image is never reused for the new idea
    original, _ = talking_reel.resolve_pictures(job, DECISIONS, "talking_2", generate_missing=False)
    assert pictures[2] != original[2]


def test_a_cached_image_counts_as_already_made(job):
    decisions = layer.apply(DECISIONS, layer.clean({"2": {"source": "ai", "visual": "cached idea"}}))
    _, slots = talking_reel.resolve_pictures(job, decisions, "talking_2", generate_missing=False)
    cached = Path(next(s for s in slots if s["i"] == 2)["file"]); cached.parent.mkdir(parents=True, exist_ok=True); cached.write_bytes(b"x")
    _, again = talking_reel.resolve_pictures(job, decisions, "talking_2", generate_missing=False)
    assert next(s for s in again if s["i"] == 2)["source"] == "ai"        # no longer "to be generated"


def test_plan_content_counts_only_pictures_that_still_have_to_be_made():
    from app import creative_plan
    status = {"style": "talking_2", "render_settings": {}, "music": "", "hook2": "ه", "creative_plan": {}}
    slots = [{"i": 2, "label": "الف", "source": "ai_planned"}, {"i": 5, "label": "ب", "source": "upload"}, {"i": 8, "label": "ج", "source": "ai"}]
    content = creative_plan.build_talking(status, sentences=[{"start": 0, "end": 1, "text": "x"}], video_seconds=10, estimate=None,
                                          has_logo=False, slots=slots)
    assert content["estimate"]["new_images"] == 1 and [p["new"] for p in content["pictures"]] == [True, False, False]
    assert "تصویر تازه" in creative_plan.summary_text(content, {"n": 1})
    edits = creative_plan.talking_edits(content, {"broll_edits": {"2": {"source": "hidden"}}}, status)
    assert edits["engine"]["broll_edits"] == {"2": {"source": "hidden"}}
    with pytest.raises(creative_plan.PlanError):
        creative_plan.talking_edits(content, {"broll_edits": {"2": {"source": "hidden"}}}, {**status, "style": "talking_1"})


def test_a_motion_scene_panel_is_not_offered_a_picture_editor_and_rejects_picture_edits(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from app import creative_plan, studio_orchestrator as o
    planned = SimpleNamespace(hyperframes=True, decisions=DECISIONS)
    monkeypatch.setattr(talking_reel, "plan_render", lambda *a, **k: planned)
    monkeypatch.setattr(talking_reel, "_library_pictures", lambda: [])
    job = SimpleNamespace(dir=tmp_path, raw_name="v.mp4")
    with pytest.raises(creative_plan.PlanError):
        o._validate_broll_edits(job, layer.clean({"2": {"source": "hidden"}}))
    planned.hyperframes = False
    o._validate_broll_edits(job, layer.clean({"2": {"source": "hidden"}}))
