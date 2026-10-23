"""Localize captions can be moved, resized and recoloured; projects without looks render exactly as before."""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import localize_overlay_fixture as fx                      # noqa: E402
from app import localize as store, localize_clean_base, project_document   # noqa: E402
from engine import localize as media                        # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def events(ass, layer=None):
    rows = [line for line in ass.splitlines() if line.startswith("Dialogue: ")]
    return [row for row in rows if layer is None or row.startswith(f"Dialogue: {layer},")]


def test_projects_without_looks_render_byte_identical_ass():
    assert fx.build() == (FIXTURES / "localize_overlays.ass").read_text()
    assert fx.build(fx.state("frame-outline-v3")) == (FIXTURES / "localize_overlays_uncovered.ass").read_text()
    empty = fx.state(); empty["caption_looks"] = {}
    assert fx.build(empty) == (FIXTURES / "localize_overlays.ass").read_text()


def test_caption_ids_are_line_and_window_number():
    windows = media.caption_windows(fx.state(), fx.PLACEMENTS, 11.0)
    assert media.caption_ids(windows) == ["caption:l0:0", "caption:l0:1", "caption:l2:0"]


def test_a_look_moves_scales_and_recolours_the_whole_caption():
    state = fx.state()
    frames = {}
    fx.build(state, frames=frames)
    f = frames[0]
    state["caption_looks"] = {"caption:l0:0": {"x": 300, "y": 500, "scale": 0.5, "color": "#FF0000"}}
    ass = fx.build(state)
    base = fx.build()
    # the first card keeps its original cover and gets a moved box + text on top of it
    layer3 = [e for e in events(ass, 3) if "0:00:01.00,0:00:02.40" in e]
    assert len(layer3) == 2 and layer3[0] == [e for e in events(base, 3) if "0:00:01.00,0:00:02.40" in e][0]
    box_x, box_y = map(float, re.search(r"\\pos\(([\d.]+),([\d.]+)\)", layer3[1]).groups())
    assert box_x == pytest.approx(300 - 0.5 * f["w"] / 2, abs=0.2) and box_y == pytest.approx(500 - 0.5 * f["h"] / 2, abs=0.2)
    text = [e for e in events(ass, 4) if "0:00:01.00,0:00:02.40" in e][0]
    assert f"\\fs{round(f['size'] * 0.5)}" in text and "\\1c&H0000FF&" in text      # BGR red
    # other captions are untouched
    second = lambda a: [e for e in events(a, 4) if e.split(",")[1] == "0:00:02.40"]
    assert second(ass) == second(base) and len(second(ass)) == 1


def test_recolouring_in_place_adds_no_second_cover():
    state = fx.state()
    state["caption_looks"] = {"caption:l0:0": {"color": "#00FF00"}}
    ass = fx.build(state)
    assert len([e for e in events(ass, 3) if "0:00:01.00,0:00:02.40" in e]) == 1
    assert "\\1c&H00FF00&" in [e for e in events(ass, 4) if "0:00:01.00,0:00:02.40" in e][0]


def test_a_caption_without_a_source_card_just_moves():
    state = fx.state("frame-outline-v3")
    state["caption_looks"] = {"caption:l1:0": {"y": 900}}
    ass, base = fx.build(state), fx.build(fx.state("frame-outline-v3"))
    assert len(events(ass)) == len(events(base))
    moved = [e for e in events(ass, 3) if "0:00:04.50" in e][0]
    assert float(re.search(r"\\pos\([\d.]+,([\d.]+)\)", moved).group(1)) < 900


def test_covers_mode_keeps_only_the_covers():
    base = events(fx.build(only_covers=True))
    assert not [e for e in base if ",caption," in e and e.startswith(("Dialogue: 4", "Dialogue: 3"))]
    covers = [e for e in base if e.startswith("Dialogue: 3,")]
    assert len(covers) == 3                                   # the three source cards stay hidden
    assert all(e in events(fx.build()) for e in covers)       # the very same cover events the render draws


def test_frames_are_reported_without_looks():
    frames = {}
    state = fx.state(); state["caption_looks"] = {"caption:l0:0": {"x": 10, "scale": 2}}
    fx.build(state, frames=frames)
    plain = {}
    fx.build(fx.state(), frames=plain)
    assert frames == plain and set(frames) == {0, 1, 2} and frames[0]["cover"] and frames[0]["lines"]


# -- storage ----------------------------------------------------------------------------------

@pytest.fixture
def project(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "LOCALIZE_ROOT", tmp_path)
    root = tmp_path / "abcdef123456"
    (root / "exports").mkdir(parents=True)
    (root / "raw").mkdir()
    state = {**fx.state(), "id": "abcdef123456", "source": "raw/a.mp4", "status": "done", "placements": fx.PLACEMENTS,
             "end_card": True, "cta_number": "31"}
    (root / "state.json").write_text(json.dumps(state))
    monkeypatch.setattr(media, "probe_video", lambda _p: (1080, 1920, 10.0))
    return state["id"]


def test_looks_are_validated_and_saved_per_caption(project):
    saved = store.set_caption_looks(project, [{"id": "caption:l0:1", "x": 540, "y": 700.456, "scale": 1.5, "color": "#aabbcc"}])
    assert saved["caption_looks"] == {"caption:l0:1": {"x": 540.0, "y": 700.46, "scale": 1.5, "color": "#AABBCC"}}
    for bad in ({"x": 2000}, {"scale": 9}, {"color": "red"}, {"y": "abc"}):
        with pytest.raises(ValueError):
            store.set_caption_looks(project, [{"id": "caption:l0:0", **bad}])
    with pytest.raises(ValueError, match="unknown caption"):
        store.set_caption_looks(project, [{"id": "caption:l9:0", "x": 1}])
    assert store.load(project)["caption_looks"].keys() == {"caption:l0:1"}          # failed edits changed nothing
    store.set_caption_looks(project, [{"id": "caption:l0:1", "reset": True}])
    assert "caption_looks" not in store.load(project)


def test_editing_never_starts_a_render(project, monkeypatch):
    monkeypatch.setattr(store, "_start", lambda *a, **k: pytest.fail("an edit must not start a render"))
    store.set_caption_looks(project, [{"id": "caption:l0:0", "x": 100}])


def test_a_busy_project_refuses_edits(project):
    store._running.add(project)
    try:
        with pytest.raises(ValueError, match="busy"):
            store.set_caption_looks(project, [{"id": "caption:l0:0", "x": 100}])
    finally:
        store._running.discard(project)


def test_looks_change_the_fingerprint_only_when_present(project):
    state = store.load(project)
    base = project_document.localize_fingerprint(state)
    assert project_document.localize_fingerprint({**state, "caption_looks": {}}) == base
    assert project_document.localize_fingerprint({**state, "caption_looks": {"caption:l0:0": {"x": 1}}}) != base


def test_document_exposes_frames_and_looks(project, monkeypatch):
    monkeypatch.setattr(media, "measure_text_boxes", fx.fake_boxes)
    store.set_caption_looks(project, [{"id": "caption:l0:0", "x": 300, "y": 500, "scale": 0.5}])
    doc = project_document.localize_document(project)
    captions = {e["id"]: e for t in doc["tracks"] if t["id"] == "captions" for e in t["elements"]}
    assert list(captions) == ["caption:l0:0", "caption:l0:1"]   # the CTA starts the end card
    first = captions["caption:l0:0"]
    frame = first["props"]["frame"]
    assert first["edit"]["via"][0] == "timeline" and first["props"]["look"] == {"x": 300.0, "y": 500.0, "scale": 0.5}
    assert frame["boxed"] and frame["font_file"] and frame["lines"]
    assert frame["rect"]["w"] == pytest.approx(frame["now"]["w"] * 2) and frame["now"]["x"] + frame["now"]["w"] / 2 == pytest.approx(300, abs=0.2)
    assert doc["edit_count"] == 1 and doc["stale_edits"] == [] and doc["basis"]["synced"] is None


def test_document_is_read_only_without_a_1080x1920_frame(project, monkeypatch):
    monkeypatch.setattr(media, "measure_text_boxes", fx.fake_boxes)
    monkeypatch.setattr(media, "probe_video", lambda _p: (1920, 1080, 10.0))
    doc = project_document.localize_document(project)
    first = next(e for t in doc["tracks"] if t["id"] == "captions" for e in t["elements"])
    assert first["props"]["frame"] is None and "timeline" not in first["edit"]["via"]


# -- editing preview ---------------------------------------------------------------------------

def test_preview_needs_voice_already_made(project, tmp_path, monkeypatch):
    status = localize_clean_base.status(project)
    assert status["state"] == "unsupported" and "صدا" in status["reason"]      # the clips named in placements do not exist
    for p in fx.PLACEMENTS:
        Path(tmp_path / p["file"]).write_bytes(b"")
    state = store.load(project)
    for p, real in zip(state["placements"], fx.PLACEMENTS):
        p["file"] = str(tmp_path / real["file"])
    store.save(state)
    assert localize_clean_base.status(project)["state"] == "missing"
    key = localize_clean_base.status(project)["key"]
    store.set_caption_looks(project, [{"id": "caption:l0:0", "x": 100}])
    assert localize_clean_base.status(project)["key"] == key                  # moving captions never makes it stale


def test_preview_is_built_without_captions_or_voice_calls(project, tmp_path, monkeypatch):
    state = store.load(project)
    for p in state["placements"]:
        p["file"] = str(tmp_path / p["file"]); Path(p["file"]).write_bytes(b"")
    store.save(state)
    seen = {}

    def fake_render(video, style, placements, out, **kwargs):
        seen.update(kwargs, out=out); out.write_bytes(b"mp4")
    monkeypatch.setattr(media, "render", fake_render)
    import brain.localize as voice
    monkeypatch.setattr(voice, "synthesize_narration", lambda *a, **k: pytest.fail("the preview must not call the voice service"))
    monkeypatch.setattr(voice, "synthesize", lambda *a, **k: pytest.fail("the preview must not call the voice service"))
    import threading
    started = []
    real_thread = threading.Thread
    monkeypatch.setattr(threading, "Thread", lambda target, daemon: type("T", (), {"start": lambda self: (target(), started.append(1))})())
    assert localize_clean_base.ensure(project)["state"] == "building"
    assert started and seen["only_covers"] is True
    assert localize_clean_base.status(project)["state"] == "ready"
