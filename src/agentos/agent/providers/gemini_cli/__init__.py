# $kw: ^agentos-provider-gemini-cli-package --from Agent.Navigable.Codebase --note [DF] provider-specific behavior lives beneath the agent provider namespace --supp ^c20260811-62u
from __future__ import annotations


def __getattr__(name: str):
    if name == "GeminiAgent":
        from .agent import GeminiAgent

        return GeminiAgent
    if name == "GeminiSession":
        from .session import GeminiSession

        return GeminiSession
    if name == "discover_gemini_sessions":
        from .session import discover_gemini_sessions

        return discover_gemini_sessions
    if name == "find_gemini_sessions":
        from .session import find_gemini_sessions

        return find_gemini_sessions
    raise AttributeError(name)

__all__ = [
    "GeminiAgent",
    "GeminiSession",
    "discover_gemini_sessions",
    "find_gemini_sessions",
]
