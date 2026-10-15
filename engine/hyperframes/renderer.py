"""Subprocess boundary for the pinned HyperFrames CLI."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional


HYPERFRAMES_VERSION = "0.8.161"


class HyperFramesError(RuntimeError):
    pass


def render_project(
    project_dir: Path,
    output: Path,
    *,
    timeout: int = 1800,
    on_progress: Optional[Callable[[int], None]] = None,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "NO_COLOR": "1"}
    if on_progress:
        on_progress(83)
    check = subprocess.run(
        ["npx", "--yes", f"hyperframes@{HYPERFRAMES_VERSION}", "check", "."],
        cwd=project_dir, env=env, text=True, capture_output=True, timeout=180,
    )
    if check.returncode:
        raise HyperFramesError(f"HyperFrames check failed: {(check.stderr or check.stdout)[-1200:]}")
    if on_progress:
        on_progress(86)
    command = (
        ["npx", "--yes", f"hyperframes@{HYPERFRAMES_VERSION}", "render", ".",
         "--output", str(output.resolve()), "--quality", "standard", "--workers", "1", "--sdr"]
    )
    process = subprocess.Popen(
        command, cwd=project_dir, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
    )
    started = time.monotonic()
    while True:
        try:
            stdout, stderr = process.communicate(timeout=10)
            break
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - started
            if elapsed >= timeout:
                os.killpg(process.pid, signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=15)
                raise HyperFramesError(f"HyperFrames render timed out after {timeout} seconds")
            if on_progress:
                on_progress(min(98, 87 + int(elapsed / 20)))
    if process.returncode or not output.is_file():
        detail = (stderr or stdout or "unknown render failure")[-2400:]
        if "HDR pre-extraction" in detail:
            detail = "HyperFrames HDR detection exhausted temporary disk space; SDR fallback failed. " + detail
        raise HyperFramesError(f"HyperFrames render failed: {detail}")
    if on_progress:
        on_progress(99)
    return output
