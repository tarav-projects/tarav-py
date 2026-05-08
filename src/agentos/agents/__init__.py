from __future__ import annotations


def __getattr__(name: str):
    if name == "AgentsAgent":
        from .agent import AgentsAgent

        return AgentsAgent
    raise AttributeError(name)


__all__ = ["AgentsAgent"]
