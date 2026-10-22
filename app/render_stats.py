"""Measured render times, used for the time estimate shown in a Creative Plan.

Estimates come only from renders this installation actually finished. With no measurement for a
style the plan says the time is unknown instead of inventing a number.
"""
from __future__ import annotations

import json
import statistics
import threading
import time
from pathlib import Path

from app import jobs as jobstore

KEEP = 30
_lock = threading.Lock()


def _path() -> Path:
    return Path(jobstore.JOBS_ROOT) / "studio" / "render_stats.json"


def _read() -> dict:
    try:
        return json.loads(_path().read_text())
    except (OSError, ValueError):
        return {}


def record(kind: str, source_seconds: float, wall_seconds: float) -> None:
    if source_seconds <= 0 or wall_seconds <= 0:
        return
    with _lock:
        data = _read()
        rows = data.setdefault(kind, [])
        rows.append({"source_s": round(source_seconds, 2), "wall_s": round(wall_seconds, 1), "at": time.time()})
        data[kind] = rows[-KEEP:]
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(path)


def estimate(kind: str, source_seconds: float) -> dict | None:
    """Range in seconds from the measured wall-time/source-time ratios, or None without data."""
    rows = _read().get(kind) or []
    ratios = sorted(row["wall_s"] / row["source_s"] for row in rows if row.get("source_s"))
    if not ratios or source_seconds <= 0:
        return None
    low, high = ratios[0], ratios[-1]
    if len(ratios) >= 4:
        quartiles = statistics.quantiles(ratios, n=4)
        low, high = quartiles[0], quartiles[2]
    return {"low_s": round(low * source_seconds), "high_s": round(high * source_seconds),
            "samples": len(ratios)}
