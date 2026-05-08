from __future__ import annotations


def __getattr__(name: str):
    if name == "OpenclawAgent":
        from .agent import OpenclawAgent

        return OpenclawAgent
    if name == "OpenclawSession":
        from .session import OpenclawSession

        return OpenclawSession
    if name == "discover_openclaw_sessions":
        from .session import discover_openclaw_sessions

        return discover_openclaw_sessions
    if name == "find_openclaw_sessions":
        from .session import find_openclaw_sessions

        return find_openclaw_sessions
    raise AttributeError(name)

__all__ = [
    "OpenclawAgent",
    "OpenclawSession",
    "discover_openclaw_sessions",
    "find_openclaw_sessions",
]
