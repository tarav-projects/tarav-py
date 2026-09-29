"""Caller-selected Record entry discovery over Tarav's trusted loader."""

from __future__ import annotations

from abc import ABC, abstractmethod
from .workflow import LoadingWorkflow


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


__all__ = ["LoadingProfile", "LoadingWorkflow", "profile_paths"]
