from pathlib import Path

import pytest

from app.product_reel import PageParser, _public_url
from engine.hyperframes.product import visual_beats
from engine.motion_recipes import BY_ID, public_recipes, select_recipe


def test_page_parser_extracts_public_product_facts():
    parser = PageParser()
    parser.feed("""<html><head><title>Acme | Home</title>
      <meta property="og:title" content="Acme AI"><meta name="description" content="Useful product">
      <style>:root{--brand:#12AB34}</style></head><body><h1>Ship faster</h1><p>No invented claims.</p></body></html>""")
    assert parser.title == "Acme | Home"
    assert parser.meta["og:title"] == "Acme AI"
    assert parser.headings == ["Ship faster"]
    assert parser.paragraphs == ["No invented claims."]


def test_private_url_is_rejected(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *args: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ValueError, match="private"):
        _public_url("https://internal.example")


def test_recipe_registry_is_unique_and_renderable():
    items = public_recipes()
    assert len(items) >= 20
    assert len({item["id"] for item in items}) == len(items)
    assert all(item["renderer"] for item in items)


def test_semantic_recipe_choice_and_restraint():
    used = {}
    first = select_recipe(role="price", title="قیمت ۲۰ دلار", items=["۱ دلار"], used=used)
    assert first.renderer in {"stat", "comparison"}
    used[first.id] = first.max_per_video
    second = select_recipe(role="price", title="قیمت دوم", items=[], used=used)
    assert second.id != first.id


def test_product_board_becomes_contiguous_visual_beats():
    board = {"scenes": [
        {"role": "hook", "title": "A", "items": [], "duration": 2.5, "recipe": "kinetic-hook-slam"},
        {"role": "steps", "title": "B", "items": ["1", "2"], "duration": 3, "recipe": "steps-rail"},
        {"role": "cta", "title": "C", "items": [], "duration": 2.5, "recipe": "cta-lockup"},
    ]}
    beats, duration = visual_beats(board)
    assert duration == 8.0
    assert [beat.start for beat in beats] == [0.0, 2.5, 5.5]
    assert [beat.recipe_id for beat in beats] == ["kinetic-hook-slam", "steps-rail", "cta-lockup"]
    assert all(beat.layout == "full_frame" for beat in beats)
