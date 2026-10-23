"""Project Document: tracks and stable ids from the exact render plan (no media generated)."""
from pathlib import Path

import pytest

from app import project_document, talking_reel
from engine.talking_styles import talking_2 as t2
from engine.talking_styles.talking_1 import CTA_SECONDS, LOGO_SECONDS

SENTENCES = [{"start": 0.0, "end": 4.0, "text": "اول"}, {"start": 4.0, "end": 9.0, "text": "دوم"},
             {"start": 9.0, "end": 14.0, "text": "سوم"}]


def planned(caption_text="کپشن", cta="فالو کن", logo=True):
    shots = [t2.Shot(0.0, 3.5, split=True, slot=0, picture="/x/ai_1.png", out_start=0.0),
             t2.Shot(4.2, 8.8, split=True, slot=1, picture="/x/up.jpg", out_start=3.5),
             t2.Shot(9.1, 13.0, split=True, slot=1, picture="/x/up.jpg", out_start=8.1)]
    plan = t2.ReelPlan(shots=shots, captions=[{"start": 0.1, "end": 1.5, "lead": "", "key": caption_text},
                                              {"start": 1.6, "end": 3.0, "lead": "و", "key": "بعد"},
                                              {"start": 4.0, "end": 5.0, "lead": "", "key": "دوم"}],
                       chips=[{"start": 8.2, "end": 10.0, "items": ["الف", "ب"]}], hook={"start": 0, "end": 3, "text": "هوک"},
                       duration=12.0)
    slots = [{"i": 0, "source": "ai_planned", "label": "تصویر یک"}, {"i": 1, "source": "upload", "label": "تصویر دو"}]
    reel = talking_reel.PlannedReel("talking_2", t2, {"sentences": SENTENCES}, {}, {"outro_logo": {"enabled": logo}},
                                    plan, pictures={}, slots=slots)
    state = {"style": "talking_2", "hook2": "هوک", "cta": cta}
    return reel, state


@pytest.fixture
def document(monkeypatch, tmp_path):
    def build(**kwargs):
        reel, state = planned(**kwargs)
        monkeypatch.setattr(talking_reel, "plan_render", lambda *a, **k: reel)
        monkeypatch.setattr(talking_reel, "load", lambda _: state)
        monkeypatch.setattr(talking_reel, "resolve_music", lambda _: None)
        monkeypatch.setattr(talking_reel, "custom_logo", lambda _: None)
        return project_document.talking_document(tmp_path, tmp_path / "v.mp4")
    return build


def ids(doc, track):
    return [e["id"] for t in doc["tracks"] if t["id"] == track for e in t["elements"]]


def test_music_track_always_exists_so_a_bed_can_be_chosen(document):
    doc = document()
    music = next(e for t in doc["tracks"] if t["id"] == "music" for e in t["elements"])
    assert music["props"]["path"] is None and music["label"] == "بدون موسیقی"
    assert {"volume_db", "fade_in", "fade_out", "duck", "defaults", "library"} <= set(music["props"])
    assert music["edit"]["via"] == ["timeline", "chat"]


def test_tracks_follow_the_render_plan(document):
    doc = document()
    assert [t["id"] for t in doc["tracks"]] == ["video", "panel", "titles", "captions", "graphics", "voice", "music", "outro"]
    assert ids(doc, "video") == ["clip:0", "clip:4200", "clip:9100"]
    assert ids(doc, "panel") == ["picture:s0", "picture:s1"]       # contiguous runs of one slot merge
    panel = {e["id"]: e for t in doc["tracks"] if t["id"] == "panel" for e in t["elements"]}
    assert panel["picture:s0"]["source"]["kind"] == "ai_planned" and panel["picture:s1"]["end"] == 12.0
    assert ids(doc, "captions") == ["caption:s0:0", "caption:s0:1", "caption:s1:0"]
    assert ids(doc, "graphics") == ["chips:s2"]   # output 8.2s is source 9.2s: the third sentence
    assert doc["duration"] == pytest.approx(12.0 + CTA_SECONDS + LOGO_SECONDS)


def test_ids_survive_text_edits_and_outro_follows_settings(document):
    before, after = document(caption_text="قبل"), document(caption_text="بعد از اصلاح")
    assert ids(before, "captions") == ids(after, "captions")
    no_outro = document(cta="", logo=False)
    assert "outro" not in [t["id"] for t in no_outro["tracks"]] and no_outro["duration"] == 12.0


def test_every_element_is_honest_about_how_it_changes(document):
    for track in document()["tracks"]:
        for element in track["elements"]:
            assert set(element["edit"]["via"]) <= {"plan", "chat", "timeline"}
            assert element["end"] >= element["start"]
