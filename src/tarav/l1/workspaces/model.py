"""Typed recipe and identity for a reproducible workspace layout."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TypeShip
from tarav.l1.checks import CheckProvider, CheckSuite

from .workflow import WORKSPACES_WORKFLOW_SHIP
from tarav.l0.kernel import LoadedRecord


def _relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("Workspace paths must be nonempty POSIX-relative paths")
    path = PurePosixPath(value)
    if (path.is_absolute() or path.as_posix() != value or
            any(part in {".", "..", ".git"} for part in path.parts) or
            path.parts[0] in {"seeds", "manifest.json", "setup.json", "AGENTS.md"}):
        raise ValueError(f"Unsafe workspace path: {value}")
    return value


class WorkspaceEntry(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    path: str

    @field_validator("path")
    @classmethod
    def valid_path(cls, value: str) -> str:
        return _relative_path(value)


class CopiedDocument(WorkspaceEntry):
    kind: Literal["copy"] = "copy"
    source: str


class WorkspaceSymlink(WorkspaceEntry):
    kind: Literal["symlink"] = "symlink"
    target: str


class RepositoryWorktree(WorkspaceEntry):
    kind: Literal["worktree"] = "worktree"
    repository: str
    commit: str

    @field_validator("commit")
    @classmethod
    def exact_commit(cls, value: str) -> str:
        if len(value) not in {40, 64} or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("Worktree commit must be an exact hexadecimal Git commit")
        return value


class NewDocument(WorkspaceEntry):
    kind: Literal["new"] = "new"
    seed: str

    @field_validator("seed")
    @classmethod
    def valid_seed(cls, value: str) -> str:
        return _relative_path(value)


Entry = Annotated[
    Union[CopiedDocument, WorkspaceSymlink, RepositoryWorktree, NewDocument],
    Field(discriminator="kind"),
]


# tarav.breadcrumb af6b8f157d1d
class WorkspaceManifest(TaravEntity.RecordInterface):
    """One workspace identity and its reproducible setup recipe."""

    model_config = ConfigDict(strict=True, extra="forbid")
    type: Literal["Tarav.Workspaces.Workspace"] = "Tarav.Workspaces.Workspace"
    label: str = Field(min_length=1)
    status: Literal["open", "harvested", "abandoned"] = "open"
    extracted: str = "none"
    project_ids: list[Ship] = Field(default_factory=list)
    entries: list[Entry] = Field(default_factory=list)

    @model_validator(mode="after")
    def nonoverlapping_destinations(self):
        paths = [PurePosixPath(entry.path) for entry in self.entries]
        for index, path in enumerate(paths):
            if any(path == other or path in other.parents or other in path.parents
                   for other in paths[index + 1:]):
                raise ValueError(f"Overlapping workspace destinations: {path}")
        return self

    @classmethod
    def new(cls, *, label: str, entries: list[Entry],
            project_ids: list[Ship] | None = None) -> WorkspaceManifest:
        return cls(id=Ship(str(uuid4())), label=label, entries=entries,
                   project_ids=project_ids or [])


class Workspace(TaravEntity, CheckProvider):
    """One identified working folder; its manifest is the retained Record."""

    RecordInterface = WorkspaceManifest

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("50bd8f32-47d4-4b53-9d75-6872a13eedb7"),
                          name="Tarav.Workspaces.Workspace", workflow=WORKSPACES_WORKFLOW_SHIP)

    def __init__(self, manifest: WorkspaceManifest, *, root: Path | None = None):
        super().__init__(manifest.id)
        self.manifest = manifest
        self.root = root
        if root is not None:
            self.source = root / "manifest.json"

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        return cls(loaded.data)

    def _to_record(self):
        return self.manifest.model_dump(mode="json")

    # tarav.breadcrumb 0371eb7b22af
    class Checks(CheckProvider.Checks):
        def suite(self) -> CheckSuite:
            if self.obj.root is None:
                raise ValueError("Detached Workspace has no checkable setup")
            from .checks import WorkspaceIntegrityCheck

            setup = WorkspaceSetupRecord.model_validate_json(
                (self.obj.root / "setup.json").read_text(encoding="utf-8"), strict=True
            )
            return CheckSuite((WorkspaceIntegrityCheck(self.obj, setup),))

    class Records(TaravEntity.Records):
        def record_example(self):
            cls = self._owner
            return cls(WorkspaceManifest(
                id=Ship("84e2214e-836a-4559-844b-cc4ee2a69ce7"), label="example"
            )).records.to_record()



class EntryObservation(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    content_hash: str | None = None
    source_hash: str | None = None
    commit: str | None = None
    branch: str | None = None


class WorkspaceSetupRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    workspace_id: Ship
    entries: dict[str, EntryObservation] = Field(default_factory=dict)


WORKSPACE_RECORD_TYPES = (Workspace,)


__all__ = [
    "CopiedDocument", "EntryObservation", "NewDocument", "RepositoryWorktree",
    "Workspace", "WorkspaceEntry", "WorkspaceManifest", "WorkspaceSetupRecord",
    "WorkspaceSymlink", "WORKSPACE_RECORD_TYPES",
]
