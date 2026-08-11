# $kw: --from Account.Management --from Provider.Instance
"""Resolve a credential `class` to its `AuthMethod` instance.

The new-shape ``accounts.json`` records each method's ``class`` (the credential
class identifier, == ``AuthMethod.name``). This registry maps ``(provider, class)``
to the implementing `AuthMethod`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentos.agent.account_status import AccountIdentity
from agentos.agent.auth_method import AuthData, AuthMethod
from agentos.agent.providers.claude_code.auth_method import ClaudeAuthMethod
from agentos.agent.providers.codex.auth_method import CodexAuthMethod

_METHODS: dict[tuple[str, str], AuthMethod] = {
    (m.provider, m.name): m for m in (CodexAuthMethod(), ClaudeAuthMethod())
}


def auth_method_for_class(provider: str, auth_class: str) -> AuthMethod | None:
    return _METHODS.get((provider, auth_class))


def auth_methods_for_provider(provider: str) -> list[AuthMethod]:
    return [method for (prov, _cls), method in _METHODS.items() if prov == provider]


def providers_with_auth_methods() -> tuple[str, ...]:
    """Providers that have a registered `AuthMethod` — the set a global capture
    sweeps. Derived from `_METHODS`, so a new method auto-joins."""

    return tuple(dict.fromkeys(prov for prov, _cls in _METHODS))


@dataclass(frozen=True)
class HomeAuth:
    """A home's readable credential: the `AuthMethod` that read it, the `AuthData`,
    and its extracted `Account.Identity` (None when unrecognizable)."""

    method: AuthMethod
    auth: AuthData
    identity: AccountIdentity | None


def read_home_auth(provider: str, home: Path) -> HomeAuth | None:
    """The first provider `AuthMethod` whose `read_auth_data(home)` is non-None.

    The single home-reading seam shared by capture, materialize, and status — each
    applies its own account policy to the result. Preserves `auth_methods_for_provider`
    order ("first method that reads wins"); applies no account policy itself."""

    for auth_method in auth_methods_for_provider(provider):
        auth = auth_method.read_auth_data(home)
        if auth is None:
            continue
        return HomeAuth(method=auth_method, auth=auth, identity=auth_method.extract_identity(auth))
    return None


__all__ = [
    "HomeAuth",
    "auth_method_for_class",
    "auth_methods_for_provider",
    "providers_with_auth_methods",
    "read_home_auth",
]
