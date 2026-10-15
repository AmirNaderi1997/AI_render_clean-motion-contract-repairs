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


def wire_registry(project_dir: Path, beats: list) -> set[str]:
    """Install only adapters that AI Render knows how to customize safely."""
    wired: set[str] = set()
    pipeline = next((beat for beat in reversed(beats) if beat.visual_type in {"steps", "before_after"}), None)
    if pipeline:
        labels = pipeline.items or ["خدمت", "نرم‌افزار", "فروش خودکار"]
        if len(labels) == 2:
            labels = [labels[0], "نرم‌افزار", labels[1]]
        if _pipeline(project_dir, labels, pipeline.end - pipeline.start):
            pipeline.registry_refs = ["hw-pipeline"]
            wired.add(pipeline.id)
    return wired
