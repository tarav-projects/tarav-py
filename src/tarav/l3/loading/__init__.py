"""Load a Record through the current installed runtime."""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar, overload

from tarav.l0.kernel import TaravObject
from tarav.l1.loading import LoadingProfile
from tarav.l3.runtime import get_runtime

ObjectT = TypeVar("ObjectT", bound=TaravObject)


@overload
def load(
    path: str | Path, *, profile: type[LoadingProfile] | None = None,
    expected_type: type[ObjectT],
) -> ObjectT: ...


@overload
def load(
    path: str | Path, *, profile: type[LoadingProfile] | None = None,
    expected_type: None = None,
) -> TaravObject: ...


def load(
    path: str | Path, *, profile: type[LoadingProfile] | None = None,
    expected_type: type[TaravObject] | None = None,
) -> TaravObject:
    """Load one Record through the current runtime's trusted Type registry."""
    return get_runtime().load_object(path, profile=profile, expected_type=expected_type)


__all__ = ["load"]
