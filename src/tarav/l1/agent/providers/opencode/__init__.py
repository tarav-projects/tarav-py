# $kw: ^agentos-provider-opencode-package --from Agent.Navigable.Codebase --note [DF] provider-specific behavior lives beneath the agent provider namespace --supp ^c20260811-62u
from __future__ import annotations


def __getattr__(name: str):
    if name == "OpencodeAgent":
        from .agent import OpencodeAgent

        return OpencodeAgent
    if name == "OpencodeSession":
        from .session import OpencodeSession

        return OpencodeSession
    if name == "discover_opencode_sessions":
        from .session import discover_opencode_sessions

        return discover_opencode_sessions
    if name == "find_opencode_sessions":
        from .session import find_opencode_sessions

        return find_opencode_sessions
    raise AttributeError(name)

__all__ = [
    "OpencodeAgent",
    "OpencodeSession",
    "discover_opencode_sessions",
    "find_opencode_sessions",
]
