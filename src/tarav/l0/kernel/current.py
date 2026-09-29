"""Access the selected runtime's trusted Record registry through kernel wiring."""

from __future__ import annotations

from collections.abc import Callable

from .records import TaravObject
from .types import TypeRegistry

_records_provider: Callable[[], TypeRegistry[TaravObject]] | None = None


def configure_current_records(
    provider: Callable[[], TypeRegistry[TaravObject]],
) -> None:
    global _records_provider
    _records_provider = provider


def current_records() -> TypeRegistry[TaravObject]:
    if _records_provider is None:
        raise RuntimeError("Current Record registry has not been configured")
    return _records_provider()
