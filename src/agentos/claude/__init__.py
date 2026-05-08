from __future__ import annotations


def __getattr__(name: str):
    if name == "ClaudeAgent":
        from .agent import ClaudeAgent

        return ClaudeAgent
    if name == "ClaudeSession":
        from .session import ClaudeSession

        return ClaudeSession
    raise AttributeError(name)

__all__ = [
    "ClaudeAgent",
    "ClaudeSession",
]
