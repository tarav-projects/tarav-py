from __future__ import annotations


def __getattr__(name: str):
    if name == "CopilotAgent":
        from .agent import CopilotAgent

        return CopilotAgent
    if name == "CopilotSession":
        from .session import CopilotSession

        return CopilotSession
    raise AttributeError(name)

__all__ = [
    "CopilotAgent",
    "CopilotSession",
]
