import pytest

from creative import panel_library, style_packs


def test_presets_validate_and_roundtrip():
    for pack in style_packs.PRESETS.values():
        again = style_packs.parse(pack.model_dump_json())
        assert again == pack


def test_a_pack_with_a_bad_colour_is_rejected():
    data = style_packs.REFERENCE_AI_NEWS.model_dump()
    data["palette"]["accent"] = "red"
    with pytest.raises(ValueError):
        style_packs.parse(data)


def test_library_never_repeats_a_component_in_one_reel():
    beats = [{"title": "فروش خدمات به ثروت نمی‌رسونه", "items": ["گوشی", "دوره", "پادکست"], "visual_type": "concept"}] * 4
    used: set[str] = set()
    names = []
    for index, beat in enumerate(beats):
        pick = panel_library.choose(beat, used, seed=str(index))
        assert pick
        names.append(pick[0])
        used.add(pick[0])
    assert len(set(names)) == len(names)


def test_roles_follow_the_beat():
    assert panel_library.role_of({"title": "الف یا ب", "items": ["الف", "ب"], "visual_type": "comparison"}) == "compare"
    assert panel_library.role_of({"title": "رشد ۳۰٪", "items": [], "visual_type": "stat"}) == "stat"
    assert panel_library.role_of({"title": "سه چیز", "items": ["۱", "۲", "۳"], "visual_type": "concept"}) == "list"


def test_vendored_components_match_their_manifest():
    import hashlib
    import json
    manifest = json.loads((panel_library.LIBRARY_DIR / "MANIFEST.json").read_text())
    for name, meta in manifest["files"].items():
        data = (panel_library.LIBRARY_DIR / f"{name}.html").read_bytes()
        assert hashlib.sha256(data).hexdigest() == meta["sha256"], name
