# $kw: ^agentos-provider-pi-package --from Agent.Navigable.Codebase --note [DF] provider-specific behavior lives beneath the agent provider namespace --supp ^c20260811-62u
from __future__ import annotations


def __getattr__(name: str):
    if name == "PiAgent":
        from .agent import PiAgent

        return PiAgent
    if name == "PiSession":
        from .session import PiSession

        return PiSession
    if name == "discover_pi_sessions":
        from .session import discover_pi_sessions

        return discover_pi_sessions
    if name == "find_pi_sessions":
        from .session import find_pi_sessions

        return find_pi_sessions
    raise AttributeError(name)

__all__ = [
    "PiAgent",
    "PiSession",
    "discover_pi_sessions",
    "find_pi_sessions",
]
