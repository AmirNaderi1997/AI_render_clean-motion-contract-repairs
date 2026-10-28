"""Shared creative resource discovery; never executes imported catalog code."""

from .registry import get_resource, search_resources

__all__ = ["get_resource", "search_resources"]
