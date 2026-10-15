"""Install and customize the small set of registry blocks wired by AI Render."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


VERSION = "0.8.161"


def _install(project_dir: Path, name: str) -> bool:
    result = subprocess.run(
        ["npx", "--yes", f"hyperframes@{VERSION}", "add", name, "--dir", ".", "--no-clipboard"],
        cwd=project_dir, text=True, capture_output=True, timeout=180,
    )
    return result.returncode == 0


def _pipeline(project_dir: Path, labels: list[str], duration: float) -> bool:
    if not _install(project_dir, "hw-pipeline"):
        return False
    path = project_dir / "compositions" / "hw-pipeline.html"
    if not path.is_file():
        return False
    source = path.read_text()
    nodes = ", ".join(f"{{ label: {json.dumps(value, ensure_ascii=False)} }}" for value in labels[:4])
    source, count = re.subn(r"nodes:\s*\[[^\]]+\]", f"nodes: [{nodes}]", source, count=1, flags=re.S)
    if not count:
        return False
    source = source.replace('font-family: "Caveat", cursive;', 'font-family: "Ray", sans-serif;')
    source = source.replace("</style>", "@font-face{font-family:Ray;src:url('../assets/ray-extrabold.ttf')}\n</style>", 1)
    source = re.sub(r'data-duration="7"', f'data-duration="{duration:.3f}"', source)
    source = re.sub(r"var DUR = 7;", f"var DUR = {duration:.3f};", source)
    path.write_text(source)
    return True


def _component(project_dir: Path, name: str, duration: float, labels: list[str]) -> bool:
    if not _install(project_dir, name):
        return False
    path = project_dir / "compositions" / "components" / f"{name}.html"
    if not path.is_file():
        return False
    source = path.read_text()
    source = re.sub(r'data-composition-duration="[0-9.]+"', f'data-composition-duration="{duration:.3f}"', source)
    source = re.sub(r'data-duration="[0-9.]+"', f'data-duration="{duration:.3f}"', source)
    if name == "comparison-split":
        pair = (labels + ["خدمت", "محصول"])[:2]
        source = source.replace('"default": "Before"', f'"default": {json.dumps(pair[0], ensure_ascii=False)}')
        source = source.replace('"default": "After"', f'"default": {json.dumps(pair[1], ensure_ascii=False)}')
        source = source.replace('font-family: var(--font-body, Inter, system-ui, sans-serif);',
                                'font-family: Ray, sans-serif; direction: rtl;')
        source = source.replace("<style>", "<style>@font-face{font-family:Ray;src:url('../../assets/ray-extrabold.ttf')}\n", 1)
    elif name == "caption-kinetic-slam":
        words = [word for word in " ".join(labels).split() if word][:6]
        step = max(.25, duration / max(1, len(words)))
        entries = []
        for index, word in enumerate(words):
            start = index * step
            entries.append({"text": word, "start": round(start, 3), "end": round(min(duration - .08, start + step * .82), 3)})
        source = re.sub(r"var WORDS = \[[\s\S]*?\n\s*\];", "var WORDS = " + json.dumps(entries, ensure_ascii=False) + ";", source, count=1)
        source = re.sub(r"var KEYWORDS = new Set\([^;]+;", f"var KEYWORDS = new Set([{max(0, len(words)-1)}]);", source, count=1)
        source = source.replace('font-family: "Anton", sans-serif;', 'font-family: "Ray", sans-serif; direction: rtl;')
        source = source.replace("width: 1920px;", "width: 1080px;").replace("height: 1080px;", "height: 1920px;")
        source = source.replace('content="width=1920, height=1080"', 'content="width=1080, height=1920"')
        source = source.replace('data-width="1920"', 'data-width="1080"').replace('data-height="1080"', 'data-height="1920"')
        source = source.replace("1720) + \"px\"", "920) + \"px\"")
        source = source.replace("<style>", "<style>@font-face{font-family:Ray;src:url('../../assets/ray-extrabold.ttf')}\n", 1)
    path.write_text(source)
    return True


def wire_registry(project_dir: Path, beats: list) -> set[str]:
    """Install only adapters that AI Render knows how to customize safely."""
    wired: set[str] = set()
    kinetic = next((beat for beat in beats if beat.visual_type == "kinetic_type"), None)
    if kinetic and _component(project_dir, "caption-kinetic-slam", kinetic.end - kinetic.start, [kinetic.title]):
        kinetic.registry_refs = ["caption-kinetic-slam"]
        wired.add(kinetic.id)
    # comparison-split's generic dashboard imagery is often semantically
    # wrong for editorial concepts. Keep our literal two-subject comparison;
    # registry code is used only where its visual meaning matches the speech.
    collage = next((beat for beat in beats if beat.visual_type == "media_collage"), None)
    if collage and _component(project_dir, "paper-collage-reveal", collage.end - collage.start, collage.items):
        collage.registry_refs = ["paper-collage-reveal"]
        wired.add(collage.id)
    pipeline = next((beat for beat in reversed(beats) if beat.visual_type in {"steps", "before_after"}), None)
    if pipeline:
        labels = pipeline.items or ["خدمت", "نرم‌افزار", "فروش خودکار"]
        if len(labels) == 2:
            labels = [labels[0], "نرم‌افزار", labels[1]]
        if _pipeline(project_dir, labels, pipeline.end - pipeline.start):
            pipeline.registry_refs = ["hw-pipeline"]
            wired.add(pipeline.id)
    return wired
