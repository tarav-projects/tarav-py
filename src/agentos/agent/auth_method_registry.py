"""Resolve a credential `class` to its `AuthMethod` instance.

The new-shape ``accounts.json`` records each method's ``class`` (the credential
class identifier, == ``AuthMethod.name``). This registry maps ``(provider, class)``
to the implementing `AuthMethod`.
"""

from __future__ import annotations

from agentos.agent.auth_method import AuthMethod
from agentos.claude.auth_method import ClaudeAuthMethod
from agentos.codex.auth_method import CodexAuthMethod

_METHODS: dict[tuple[str, str], AuthMethod] = {
    (m.provider, m.name): m for m in (CodexAuthMethod(), ClaudeAuthMethod())
}


def auth_method_for_class(provider: str, auth_class: str) -> AuthMethod | None:
    return _METHODS.get((provider, auth_class))


def auth_methods_for_provider(provider: str) -> list[AuthMethod]:
    return [method for (prov, _cls), method in _METHODS.items() if prov == provider]


__all__ = ["auth_method_for_class", "auth_methods_for_provider"]
