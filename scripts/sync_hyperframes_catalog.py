#!/usr/bin/env python3
"""Freeze the complete official HyperFrames catalog as safe metadata."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "engine" / "hyperframes" / "catalog_index.json"
DEFAULT_VERSION = "0.8.161"

RVE_TEMPLATES = [
    ("aurora-headline", "Aurora Headline", "text", "Masked kinetic type over an aurora wash with grain and bloom"),
    ("prism-lower-third", "Prism Lower Third", "overlay", "Glass name badge with tilt, light bar and sheen"),
    ("liquid-counter", "Liquid Counter", "data", "Number filled by an animated liquid treatment"),
    ("signal-line", "Signal Line", "data", "Area chart with a glowing leading dot and gradient fill"),
    ("notification-stack", "Notification Stack", "social", "Springing glass notifications with depth blur"),
    ("light-leak-wipe", "Light Leak Wipe", "transition", "Light-leak scene wipe with an RGB fringe"),
    ("particle-wordmark", "Particle Wordmark", "text", "Particle-built wordmark treatment"),
    ("spotlight-testimonial", "Spotlight Testimonial", "social", "Focused animated testimonial card"),
    ("radial-gauge", "Radial Gauge", "data", "Animated radial metric gauge"),
    ("ranked-bars", "Ranked Bars", "data", "Animated ranked bar comparison"),
    ("metric-grid", "Metric Grid", "data", "Grid of animated key metrics"),
    ("dual-area-chart", "Dual Area Chart", "data", "Two-series animated area chart"),
    ("activity-rings", "Activity Rings", "data", "Concentric animated progress rings"),
    ("kinetic-title", "Kinetic Title", "text", "Animated kinetic title treatment"),
    ("lower-third", "Lower Third", "overlay", "Animated lower-third identification card"),
    ("follow-pill", "Follow Pill", "social", "Animated social follow prompt"),
    ("animated-bar-chart", "Animated Bar Chart", "data", "Animated categorical bar chart"),
    ("stat-counter", "Stat Counter", "data", "Animated numeric statistic"),
    ("fade-through-white", "Fade Through White", "transition", "Clean fade-through-white transition"),
]


def orientation(dimensions: dict | None) -> str:
    dimensions = dimensions or {}
    width, height = dimensions.get("width", 0), dimensions.get("height", 0)
    if not width or not height:
        return "overlay"
    if height > width:
        return "portrait"
    if height == width:
        return "square"
    return "landscape"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=DEFAULT_VERSION)
    args = parser.parse_args()
    command = ["npx", "--yes", f"hyperframes@{args.version}", "catalog", "--json"]
    raw = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True).stdout
    official = json.loads(raw)
    items = []
    for value in official:
        dimensions = value.get("dimensions")
        item = {
            "name": value["name"], "type": value.get("type", "block"),
            "title": value.get("title", value["name"]),
            "description": value.get("description", ""), "tags": value.get("tags", []),
            "dimensions": dimensions, "duration": value.get("duration"),
            "orientation": orientation(dimensions), "source": "hyperframes-official",
            "install": f"npx hyperframes add {value['name']}",
        }
        items.append({key: val for key, val in item.items() if val is not None})
    payload = {
        "schema_version": 1, "hyperframes_version": args.version,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "sources": [
            {"id": "hyperframes-official", "url": "https://hyperframes.heygen.com/catalog", "count": len(items)},
            {"id": "react-video-editor", "url": "https://www.reactvideoeditor.com/hyperframes-templates", "count": len(RVE_TEMPLATES), "usage": "reference-only"},
        ],
        "items": items,
        "external_references": [
            {"name": name, "title": title, "category": category, "description": description,
             "source": "react-video-editor", "url": f"https://www.reactvideoeditor.com/hyperframes-templates/{name}"}
            for name, title, category, description in RVE_TEMPLATES
        ],
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(OUTPUT), "official": len(items), "external": len(RVE_TEMPLATES)}))


if __name__ == "__main__":
    main()
