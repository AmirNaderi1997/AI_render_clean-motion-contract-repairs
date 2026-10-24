"""The studio's voice in the chat: one short, streamed message about what a step just did or found.

The words are written by the model from the REAL facts of the step (the title of the page it read, the number of shots in the reference, the colours it
measured, the idea it chose), so a message is never a canned sentence. If the model is unavailable the caller's plain factual ``fallback`` is posted
instead: something true always appears. Messages are queued per conversation and run in the background, so the pipeline never waits for its own narration
and two messages never interleave.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

log = logging.getLogger(__name__)
_lock = threading.Lock()
_queues: dict[str, ThreadPoolExecutor] = {}
MAX_CHARS = 520

SYSTEM = (
    "You are the voice of a video and motion-graphics studio, talking to the person who asked for the work. Write ONE short chat message "
    "(1 to 3 sentences, at most about 60 words) about what the studio has just done or found, in the language of the request (Persian by default), "
    "first person, natural, in your own words. Use ONLY the facts given: name concrete things (a page title, a number, a colour, a short quoted phrase). "
    "Never invent details, never claim anything the facts do not say, never promise results, never describe internal steps or tools. "
    "If a fact says something could not be determined or read, say so plainly in one clause. No headings, no bullet lists, no emojis, no greeting."
)


def _executor(conversation_id: str) -> ThreadPoolExecutor:
    with _lock:
        if conversation_id not in _queues:
            _queues[conversation_id] = ThreadPoolExecutor(max_workers=1, thread_name_prefix="narrator")
        return _queues[conversation_id]


def _trim(text: str) -> str:
    """A narration is short: cut a rambling answer at a sentence end instead of showing a wall of text."""
    text = text.strip()
    if len(text) <= MAX_CHARS:
        return text
    cut = text[:MAX_CHARS]
    end = max(cut.rfind("."), cut.rfind("؟"), cut.rfind("!"), cut.rfind("؛"), cut.rfind("\n"))
    return (cut[:end + 1] if end > MAX_CHARS * 0.4 else cut.rsplit(" ", 1)[0] + "…").strip()


def _post(conversation_id: str, user_key: str, text: str, attachments: list[str] | None) -> None:
    from app.studio_orchestrator import _assistant
    _assistant(conversation_id, user_key, text, attachments or None)


def _stream(conversation_id: str, user_key: str, kind: str, facts: dict, attachments: list[str] | None, fallback: str) -> None:
    from app.studio_orchestrator import _emit, repo, run
    from brain.lm_gateway import configured, stream_chat
    text = ""
    if configured():
        response_id = f"narration:{uuid.uuid4().hex[:12]}"
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps({"stage": kind, "facts": facts}, ensure_ascii=False)[:6000]}]
        _emit(conversation_id, "assistant.response.started", response_id=response_id, narration=kind)
        flushed, tick = "", 0.0
        try:
            for chunk in stream_chat("conversation_response", messages, tokens=300, timeout_seconds=30):
                text += chunk
                if len(text) > MAX_CHARS * 1.6:
                    break                                        # enough: the message is cut at a sentence end below
                if not flushed or time.monotonic() - tick > 0.12:
                    _emit(conversation_id, "assistant.response.delta", response_id=response_id, text=text)
                    flushed, tick = text, time.monotonic()
            text = _trim(text)
            if not text:
                raise ValueError("empty narration")
            saved = run(repo.add_message(conversation_id, user_key, "assistant", text, attachments or None))
            _emit(conversation_id, "assistant.response.completed", response_id=response_id, text=text, message_id=saved["id"], attachments=list(attachments or []))
            return
        except Exception as exc:
            log.warning("narration %s fell back to its plain text: %s", kind, type(exc).__name__)
            _emit(conversation_id, "assistant.response.failed", response_id=response_id, text="", message_id=None, error="")
    if fallback.strip():
        _post(conversation_id, user_key, fallback.strip(), attachments)


def narrate(conversation_id: str, user_key: str, kind: str, facts: dict[str, Any], *, attachments: list[str] | None = None,
            fallback: str = "", background: bool = True):
    """Say what ``kind`` of step just happened, from ``facts``. Returns the future (``.result()`` to wait for the message to be posted)."""
    job = _executor(conversation_id).submit(_stream, conversation_id, user_key, kind, facts, attachments, fallback)
    if not background:
        job.result()
    return job
