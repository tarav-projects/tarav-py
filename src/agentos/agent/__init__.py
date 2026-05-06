from __future__ import annotations


def register_agent_commands(*args, **kwargs):
    from .commands import register_agent_commands as _register_agent_commands

    return _register_agent_commands(*args, **kwargs)

__all__ = ["register_agent_commands"]
