"""Runtime-backed Context navigation."""

from __future__ import annotations

from tarav.l1.context import ContextEntry, ContextExplorer, ContextSubject


def context(subject: ContextSubject | ContextEntry) -> ContextExplorer:
    """Explore a subject with the current runtime's retained Context entries."""
    from tarav.runtime import get_runtime

    return get_runtime().context(subject)


__all__ = ["context"]
