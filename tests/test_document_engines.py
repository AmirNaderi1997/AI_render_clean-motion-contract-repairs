"""Localize and Motion timelines come from the renderers' own functions (shared placement, windows, timing)."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import project_document as documents
from engine import localize as media
from engine.schema import validate_plan


def edit_plan(transitions=(), segments=3):
    return {
        "version": "0.2", "style": "rafiei_reel", "canvas": {"width": 1080, "height": 1920, "fps": 30}, "source": "raw/v.mp4",
        "segments": [{"id": f"s{i + 1}", "in": i * 10.0, "out": i * 10.0 + 4.0} for i in range(segments)],
        "transitions": list(transitions), "captions": [{"start": 0.1, "end": 2.0, "text": "اول", "style": "cover"}],
        "export": {"file": "exports/v1.mp4"},
    }


def test_segment_placement_subtracts_transition_overlap():
    plan, errors = validate_plan(edit_plan([{"from_segment_id": "s1", "to_segment_id": "s2", "type": "crossfade", "duration_frames": 6},
                                            {"from_segment_id": "s2", "to_segment_id": "s3", "type": "zoom", "duration_frames": 10}]),
                                 check_media=False)
    assert errors == [] and plan.segment_frames() == [(0, 120), (114, 120), (224, 120)]
    assert plan.segment_frames()[-1][0] + plan.segment_frames()[-1][1] == plan.output_frames   # ends where the video ends
    bare, _ = validate_plan(edit_plan(), check_media=False)
    assert bare.segment_frames() == [(0, 120), (120, 120), (240, 120)]


def motion_job(tmp_path, plan=None, scenes=None):
    (tmp_path / "storyboard.json").write_text(json.dumps({"scenes": scenes or []}))
    return SimpleNamespace(dir=tmp_path, plan_data=plan, render=SimpleNamespace(status="done"), id="j")


def test_motion_document_follows_the_edit_plan(tmp_path, monkeypatch):
    plan = edit_plan([{"from_segment_id": "s1", "to_segment_id": "s2", "type": "crossfade", "duration_frames": 6}])
    plan["captions"] = [{"start": 0.1, "end": 2.0, "text": "اول", "style": "cover"}, {"start": 3.0, "end": 5.0, "text": "دوم", "style": "normal"}]
    plan["music"] = {"file": "assets/music/soft_lofi_loop.mp3", "volume_db": -18, "duck": []}
    plan["sfx"] = [{"at": 0.0, "file": "/server/secret/path/narration_full.mp3", "volume_db": 0}]
    monkeypatch.setattr("app.jobs.load_plan", lambda job: job.plan_data)
    doc = documents.motion_document(motion_job(tmp_path, plan, [{"duration_s": 4, "text_overlay": "صحنه"}] * 3))
    video = next(t for t in doc["tracks"] if t["id"] == "video")["elements"]
    assert [e["id"] for e in video] == ["segment:s1", "segment:s2", "segment:s3"]
    assert video[1]["start"] == pytest.approx(3.8) and video[2]["start"] == pytest.approx(7.8)        # 4.0 s minus a 0.2 s overlap
    assert doc["duration"] == pytest.approx(11.8)
    assert next(t for t in doc["tracks"] if t["id"] == "graphics")["elements"][0]["start"] == pytest.approx(3.8)
    assert [e["label"] for e in next(t for t in doc["tracks"] if t["id"] == "captions")["elements"]] == ["تیتر ابتدایی", "معمولی"]
    dumped = json.dumps(doc, ensure_ascii=False)
    assert "/server/secret/path" not in dumped and "narration_full.mp3" in dumped   # file names only, never server paths
    assert doc["basis"]["synced"] is None


def test_motion_without_a_plan_shows_the_storyboard_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr("app.jobs.load_plan", lambda job: (_ for _ in ()).throw(FileNotFoundError()))
    doc = documents.motion_document(motion_job(tmp_path, None, [{"duration_s": 3, "text_overlay": "الف", "narration_text": "نریشن یک"},
                                                                {"duration_s": 4, "text_overlay": "ب", "narration_text": "نریشن دو"}]))
    assert doc["duration"] == 7.0 and doc["notes"] and "استوری‌بورد" in doc["notes"][0]
    assert all(e["props"].get("planned") for t in doc["tracks"] for e in t["elements"] if t["id"] in {"video", "voice"})
    with pytest.raises(ValueError):
        documents.motion_document(motion_job(tmp_path, None, []))


STATE = {
    "id": "p1", "source": "raw/v.mp4", "name": "ویدیو", "end_card": True, "end_card_seconds": 3.5, "cta_number": "15",
    "title": "عنوان", "title_layout": {"start": 0.0, "end": 5.0}, "music": None, "caption_detector": "frame-outline-v6",
    "lines": [{"i": 0, "start": 1.0, "end": 3.0, "en": "Hello", "fa": "سلام", "kind": "speech", "covers": [{"start": 1.0, "end": 3.0, "box": {}}]},
              {"i": 1, "start": 8.0, "end": 9.0, "en": "Comment", "fa": "کامنت", "kind": "cta", "covers": []}],
    "placements": [{"i": 0, "start": 1.2, "end": 3.1, "tempo": 1.0, "file": "/x/a.wav"}, {"i": 1, "start": 8.0, "end": 9.0, "tempo": 1.0, "file": "/x/b.wav"}],
}


def test_localize_timing_is_shared_with_the_renderer_and_the_document(tmp_path, monkeypatch):
    duration, card_at = media.output_timing(STATE, STATE["placements"], 12.0)
    assert (card_at, duration) == (8.0, 11.5)                     # the card replaces the source's own CTA
    held = media.output_timing({**STATE, "end_card": False}, STATE["placements"], 12.0)
    assert held == (12.0, 12.0)
    from app import localize as store
    monkeypatch.setattr(store, "load", lambda _: STATE)
    monkeypatch.setattr(store, "_dir", lambda _: tmp_path)
    monkeypatch.setattr(media, "probe_video", lambda _: (1080, 1920, 12.0))
    monkeypatch.setattr(store, "resolve_music", lambda _: None)
    doc = documents.localize_document("p1")
    assert doc["duration"] == 11.5 and doc["content_duration"] == 8.0
    by_track = {t["id"]: t["elements"] for t in doc["tracks"]}
    assert [e["id"] for e in by_track["video"]] == ["source"] and by_track["video"][0]["end"] == 8.0
    assert by_track["outro"][0]["start"] == 8.0 and by_track["outro"][0]["end"] == 11.5
    assert [e["id"] for e in by_track["voice"]] == ["voice:l0", "voice:l1"]
    assert by_track["captions"][0]["text"] == "سلام" and by_track["captions"][0]["props"]["covers_english"] is True
    assert by_track["audio"][0]["end"] == pytest.approx(1.05)      # original audio until just before the first Persian clip
    assert "/x/a.wav" not in json.dumps(doc)


def test_localize_fingerprint_changes_with_the_render_but_not_with_bookkeeping():
    base = documents.localize_fingerprint(STATE)
    assert documents.localize_fingerprint({**STATE, "progress": 99, "updated_at": 5, "stage": "x"}) == base
    edited = json.loads(json.dumps(STATE)); edited["lines"][0]["fa"] = "درود"
    assert documents.localize_fingerprint(edited) != base
    assert documents.localize_fingerprint({**STATE, "cta_number": "31"}) != base


def test_opening_a_legacy_motion_job_in_studio_does_not_crash(tmp_path, monkeypatch):
    """open_legacy_project read `job.plan`, which Job never had: every legacy Motion/Talking open returned 500."""
    import asyncio
    from app import studio_store
    from app.routers import studio
    monkeypatch.setattr(studio_store, "DB_AVAILABLE", False)
    monkeypatch.setattr(studio_store, "ROOT", tmp_path)
    monkeypatch.setattr(studio_store, "FALLBACK", tmp_path / "studio.json")
    monkeypatch.setattr(studio, "get_job_for_request", lambda request, ref: SimpleNamespace(raw_name=None, plan_data={"title": "تیزر"}))
    async def nothing(*a): pass
    monkeypatch.setattr(studio, "sync_conversation", nothing)
    request = SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id="u")))
    body = studio.LegacyProjectOpen(engine="motion", external_ref="abcd1234", title="پروژه")
    result = asyncio.run(studio.open_legacy_project(request, body))
    assert result["title"] == "تیزر" and result["projects"][0]["engine"] == "motion"
