"""Runtime-backed Context navigation."""

from __future__ import annotations

from tarav.l1.context import ContextEntry, ContextSubject


def context(subject: ContextSubject | ContextEntry, *, views=()):
    """Explore a subject with the current runtime's retained Context entries."""
    from tarav.l3.runtime import get_runtime

    return get_runtime().context(subject, views=views)


__all__ = ["context"]
