"""Public Tarav library entry points."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar, overload

from tarav.record_archive import ARCHIVE

if TYPE_CHECKING:
    from tarav.kernel import TaravObject
    from tarav.kernel.context import ContextEntry, ContextExplorer, ContextSubject
    from tarav.runtime import TaravRuntime


ObjectT = TypeVar("ObjectT", bound="TaravObject")

__all__ = [
    "ARCHIVE",
    "__version__",
    "context",
    "get_runtime",
    "load_object",
    "set_runtime",
]


__version__ = "0.1.0"

# Tarav libraries emit diagnostics but leave handler configuration to the host.
logging.getLogger(__name__).addHandler(logging.NullHandler())


@overload
def load_object(path: str | Path, *, expected_type: type[ObjectT]) -> ObjectT: ...


@overload
def load_object(path: str | Path, *, expected_type: None = None) -> TaravObject: ...


def load_object(
    path: str | Path,
    *,
    expected_type: type[TaravObject] | None = None,
) -> TaravObject:
    """Load one object through Tarav's default composed runtime."""

    from tarav.runtime import get_runtime

    return get_runtime().load_object(path, expected_type=expected_type)


def context(subject: ContextSubject | ContextEntry) -> ContextExplorer:
    """Open one subject's runtime and retained Context through the default runtime."""

    from tarav.runtime import get_runtime

    return get_runtime().context(subject)


def get_runtime() -> TaravRuntime:
    """Return the current process-wide Tarav runtime."""

    from tarav.runtime import get_runtime as current

    return current()


def set_runtime(runtime: TaravRuntime | None) -> None:
    """Select a composed runtime for process-wide Tarav operations."""

    from tarav.runtime import set_runtime as select

    select(runtime)
