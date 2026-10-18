"""A standard, explicitly located map of typed Records by Workflow Ship."""
# tarav.breadcrumb 5147012fa21d

from __future__ import annotations

import json
import os
from pathlib import Path

from filelock import FileLock

from tarav.l0._core.data_root import default_tarav_data_root
from tarav.l0._core.git_repository import commit_paths, initialize_repository
from tarav.l0._core.persistence import atomic_write_json, atomic_write_text
from tarav.l0.kernel import TaravObject, TypeRegistry, WorkflowShip
from tarav.l0.kernel.current import current_records
from tarav.l0.kernel.space import Entry, FilesystemProvider
from tarav.l0.kernel.workflows import TaravWorkflow
from tarav.l1.references import FileReference
from tarav.l1.references.git import GitFileReference

from .storage import write_typed_record


REGISTRY_MARKER = "registry.json"
REGISTRY_KIND = "Tarav.Records.Registry"


def _key(value: str) -> str:
    if not isinstance(value, str) or not value or value in {".", ".."}:
        raise ValueError("Record key must be one nonempty path segment")
    if "/" in value or "\\" in value or value.startswith("."):
        raise ValueError("Record key must be one ordinary path segment")
    return value


def default_records_root() -> Path:
    """The standard Record Registry. ``TARAV_RECORDS`` relocates it, which test suites use."""
    override = os.getenv("TARAV_RECORDS")
    if override:
        return Path(override).expanduser().resolve()
    return default_tarav_data_root() / "records"


class RecordMap:
    """One Git-capable Workflow partition with caller-chosen Record keys."""

    def __init__(
        self, root: Path, workflow: WorkflowShip,
        records: TypeRegistry[TaravObject] | None = None,
    ) -> None:
        self.root = root.expanduser().resolve()
        self.workflow = workflow
        self.records = records if records is not None else current_records()

    @property
    def marker(self) -> Path:
        return self.root / REGISTRY_MARKER

    @property
    def records_dir(self) -> Path:
        return self.root / "records"

    def create(self) -> RecordMap:
        if self.marker.is_file():
            return self.open()
        if self.root.exists() and any(self.root.iterdir()):
            raise FileExistsError(f"Record Registry location is not empty: {self.root}")
        self.root.mkdir(parents=True, exist_ok=True)
        initialize_repository(self.root)
        self.records_dir.mkdir()
        atomic_write_text(self.root / ".gitignore", ".write.lock\n")
        atomic_write_json(
            self.marker,
            {"kind": REGISTRY_KIND, "workflow": str(self.workflow), "schema": 1},
        )
        return self

    def open(self) -> RecordMap:
        if not self.marker.is_file() or not (self.root / ".git").is_dir():
            raise FileNotFoundError(f"Record Registry is not initialized: {self.root}")
        marker = json.loads(self.marker.read_text(encoding="utf-8"))
        expected = {"kind": REGISTRY_KIND, "workflow": str(self.workflow), "schema": 1}
        if marker != expected or not self.records_dir.is_dir():
            raise ValueError(f"Invalid Record Registry partition: {self.root}")
        return self

    def path(self, name: str) -> Path:
        selected = self.records_dir.resolve()
        if selected != self.root / "records":
            raise ValueError("Record Registry records directory is redirected")
        return selected / f"{_key(name)}.json"

    def names(self) -> tuple[str, ...]:
        self.open()
        return tuple(path.stem for path in sorted(self.records_dir.glob("*.json")))

    def load(self, name: str) -> TaravObject:
        self.open()
        return self.records.load(self.path(name))

    def insert(self, name: str, obj: TaravObject) -> Path:
        self.open()
        target = self.path(name)
        with FileLock(str(self.root / ".write.lock")):
            if target.exists():
                raise FileExistsError(target)
            write_typed_record(target, obj, records=self.records)
        return target

    def replace(self, name: str, obj: TaravObject) -> Path:
        self.open()
        target = self.path(name)
        with FileLock(str(self.root / ".write.lock")):
            if not target.is_file():
                raise FileNotFoundError(target)
            write_typed_record(target, obj, records=self.records)
        return target

    def working_reference(self, name: str) -> FileReference:
        self.load(name)
        return FileReference(self.path(name))

    def head_reference(self, name: str) -> GitFileReference:
        self.open()
        return GitFileReference(repository=self.root, commit="HEAD", path=f"records/{_key(name)}.json")

    def edition_reference(self, name: str, commit: str) -> GitFileReference:
        self.open()
        return GitFileReference(repository=self.root, commit=commit, path=f"records/{_key(name)}.json")

    def commit(self, names: tuple[str, ...], message: str) -> str:
        self.open()
        if not names:
            raise ValueError("Record Registry commit needs at least one Record key")
        for name in names:
            if not self.path(name).is_file():
                raise FileNotFoundError(self.path(name))
        paths = (REGISTRY_MARKER, ".gitignore", *(f"records/{_key(name)}.json" for name in names))
        return commit_paths(self.root, paths, message)


class RecordRegistry:
    """Standard Workflow partitions; each partition owns its repository."""

    def __init__(
        self, root: Path | None = None,
        records: TypeRegistry[TaravObject] | None = None,
    ) -> None:
        self.root = (root or default_records_root()).expanduser().resolve()
        self.records = records if records is not None else current_records()

    def for_workflow(self, workflow: type[TaravWorkflow]) -> RecordMap:
        if not isinstance(workflow, type) or not issubclass(workflow, TaravWorkflow):
            raise TypeError("Record Registry partition requires a Workflow Type")
        ship = workflow().id
        return RecordMap(self.root / str(ship), ship, self.records)

    def provider(self) -> RegistryProvider:
        return RegistryProvider(self.root, self.records)


class RegistryProvider(FilesystemProvider):
    """Navigate initialized Registry partitions without exposing their markers."""

    def list(self, address: str = "") -> tuple[Entry, ...]:
        if not address:
            if not self.root.is_dir():
                return ()
            return tuple(
                Entry(path.name, "collection")
                for path in sorted(self.root.iterdir())
                if path.is_dir() and not path.is_symlink()
                and (path / REGISTRY_MARKER).is_file()
            )
        entries = super().list(address)
        if len(Path(address).parts) == 1:
            return tuple(entry for entry in entries if entry.name != REGISTRY_MARKER)
        return entries


__all__ = [
    "RecordMap", "RecordRegistry", "RegistryProvider", "default_records_root",
]
