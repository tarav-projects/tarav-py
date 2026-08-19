# $kw: --from Scope.Axis --note [CT] the axis is project-scope vs user-scope, not public vs private
"""LineScope resolution.

Two tiers, and the distinction is *not* public/private:

- ``Project.LineScope`` — this project's shared understanding, at ``<project>/.tarav/``.
- ``User.LineScope`` — the user's working life across all projects, at ``~/.tarav/``.

The rule that settles placement arguments: a fresh clone with no user tier must be able to
use the project and read its index. Grounding degrades; nothing else does.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIR_NAME = ".tarav"
USER_DIR_ENV = "TARAV2_HOME"
PROJECT_ROOT_ENV = "TARAV2_PROJECT"

#: Markers that identify a project root when walking upward from the working directory.
_PROJECT_MARKERS = (PROJECT_DIR_NAME, "AGENTS.md", ".git")


class TaravIndexError(RuntimeError):
    """Base error for every index operation."""


class ScopeResolutionError(TaravIndexError):
    """Raised when a required scope root cannot be resolved."""


@dataclass(frozen=True, slots=True)
class Geography:
    """The two resolved tiers for one invocation."""

    project_root: Path
    user_root: Path

    @property
    def project_tier(self) -> Path:
        """Project-scoped index state: record, manifests, chat index."""
        return self.project_root / PROJECT_DIR_NAME

    @property
    def user_tier(self) -> Path:
        """User-scoped index state: the authority archive."""
        return self.user_root

    @property
    def index_dir(self) -> Path:
        """Project-tier index roots: what ships with the project."""
        return self.project_tier / "index"

    @property
    def manifest_dir(self) -> Path:
        return self.project_tier / "manifests"

    @property
    def user_index_dir(self) -> Path:
        """User-tier index roots: a full index held outside the project folder."""
        return self.user_tier / "index"

    def ensure_project_tier(self) -> Path:
        self.project_tier.mkdir(parents=True, exist_ok=True)
        return self.project_tier

    def ensure_user_tier(self) -> Path:
        self.user_tier.mkdir(parents=True, exist_ok=True)
        return self.user_tier


def find_project_root(start: Path | None = None) -> Path:
    """Walk upward from ``start`` until a project marker is found.

    An explicit ``TARAV2_PROJECT`` always wins, so tests and tooling can bind a root
    without depending on the working directory.
    """

    override = os.environ.get(PROJECT_ROOT_ENV)
    if override:
        return Path(override).expanduser().resolve()

    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if any((candidate / marker).exists() for marker in _PROJECT_MARKERS):
            return candidate
    return current


def find_user_root() -> Path:
    override = os.environ.get(USER_DIR_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / PROJECT_DIR_NAME


def resolve_geography(start: Path | None = None) -> Geography:
    return Geography(project_root=find_project_root(start), user_root=find_user_root())


__all__ = [
    "PROJECT_DIR_NAME",
    "PROJECT_ROOT_ENV",
    "USER_DIR_ENV",
    "Geography",
    "ScopeResolutionError",
    "TaravIndexError",
    "find_project_root",
    "find_user_root",
    "resolve_geography",
]
