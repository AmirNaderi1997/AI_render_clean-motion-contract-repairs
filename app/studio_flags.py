"""State that several processes must agree on, kept in small files next to the conversation.

On the server the API process (which receives the Stop button) and the Celery worker (which does the work) are different processes and different
containers that share one data volume. A flag in memory is invisible across that boundary, so everything the Stop button and the "working" indicator
depend on lives here, in files:

  <studio>/<user>/<conversation>/.stop        the stop generation (an integer); work started under an older number stops at its next checkpoint
  <studio>/<user>/<conversation>/.busy/<id>   one file per running unit of work, touched every few seconds; a file nobody touches for a while is dead
"""
from __future__ import annotations

import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from app import studio_store

HEARTBEAT_S = 4.0
STALE_S = 20.0


def _safe(user_key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(user_key))


def conversation_dir(user_key: str, conversation_id: str) -> Path:
    return studio_store.ROOT / _safe(user_key) / re.sub(r"[^A-Za-z0-9_-]", "_", str(conversation_id))


def generation(user_key: str, conversation_id: str) -> int:
    try:
        return int((conversation_dir(user_key, conversation_id) / ".stop").read_text().strip() or 0)
    except (OSError, ValueError):
        return 0


def bump_generation(user_key: str, conversation_id: str) -> int:
    """Stop pressed: everything started under the previous generation is now out of date, in every process."""
    directory = conversation_dir(user_key, conversation_id)
    directory.mkdir(parents=True, exist_ok=True)
    value = generation(user_key, conversation_id) + 1
    temporary = directory / f".stop.{uuid.uuid4().hex[:6]}"
    temporary.write_text(str(value))
    os.replace(temporary, directory / ".stop")
    return value


@contextmanager
def working(user_key: str, conversation_id: str):
    """Mark one unit of work as running for as long as the block runs (and a while after a crash: the heartbeat simply stops)."""
    directory = conversation_dir(user_key, conversation_id) / ".busy"
    directory.mkdir(parents=True, exist_ok=True)
    token = directory / uuid.uuid4().hex
    token.write_text(f"{os.getpid()} {time.time()}")
    done = threading.Event()

    def beat() -> None:
        while not done.wait(HEARTBEAT_S):
            try:
                token.touch()
            except OSError:
                return

    threading.Thread(target=beat, daemon=True, name="studio-busy-heartbeat").start()
    try:
        yield token
    finally:
        done.set()
        try:
            token.unlink()
        except OSError:
            pass


def busy(user_key: str, conversation_id: str) -> bool:
    """Is any unit of work running for this conversation, in any process?"""
    base = conversation_dir(user_key, conversation_id)
    directory = base / ".busy"
    now = time.time()
    try:
        entries = list(directory.iterdir())
        stopped_at = (base / ".stop").stat().st_mtime if (base / ".stop").exists() else 0.0
    except OSError:
        return False
    alive = False
    for entry in entries:
        try:
            age = now - entry.stat().st_mtime
            if age > 600:
                entry.unlink()                       # tidy up what a crash left behind
                continue
            started = float((entry.read_text().split() + ["0", "0"])[1])
            # work that started before the last Stop is finishing in the background (a model call cannot be interrupted): it is not "working" any more
            if age <= STALE_S and started > stopped_at:
                alive = True
        except (OSError, ValueError):
            continue
    return alive
