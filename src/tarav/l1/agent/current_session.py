"""Which session the running agent is in, as its provider's harness reports it."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar


# tarav.breadcrumb 2984c95d83d09439bda9ea84044a7b80eaad842f4d13068684a46eb05ed2fde6
class ReportsCurrentSession:
    """Capability: the harness tells the processes it starts which session they run in.

    A provider adapter inherits this and names the environment variable its
    harness sets. An adapter that does not inherit it cannot answer.
    """

    current_session_variable: ClassVar[str]

    @classmethod
    def current_session_id(cls, environ: Mapping[str, str] | None = None) -> str | None:
        source = os.environ if environ is None else environ
        return source.get(cls.current_session_variable, "").strip() or None


@dataclass(frozen=True)
class CurrentSession:
    provider: str
    session_id: str


class CurrentSessionError(LookupError):
    """The running session could not be named."""


class CurrentSessionUnsupported(CurrentSessionError):
    """The named provider does not report its current session."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"provider does not report its current session: {provider}")


class CurrentSessionAbsent(CurrentSessionError):
    """A reporting provider was asked, or all were, and none names a session."""

    def __init__(self, provider: str | None = None, variable: str | None = None) -> None:
        self.provider = provider
        self.variable = variable
        super().__init__(
            f"no {variable} for provider {provider}" if provider is not None
            else "no provider reports a current session"
        )


class CurrentSessionAmbiguous(CurrentSessionError):
    """Several providers report a session and none was named."""

    def __init__(self, providers: tuple[str, ...]) -> None:
        self.providers = providers
        super().__init__(f"several providers report a current session: {', '.join(providers)}")


def session_reporters() -> dict[str, type[ReportsCurrentSession]]:
    """Provider family to adapter, for the adapters that report their session."""
    from tarav.l1.agent.providers.registry import PROVIDER_ADAPTERS

    return {provider: adapter for provider, adapter in PROVIDER_ADAPTERS.items()
            if issubclass(adapter, ReportsCurrentSession)}


def current_session(
    provider: str | None = None, *, environ: Mapping[str, str] | None = None,
) -> CurrentSession:
    """The session of the running agent. It never guesses between providers."""
    reporters = session_reporters()
    if provider is not None:
        adapter = reporters.get(provider)
        if adapter is None:
            raise CurrentSessionUnsupported(provider)
        session_id = adapter.current_session_id(environ)
        if session_id is None:
            raise CurrentSessionAbsent(provider, adapter.current_session_variable)
        return CurrentSession(provider, session_id)
    found = [CurrentSession(name, session_id) for name, adapter in reporters.items()
             if (session_id := adapter.current_session_id(environ)) is not None]
    if not found:
        raise CurrentSessionAbsent()
    if len(found) != 1:
        raise CurrentSessionAmbiguous(tuple(session.provider for session in found))
    return found[0]


__all__ = [
    "CurrentSession",
    "CurrentSessionAbsent",
    "CurrentSessionAmbiguous",
    "CurrentSessionError",
    "CurrentSessionUnsupported",
    "ReportsCurrentSession",
    "current_session",
    "session_reporters",
]
