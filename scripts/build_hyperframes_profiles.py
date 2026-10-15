#!/usr/bin/env python3
"""Build a code-aware registry index from an official HyperFrames checkout."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROLE_RULES = {
    "transition": {"transition", "wipe", "reveal", "dissolve", "iris", "morph"},
    "caption": {"caption", "captions", "karaoke", "subtitle"},
    "typography": {"typography", "title", "headline", "text-effect", "kinetic"},
    "data_viz": {"data-viz", "chart", "stat", "counter", "map", "flowchart", "diagram"},
    "product_ui": {"mock-ui", "product-demo", "showcase", "device", "cursor", "app"},
    "social": {"social", "lower-third", "follow", "notification", "post"},
    "media_treatment": {"media-treatment", "overlay", "film", "grain", "light-leak", "texture"},
    "vfx": {"vfx", "shader", "webgl", "three-js", "particles", "3d"},
    "background": {"background", "ambient", "aurora", "gradient", "noise"},
}


def _orientation(item: dict) -> str:
    dims = item.get("dimensions") or {}
    width, height = int(dims.get("width") or 0), int(dims.get("height") or 0)
    if width and height:
        if height > width * 1.25:
            return "portrait"
        if width > height * 1.25:
            return "landscape"
        return "square"
    return str(item.get("orientation") or "overlay")


def _roles(item: dict) -> list[str]:
    words = set(re.findall(r"[a-z0-9-]+", " ".join([
        str(item.get("name", "")), str(item.get("title", "")),
        str(item.get("description", "")), " ".join(item.get("tags") or []),
    ]).lower()))
    found = [role for role, hints in ROLE_RULES.items() if words & hints]
    return found or ["general"]


def profile(manifest: Path) -> dict:
    item = json.loads(manifest.read_text())
    directory = manifest.parent
    code_parts = []
    for path in directory.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".html", ".js", ".mjs", ".ts", ".tsx", ".css"}:
            try:
                code_parts.append(path.read_text(errors="ignore"))
            except OSError:
                pass
    code = "\n".join(code_parts)
    lower = code.lower()
    variables_match = re.search(r"data-composition-variables=['\"](\[.*?\])['\"]", code, re.S)
    variables = []
    if variables_match:
        try:
            variables = [str(value.get("id")) for value in json.loads(variables_match.group(1))]
        except (json.JSONDecodeError, AttributeError):
            pass
    tags = [str(value) for value in item.get("tags") or []]
    roles = _roles(item)
    orientation = _orientation(item)
    files = [str(value.get("target") or value.get("path") or "") for value in item.get("files") or []]
    external_media = bool(re.search(r"(?:src|href)\s*=\s*['\"](?:https?:|\.?\.?/assets/)", code, re.I))
    has_slot = "data-slot" in lower or "<slot" in lower
    runtime = {
        "gsap": "gsap" in lower,
        "three": "three." in code or "three.min.js" in lower,
        "webgpu": "typegpu" in lower or "webgpu" in lower,
        "d3": "d3." in code or "d3.min.js" in lower,
        "svg": "<svg" in lower,
        "canvas": "<canvas" in lower,
        "lottie": "lottie" in lower,
        "audio": "<audio" in lower or "data-has-audio" in lower,
    }
    talk_score = 0
    talk_score += 8 if orientation in {"portrait", "overlay"} else -3
    talk_score += 5 if set(roles) & {"caption", "typography", "data_viz", "product_ui", "social", "media_treatment"} else 0
    talk_score += 4 if has_slot or variables else 0
    talk_score -= 5 if runtime["webgpu"] else 0
    talk_score -= 3 if external_media else 0
    talk_score -= 2 if float(item.get("duration") or 0) > 12 else 0
    best_for = []
    if "caption" in roles or "typography" in roles:
        best_for.append("spoken hook or emphasized phrase")
    if "data_viz" in roles:
        best_for.append("number, comparison, process, route, or factual evidence")
    if "product_ui" in roles:
        best_for.append("software, app, workflow, or product demonstration")
    if "transition" in roles:
        best_for.append("handoff between two motivated visual worlds")
    if "media_treatment" in roles:
        best_for.append("footage polish or a motivated reveal")
    avoid_when = []
    if orientation == "landscape":
        avoid_when.append("direct 9:16 insert without portrait adaptation")
    if external_media:
        avoid_when.append("required assets are not supplied or replaced")
    if runtime["webgpu"]:
        avoid_when.append("the render browser lacks verified WebGPU support")
    if not variables and not has_slot:
        avoid_when.append("story-specific content cannot be safely customized")
    return {
        "name": item.get("name"), "type": item.get("type"), "title": item.get("title"),
        "description": item.get("description"), "tags": tags, "roles": roles,
        "orientation": orientation, "dimensions": item.get("dimensions"),
        "duration": item.get("duration"), "preview": item.get("preview"),
        "variables": variables, "has_slot": has_slot, "runtime": runtime,
        "external_media": external_media, "files": files,
        "registry_dependencies": item.get("registryDependencies") or [],
        "talking_reel_score": talk_score, "best_for": best_for, "avoid_when": avoid_when,
        "install": f"npx hyperframes add {item.get('name')}",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkout", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifests = sorted((args.checkout / "registry").rglob("registry-item.json"))
    profiles = [profile(path) for path in manifests]
    args.output.write_text(json.dumps({"schema_version": 1, "count": len(profiles), "items": profiles}, ensure_ascii=False, indent=1))
    print(f"wrote {len(profiles)} code-aware profiles to {args.output}")


if __name__ == "__main__":
    main()
