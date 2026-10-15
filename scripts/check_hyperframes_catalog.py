#!/usr/bin/env python3
"""Fast integrity check for the frozen visual catalog."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.hyperframes.catalog import catalog_stats, load_catalog, recommend


def main() -> None:
    data = load_catalog()
    items = data["items"]
    names = [item["name"] for item in items]
    assert len(items) >= 400, "official catalog is unexpectedly incomplete"
    assert len(names) == len(set(names)), "duplicate catalog names"
    assert all(item.get("source") == "hyperframes-official" for item in items)
    for visual_type in ("stat", "comparison", "steps", "ui_showcase", "media_collage",
                        "chat", "map_route", "spec_callout", "kinetic_type", "before_after"):
        results = recommend(visual_type)
        assert results, f"no recommendation for {visual_type}"
        assert len(results) <= 3
    stats = catalog_stats()
    print(f"catalog ok: {stats['count']} official items, {len(data['external_references'])} external references")


if __name__ == "__main__":
    main()
