"""Versioned HyperFrames catalog lookup for talking-reel visual planning.

The committed index is metadata only.  Catalog HTML is never executed by the
API process; renderable visuals continue to use our audited vertical adapters.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path


INDEX = Path(__file__).with_name("catalog_index.json")

TYPE_TAGS = {
    "concept": ("diagram", "editorial", "symbol", "callout", "flowchart"),
    "stat": ("stat", "counter", "progress", "data-viz", "metric", "chart"),
    "comparison": ("comparison", "versus", "split", "before-after"),
    "steps": ("steps", "list", "timeline", "process", "flowchart"),
    "ui_showcase": ("mock-ui", "app", "product", "interface", "dashboard"),
    "media_collage": ("collage", "carousel", "gallery", "editorial"),
    "chat": ("chat", "message", "conversation", "social"),
    "map_route": ("map", "route", "travel", "location"),
    "spec_callout": ("spec", "callout", "feature", "list"),
    "kinetic_type": ("kinetic", "typography", "title", "text"),
    "before_after": ("before-after", "wipe", "comparison", "reveal"),
}

PREFERRED = {
    "concept": ("flowchart", "mk-callout-highlight", "editorial-flash-overlay"),
    "stat": ("mk-progress-stat", "data-chart", "stat-counter"),
    "comparison": ("comparison-split", "before-after-wipe"),
    "steps": ("flowchart", "mk-specs-list"),
    "ui_showcase": ("app-showcase", "ai-chat-reveal"),
    "media_collage": ("paper-collage-reveal",),
    "chat": ("message-thread-reveal", "chat-thread"),
    "map_route": ("world-map",),
    "spec_callout": ("mk-specs-list", "mk-callout-highlight"),
    "kinetic_type": ("caption-kinetic-slam", "mk-emphasis-type"),
    "before_after": ("before-after-wipe", "comparison-split"),
}


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9-]+", value.lower()))


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    if not INDEX.exists():
        return {"items": [], "sources": []}
    return json.loads(INDEX.read_text())


def catalog_stats() -> dict:
    data = load_catalog()
    items = data.get("items", [])
    return {
        "count": len(items),
        "blocks": sum(item.get("type") == "block" for item in items),
        "components": sum(item.get("type") == "component" for item in items),
        "portrait": sum(item.get("orientation") == "portrait" for item in items),
        "sources": data.get("sources", []),
        "version": data.get("hyperframes_version"),
    }


def recommend(visual_type: str, title: str = "", *, limit: int = 3) -> list[dict]:
    """Return catalog references ranked for a 9:16 talking-head overlay.

    Results are inspiration/provenance for the audited local adapter.  They do
    not cause remote registry code to run inside a render job.
    """
    wanted = set(TYPE_TAGS.get(visual_type, TYPE_TAGS["concept"]))
    title_tokens = _tokens(title)
    ranked = []
    for item in load_catalog().get("items", []):
        haystack = _tokens(" ".join([
            str(item.get("name", "")), str(item.get("title", "")),
            str(item.get("description", "")), " ".join(item.get("tags", [])),
        ]))
        tag_score = len(wanted & haystack) * 5
        text_score = len(title_tokens & haystack) * 2
        orientation_score = {"portrait": 4, "square": 2, "landscape": 0}.get(item.get("orientation"), 1)
        component_score = 2 if item.get("type") == "component" else 0
        preferred = PREFERRED.get(visual_type, ())
        preferred_score = (len(preferred) - preferred.index(item.get("name"))) * 20 if item.get("name") in preferred else 0
        score = tag_score + text_score + orientation_score + component_score + preferred_score
        if score:
            ranked.append((score, item.get("name", ""), item))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [item for _, _, item in ranked[:limit]]
