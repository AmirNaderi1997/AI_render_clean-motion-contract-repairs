"""Subprocess boundary for the pinned HyperFrames CLI."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


HYPERFRAMES_VERSION = "0.8.160"


class HyperFramesError(RuntimeError):
    pass


def render_project(project_dir: Path, output: Path, *, timeout: int = 1800) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "NO_COLOR": "1"}
    check = subprocess.run(
        ["npx", "--yes", f"hyperframes@{HYPERFRAMES_VERSION}", "check", "."],
        cwd=project_dir, env=env, text=True, capture_output=True, timeout=180,
    )
    if check.returncode:
        raise HyperFramesError(f"HyperFrames check failed: {(check.stderr or check.stdout)[-1200:]}")
    result = subprocess.run(
        ["npx", "--yes", f"hyperframes@{HYPERFRAMES_VERSION}", "render", ".",
         "--output", str(output.resolve()), "--quality", "standard", "--workers", "1"],
        cwd=project_dir, env=env, text=True, capture_output=True, timeout=timeout,
    )
    if result.returncode or not output.is_file():
        raise HyperFramesError(f"HyperFrames render failed: {(result.stderr or result.stdout)[-2000:]}")
    return output
