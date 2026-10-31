"""Cancellation checkpoints shared by Studio stages, engines and AI transports."""
from contextvars import ContextVar

generation = ContextVar("studio_generation", default=None)
engine_guard = ContextVar("studio_engine_guard", default=None)


class Stopped(InterruptedError):
    """The user cancelled this execution; never retry or turn it into a fallback."""


def checkpoint(conversation_id=None):
    from app import studio_flags
    mine = generation.get()
    if mine and (conversation_id is None or mine[0] == conversation_id):
        if studio_flags.generation(mine[1], mine[0]) != mine[2]:
            raise Stopped("Stopped by user")
    guard = engine_guard.get()
    if guard:
        guard()
