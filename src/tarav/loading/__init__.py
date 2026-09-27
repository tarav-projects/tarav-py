"""Caller-selected Record entry discovery over Tarav's trusted loader."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TypeVar, overload

from tarav.kernel import TaravObject

from .workflow import LoadingWorkflow

ObjectT = TypeVar("ObjectT", bound=TaravObject)


class LoadingProfile(ABC):
    """Opt-in ordered entry paths for loading from a directory."""

    @classmethod
    @abstractmethod
    def loading_paths(cls) -> tuple[str, ...]: ...


def profile_paths(profile: type[LoadingProfile] | None) -> tuple[str, ...] | None:
    if profile is None:
        return None
    if not isinstance(profile, type) or not issubclass(profile, LoadingProfile):
        raise TypeError("profile must be a LoadingProfile class")
    return profile.loading_paths()


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
    from tarav.runtime import get_runtime

    return get_runtime().load_object(path, profile=profile, expected_type=expected_type)


__all__ = ["LoadingProfile", "LoadingWorkflow", "load"]
