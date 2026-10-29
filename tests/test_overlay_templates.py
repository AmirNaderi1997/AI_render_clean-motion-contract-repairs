"""Exercise the talking_5 page boundary, local pins and typed registry fields."""
import hashlib
import json
from html.parser import HTMLParser

import pytest

from creative import panel_library as library
from creative.style_packs import REFERENCE_AI_NEWS
from engine.hyperframes import overlay_reel, registry_runtime


class Mounts(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.values = []
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "data-variable-values" in attrs:
            self.values.append(json.loads(attrs["data-variable-values"]))


def build(tmp_path, monkeypatch, **beat):
    gsap = tmp_path / "gsap.js"
    gsap.write_text("local")
    monkeypatch.setattr("engine.hyperframes.assets.ensure_gsap", lambda: gsap)
    script = {"duration": 4, "segments": [{"start": 0, "end": 4, "layout": "split", "beat": {
        "title": "۱۲ گام ساده", "visual_type": "kinetic_type", "component_id": "headline-slam", **beat}}]}
    entry = overlay_reel.build_project(tmp_path / "project", REFERENCE_AI_NEWS, script, part="panel")
    return entry, script


def test_legacy_overlay_is_replaced_and_recorded(tmp_path, monkeypatch):
    entry, script = build(tmp_path, monkeypatch, custom={"html": "EVIL_HTML", "css": "EVIL_CSS", "js": "EVIL_JS", "bg": "EVIL_BG"})
    for path in entry.parent.rglob("*"):
        if path.is_file():
            assert "EVIL_" not in path.read_text(errors="replace")
    seg = script["segments"][0]
    assert seg["layout"] == "split" and seg["component"] == "headline-slam"
    assert "legacy authored panel replaced" in seg["template_resolution"]["reason"]
    assert "custom" not in seg["beat"]
    receipt = json.loads((entry.parent / "resource-receipts/headline-slam.json").read_text())
    component = entry.parent / "compositions/components/headline-slam.html"
    assert receipt["adapted_sha256"] == hashlib.sha256(component.read_bytes()).hexdigest()
    assert "https://cdn" not in component.read_text()
    assert 'lang="fa" dir="rtl"' in component.read_text()
    assert "letter-spacing: -" not in component.read_text()


def test_registry_text_is_attribute_escaped_and_never_written_into_source(tmp_path, monkeypatch):
    text = "سلام 12 </script><img src=x onerror=alert(1)> ' & \\\\"
    entry, _ = build(tmp_path, monkeypatch, title=text)
    page = entry.read_text()
    assert "<img src=x" not in page
    values = Mounts(page).values
    from engine.persian_text import display_text
    assert values[0]["text"] == display_text(text)
    assert text not in (entry.parent / "compositions/components/headline-slam.html").read_text()


@pytest.mark.parametrize("name", ["../../evil", "unlisted", "notes-typing", "perspective-marquee"])
def test_unreviewed_component_cannot_load(name):
    with pytest.raises(ValueError):
        library.validate_values(name, {"text": "سلام"})


@pytest.mark.parametrize("values", [{"html": "<b>bad</b>"}, {"text": {}}, {"text": "x" * 1001}, {"accent_word_index": float("nan")}, {"accent_word_index": True}])
def test_component_fields_are_typed_content_only(values):
    with pytest.raises(ValueError):
        library.validate_values("headline-slam", values)


def test_corrupt_source_keeps_a_builtin_panel_and_records_fallback(tmp_path, monkeypatch):
    import shutil
    source = tmp_path / "library"
    shutil.copytree(library.LIBRARY_DIR, source)
    (source / "headline-slam.html").write_text("BAD_SOURCE")
    monkeypatch.setattr(library, "LIBRARY_DIR", source)
    monkeypatch.setattr(library, "choose", lambda *a, **k: ("headline-slam", {"text": "سلام", "accent_word_index": 0}))
    entry, script = build(tmp_path, monkeypatch)
    assert "۱۲" in entry.read_text() and "BAD_SOURCE" not in entry.read_text()
    assert script["segments"][0]["component"] == "builtin:kinetic_type"
    assert "integrity unavailable" in script["segments"][0]["template_resolution"]["reason"]


def test_all_enabled_adapters_accept_their_fields_and_pin_their_sources():
    assert set(library.available()) == library.SAFE_COMPONENTS
    for name in library.available():
        values = library.LIBRARY[name].fill({"title": "۱۲ گام", "items": ["یک", "دو", "سه"]}, 4)
        assert library.validate_values(name, values) == values


def test_older_registry_adapter_serializes_data_without_script_breakout(tmp_path, monkeypatch):
    path = tmp_path / "compositions/components/caption-kinetic-slam.html"
    path.parent.mkdir(parents=True)
    path.write_text("<script>var WORDS = [\n];</script>")
    monkeypatch.setattr(registry_runtime, "_install", lambda *a: True)
    assert registry_runtime._component(tmp_path, "caption-kinetic-slam", 4, ["</script><script>alert(1)</script>\\1"])
    source = path.read_text()
    assert source.count("<script>") == 1 and "\\u003c" in source
