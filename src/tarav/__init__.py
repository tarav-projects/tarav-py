"""Public Tarav library entry points."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar, overload

from tarav.archive.records import ARCHIVE
from tarav.kernel.records import configure_workflow_resolver

if TYPE_CHECKING:
    from tarav.kernel import TaravObject
    from tarav.loading import LoadingProfile
    from tarav.runtime import TaravRuntime


ObjectT = TypeVar("ObjectT", bound="TaravObject")

__all__ = [
    "ARCHIVE",
    "__version__",
    "get_runtime",
    "load_object",
    "set_runtime",
]


__version__ = "0.1.0"

# Resolve lazily against the selected runtime, never during kernel bootstrap.
configure_workflow_resolver(lambda ship: get_runtime().workflows.get(ship)())

# Tarav libraries emit diagnostics but leave handler configuration to the host.
logging.getLogger(__name__).addHandler(logging.NullHandler())


@overload
def load_object(
    path: str | Path, *, profile: type[LoadingProfile] | None = None,
    expected_type: type[ObjectT],
) -> ObjectT: ...


@overload
def load_object(
    path: str | Path, *, profile: type[LoadingProfile] | None = None,
    expected_type: None = None,
) -> TaravObject: ...


def load_object(
    path: str | Path,
    *,
    profile: type[LoadingProfile] | None = None,
    expected_type: type[TaravObject] | None = None,
) -> TaravObject:
    """Load one object through Tarav's default composed runtime."""

    from tarav.runtime import get_runtime

    return get_runtime().load_object(
        path, profile=profile, expected_type=expected_type
    )


def get_runtime() -> TaravRuntime:
    """Return the current process-wide Tarav runtime."""

    from tarav.runtime import get_runtime as current

    return current()


def set_runtime(runtime: TaravRuntime | None) -> None:
    """Select a composed runtime for process-wide Tarav operations."""

    from tarav.runtime import set_runtime as select

    select(runtime)
