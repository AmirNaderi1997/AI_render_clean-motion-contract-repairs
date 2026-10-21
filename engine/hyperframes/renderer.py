"""Subprocess boundary for the pinned HyperFrames CLI."""
from __future__ import annotations

import os
import json
import hashlib
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional
from .cli import cli_command


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


def check_batches(project_dir: Path) -> list[list[str]]:
    """Keep the CLI's per-session audit deadline bounded on CPU-only servers.

    The CLI always performs up to 600 dense overlap seeks, independently of
    --samples. Check every authored motion window plus opening/ending instead.
    Static lint remains project-wide and runtime/layout/contrast remain enabled.
    Range mode skips the CLI's global frozen-sweep/sidecar assertions; the caller
    must retain its post-render visual QC. Never label this a full-timeline pass.
    """
    try:
        meta = json.loads((project_dir / 'meta.json').read_text())
        beats = meta.get('visual_library') or []
        if not beats:
            return [[]]
        duration = float(meta.get('duration') or max(float(b['end']) for b in beats))
        windows = [(0.0, min(1.0, duration)), (max(0.0, duration-1), duration)]
        windows += [(max(0.0, float(b['start'])-.15), min(duration, float(b['end'])+.15)) for b in beats]
        # Cap each session to four seconds, retaining overlapping boundary frames.
        ranges = []
        for start, end in sorted(windows):
            while end > start:
                stop = min(end, start+4)
                ranges.append(['--range', f'{start:.3f},{stop:.3f}', '--samples', '3'])
                if stop == end:
                    break
                start = stop-.05
        return ranges
    except (OSError, ValueError, KeyError, TypeError):
        return [[]]


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
    batches = check_batches(project_dir)
    receipt = project_dir/'.hyperframes/editor-checkpoint.json'
    key = audit_key(project_dir)
    try:
        cached = json.loads(receipt.read_text()).get('key') == key
    except (OSError, ValueError):
        cached = False
    if cached:
        batches = []
    for batch_index, batch in enumerate(batches):
        for attempt in range(3):
            check = subprocess.run(
                [*cli_command(), "check", ".", *batch],
                cwd=project_dir, env=env, text=True, capture_output=True, timeout=180,
            )
            detail = "\n".join(part for part in (check.stdout, check.stderr) if part)
            if not check.returncode:
                break
            if "Navigation timeout" not in detail or attempt == 2:
                raise HyperFramesError(f"HyperFrames check failed: {detail[-2400:]}")
            time.sleep(1.5 * (attempt + 1))
        if on_progress and check is not None and not check.returncode:
            on_progress(83 + int(3 * (batch_index + 1) / len(batches)))
    if not cached and (check is None or check.returncode):
        raise HyperFramesError(f"HyperFrames check failed: {detail[-2400:]}")
    if not cached:
        receipt.parent.mkdir(parents=True,exist_ok=True)
        receipt.write_text(json.dumps({'key': key, 'scope':'motion windows, opening and ending; post-render QC required'}))
    if on_progress:
        on_progress(86)
    from .sparse import render_sparse
    result = render_sparse(project_dir, output,
        lambda p,o: _render_cli(p,o,timeout=timeout,should_cancel=should_cancel),
        on_progress=on_progress,should_cancel=should_cancel)
    if result is not None:
        if on_progress:
            on_progress(99)
        return result
    return _render_cli(project_dir,output,timeout=timeout,on_progress=on_progress,should_cancel=should_cancel)


def audit_key(project_dir: Path) -> str:
    """Invalidate quality receipts when owned code/media/check windows change."""
    value = hashlib.sha256(json.dumps([HYPERFRAMES_VERSION,check_batches(project_dir)]).encode())
    files = [project_dir/name for name in ('index.html','meta.json','hyperframes.json')]
    files += list(project_dir.glob('*.motion.json'))
    for folder in ('assets','compositions'):
        if (project_dir/folder).is_dir():
            files += [p for p in (project_dir/folder).rglob('*') if p.is_file()]
    for path in sorted(files):
        if not path.is_file():
            continue
        info=path.stat()
        value.update(str(path.relative_to(project_dir)).encode())
        if path.suffix in {'.html','.js','.css','.json'}:
            value.update(path.read_bytes())
        else:
            value.update(repr((info.st_size,info.st_mtime_ns)).encode())
    return value.hexdigest()


def _render_cli(project_dir: Path, output: Path, *, timeout=1800, on_progress=None, should_cancel=None) -> Path:
    env = {**os.environ, 'NO_COLOR':'1'}
    command = (
        [*cli_command(), "render", ".",
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
            # No elapsed-time percentage: the CLI does not expose frame progress
            # here. Keep the last real milestone until encoding completes.
    if process.returncode or not output.is_file():
        detail = (stderr or stdout or "unknown render failure")[-2400:]
        if "HDR pre-extraction" in detail:
            detail = "HyperFrames HDR detection exhausted temporary disk space; SDR fallback failed. " + detail
        raise HyperFramesError(f"HyperFrames render failed: {summarize_failure(detail)}")
    if on_progress:
        on_progress(99)
    return output
