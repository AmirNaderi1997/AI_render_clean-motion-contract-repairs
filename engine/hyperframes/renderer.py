"""Subprocess boundary for the pinned HyperFrames CLI."""
from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional


HYPERFRAMES_VERSION = "0.8.161"


class HyperFramesError(RuntimeError):
    pass


_KEY_LINE = ("Render blocked", "correctness warning", "sub_timeline_script_failure", "Error:", "TypeError", "ReferenceError",
             "Failed to load", "net::ERR", "Navigation timeout", "ENOSPC", "FFmpeg")


def summarize_failure(detail: str, limit: int = 420) -> str:
    """Put the cause first. The raw tail of the CLI log is mostly JSON; the reason is a single line in it."""
    seen: list[str] = []
    for raw in detail.splitlines():
        trace = re.search(r'"message":"(.*?)(?:"\}\s*)?$', raw.strip())  # CLI trace lines are JSON; use their message
        text = trace.group(1) if trace else raw
        for part in text.replace("\\n", "\n").splitlines():
            line = part.strip(" -\t")
            if line and any(key in line for key in _KEY_LINE) and line not in seen:
                seen.append(line)
    summary = " | ".join(seen)[:limit]
    return summary or detail.strip()[-limit:]


def render_project(
    project_dir: Path,
    output: Path,
    *,
    timeout: int = 1800,
    on_progress: Optional[Callable[[int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "NO_COLOR": "1"}
    if on_progress:
        on_progress(83)
    check = None
    detail = ""
    for attempt in range(3):
        check = subprocess.run(
            ["npx", "--yes", f"hyperframes@{HYPERFRAMES_VERSION}", "check", "."],
            cwd=project_dir, env=env, text=True, capture_output=True, timeout=180,
        )
        detail = "\n".join(part for part in (check.stdout, check.stderr) if part)
        if not check.returncode:
            break
        # Browser startup occasionally misses the CLI's 10s navigation
        # window even though the identical project passes immediately after.
        # Retry only that transient; structural/runtime errors still fail fast.
        if "Navigation timeout" not in detail or attempt == 2:
            raise HyperFramesError(f"HyperFrames check failed: {detail[-2400:]}")
        time.sleep(1.5 * (attempt + 1))
    if check is None or check.returncode:
        raise HyperFramesError(f"HyperFrames check failed: {detail[-2400:]}")
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
        if should_cancel and should_cancel():
            os.killpg(process.pid, signal.SIGTERM)
            process.communicate(timeout=15)
            raise HyperFramesError("HyperFrames render canceled")
        try:
            stdout, stderr = process.communicate(timeout=10)
            break
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - started
            if should_cancel and should_cancel():
                os.killpg(process.pid, signal.SIGTERM)
                process.communicate(timeout=15)
                raise HyperFramesError("HyperFrames render canceled")
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
        raise HyperFramesError(f"HyperFrames render failed: {summarize_failure(detail)}")
    if on_progress:
        on_progress(99)
    return output
