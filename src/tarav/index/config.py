# $kw: Index.Evaluator/Configuration --from Scope.Axis --note [CT] the axis is project-scope vs user-scope, not public vs private
# --note [DC] The default Index evaluator derives project identity from .tarav/project.json and resolves evidence and surfaces structurally, without evaluator manifests. ^c20260821-1u
"""Index geography.

The project root locates source surfaces and project-local declarations. The user root
locates operational state. Neither is an Index-record tier: every ``LineRecord`` lives in
one Bloberia depot, and its ``scope`` distinguishes projects inside that model.

A clone can read its source surfaces without user state. It cannot resolve the serialized
record model or its chat evidence until the user-side record depot and archive are present.
"""

from __future__ import annotations

from tarav._core.errors import CliError

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIR_NAME = ".tarav"
USER_DIR_ENV = "TARAV_INDEX_HOME"
#: Beside `~/Documents/chatlas`, whose messages every record's support points at.
PUBLIC_INDEX_DEPOT = Path.home() / "Documents" / "bloberia" / "tarav-index"
#: Beside the records it accepts findings about, and grounded against the same archive.
PUBLIC_BLESSING_DEPOT = Path.home() / "Documents" / "bloberia" / "tarav-blessings"
PROJECT_ROOT_ENV = "TARAV_INDEX_PROJECT"

#: Markers that identify a project root when walking upward from the working directory.
_PROJECT_MARKERS = (PROJECT_DIR_NAME, "AGENTS.md", ".git")


class TaravIndexError(CliError):
    """Base error for every index operation.

    It is a `CliError` so the umbrella CLI reports it the way it reports every
    other subsystem's failure: one line on stderr, exit 1. The index does not
    get its own error convention just because it used to be its own program.
    """


class ScopeResolutionError(TaravIndexError):
    """Raised when a required scope root cannot be resolved."""


@dataclass(frozen=True, slots=True)
class Geography:
    """The project and user roots resolved for one invocation."""

    project_root: Path
    user_root: Path
    project_id: str | None = None

    @property
    def project_tier(self) -> Path:
        """Project-local declarations and manifests; never the record depot."""
        return self.project_root / PROJECT_DIR_NAME

    @property
    def user_tier(self) -> Path:
        """User-local operational state."""
        return self.user_root

    @property
    def index_dir(self) -> Path:
        """Project-tier index roots: what ships with the project."""
        return self.project_tier / "index"

    @property
    def index_depot(self) -> Path:
        """The one depot holding every index line record.

        Public by default, beside the Chatlas archive it grounds against: an important
        system carries its own visible home rather than hiding in a dotfile. A configured
        user root still wins, which is what keeps a test isolated from the real corpus.
        """
        if self.user_root != _default_user_root():
            return self.user_root / "index"
        return PUBLIC_INDEX_DEPOT

    @property
    def blessing_depot(self) -> Path:
        """The one depot holding every `Blessing.Record`.

        Public and user-side for the same reason the record depot is: a blessing's support
        points at chat evidence that never ships with a project, and its subject is a
        depot-global record id, so there is no project data in it to make it project-tier.
        """

        if self.user_root != _default_user_root():
            return self.user_root / "blessings"
        return PUBLIC_BLESSING_DEPOT

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

    An explicit ``TARAV_INDEX_PROJECT`` always wins, so tests and tooling can bind a root
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


def _default_user_root() -> Path:
    return Path.home() / PROJECT_DIR_NAME


def find_user_root() -> Path:
    override = os.environ.get(USER_DIR_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return _default_user_root()


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
