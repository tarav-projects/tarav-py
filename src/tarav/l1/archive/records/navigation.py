"""Record Archive folders, workflow partitions, and route-aware exploration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self, TypeVar

from pydantic import BaseModel

from tarav.l0._core.data_root import default_tarav_data_root
from tarav.l0.kernel.current import current_records
from tarav.l0.kernel.records import resolve_workflow
from tarav.l0.kernel import (
    Explorer,
    ExplorerFolder,
    ExplorerList,
    TaravClass,
    TaravObject,
    TypeShip,
    WorkflowShip,
    entity,
)
from tarav.l0.kernel.workflows import TaravWorkflow

from . import (
    RECORD_ARCHIVE_WORKFLOW_SHIP,
    ArchiveEntry,
    ArchiveObject,
    ArchiveType,
    ArchiveFolder,
    ArchiveEntity,
    ArchiveList,
    _name,
)
from .git import GIT_CONFIG_FILENAME, initialize_repository, placement_for_child


ArchiveT = TypeVar("ArchiveT", bound=ArchiveEntity)
ArchiveContainer = ExplorerFolder | ExplorerList


class ArchiveRoot(ExplorerFolder, ArchiveObject):
    """The top-level folder containing Workflow Ship partitions."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("7c6d182f-3547-4a44-90b3-d9fa5db7a68d"),
            name="Tarav.RecordArchive.Root",
            workflow=RECORD_ARCHIVE_WORKFLOW_SHIP,
        )

    class RecordInterface(ExplorerFolder.RecordInterface):
        type: Literal["Tarav.RecordArchive.Root"]

    def __init__(self, root: Path | None = None) -> None:
        super().__init__()
        self.root = (
            (root or default_tarav_data_root() / "archive").expanduser().resolve()
        )

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls()

    @property
    def directory(self) -> Path:
        return self.root

    def ls(self) -> tuple[ArchiveEntry, ...]:
        if not self.root.is_dir():
            return ()
        entries: list[ArchiveEntry] = []
        for child in sorted(self.root.iterdir(), key=lambda path: path.name):
            if not child.is_dir() or child.is_symlink() or child.name == ".git":
                continue
            try:
                ship = WorkflowShip(child.name)
            except ValueError as exc:
                raise ValueError(
                    f"Archive partition is not a Workflow Ship: {child.name}"
                ) from exc
            if child.name != str(ship):
                raise ValueError(
                    f"Archive partition is not a canonical Workflow Ship: {child.name}"
                )
            entries.append(
                ArchiveEntry(
                    child.name,
                    opener=lambda ship=ship: ArchivePartition(self.root, ship),
                    directory=True,
                    child_directory=child,
                )
            )
        return tuple(entries)

    def get(self, name: str) -> ArchiveEntry:
        _name(name)
        for entry in self.ls():
            if entry.name == name:
                return entry
        raise KeyError(name)

    def for_workflow(
        self, workflow: type[TaravWorkflow]
    ) -> ArchivePartition:
        """Address a registered Workflow's Ship partition without creating it."""

        workflow_type = workflow
        if not isinstance(workflow_type, type) or not issubclass(workflow_type, TaravWorkflow):
            raise TypeError("Archive partition requires a TaravWorkflow")
        ship = workflow_type().id
        registered = type(resolve_workflow(ship))
        if registered is not workflow_type:
            raise TypeError("Workflow Ship resolves to a different Workflow class")
        return ArchivePartition(self.root, ship)


class ArchivePartition(ExplorerFolder, ArchiveObject):
    """A named grouping inside one Workflow's Archive space."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("19fabd2b-02a3-4057-96e4-b68fdc01f771"),
            name="Tarav.RecordArchive.Partition",
            workflow=RECORD_ARCHIVE_WORKFLOW_SHIP,
        )

    class RecordInterface(ExplorerFolder.RecordInterface):
        type: Literal["Tarav.RecordArchive.Partition"]
        workflow: WorkflowShip
        root: str
        parts: list[str]

    def __init__(
        self,
        root: Path,
        workflow: WorkflowShip,
        parts: tuple[str, ...] | None = None,
    ) -> None:
        super().__init__()
        if not isinstance(workflow, WorkflowShip):
            raise TypeError("Archive partition requires a Workflow Ship")
        selected = parts if parts is not None else (str(workflow),)
        if not selected or selected[0] != str(workflow):
            raise ValueError("Archive partition must start with its Workflow Ship")
        self.root = root.expanduser().resolve()
        self.workflow_ship = workflow
        self.parts = tuple(_name(part) for part in selected)

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls(
            Path(record_data.root), record_data.workflow, tuple(record_data.parts)
        )

    class Records(ExplorerFolder.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            ship = str(RECORD_ARCHIVE_WORKFLOW_SHIP)
            return {
                "type": entity(cls).name,
                "workflow": ship,
                "root": "/example/archive",
                "parts": [ship],
            }


    def _to_record(self) -> dict[str, object]:
        return {
            "type": entity(type(self)).name,
            "workflow": str(self.workflow_ship),
            "root": str(self.root),
            "parts": list(self.parts),
        }

    @property
    def directory(self) -> Path:
        directory = self.root.joinpath(*self.parts)
        if not directory.resolve().is_relative_to(self.root):
            raise ValueError("Archive partition escapes its root")
        return directory

    def owning_workflow(self) -> type[TaravWorkflow]:
        """Return the Workflow Entity associated with this partition."""

        return type(resolve_workflow(self.workflow_ship))

    @property
    def workflow(self) -> TaravWorkflow:
        return self.owning_workflow()()

    @property
    def git_config_path(self) -> Path:
        return self.directory / GIT_CONFIG_FILENAME

    @property
    def gitignore_path(self) -> Path:
        return self.directory / ".gitignore"

    @property
    def gitignore_exists(self) -> bool:
        return self.gitignore_path.is_file()

    def git_settings(self) -> dict[str, object]:
        placement = placement_for_child(self.directory, self.root / str(self.workflow_ship))
        return {
            "children": placement.mode,
            "source": placement.source,
            "repository": placement.parent_repository,
            "gitignore_path": self.gitignore_path,
            "gitignore_exists": self.gitignore_exists,
        }

    def ls(self) -> tuple[ArchiveEntry, ...]:
        if not self.directory.is_dir():
            return ()
        entries: list[ArchiveEntry] = []
        for child in sorted(self.directory.iterdir(), key=lambda path: path.name):
            if not child.is_dir() or child.is_symlink() or child.name == ".git":
                continue
            if (child / "main.json").is_file():

                def opener(child: Path = child) -> TaravObject:
                    return _open_directory(child)
            else:

                def opener(name: str = child.name) -> TaravObject:
                    return ArchivePartition(
                        self.root, self.workflow_ship, (*self.parts, name)
                    )

            entries.append(
                ArchiveEntry(
                    child.name,
                    opener=opener,
                    directory=True,
                    child_directory=child,
                )
            )
        return tuple(entries)

    def get(self, name: str) -> ArchiveEntry:
        _name(name)
        for entry in self.ls():
            if entry.name == name:
                return entry
        raise KeyError(name)

    def create_directory(self, name: str) -> ArchivePartition:
        """Create one named grouping without assigning another Ship."""

        name = _name(name)
        self.directory.mkdir(parents=True, exist_ok=True)
        placement = placement_for_child(self.directory, self.root / str(self.workflow_ship))
        initialize = placement.initialize
        child = self.directory / name
        child.mkdir(exist_ok=False)
        if initialize:
            initialize_repository(child)
        return ArchivePartition(self.root, self.workflow_ship, (*self.parts, name))

    def create_archive(
        self,
        name: str,
        archive_type: type[ArchiveT],
        *,
        constitution: str,
        **archive_options: object,
    ) -> ArchiveT:
        """Create one registered typed Archive under this grouping."""

        if not isinstance(archive_type, type) or not issubclass(
            archive_type, ArchiveEntity
        ):
            raise TypeError("Archive Type must extend ArchiveEntity")
        if (
            current_records().resolve({"type": entity(archive_type).name})
            is not archive_type
        ):
            raise ValueError("Archive must have its exact registered Type")
        name = _name(name)
        self.directory.mkdir(parents=True, exist_ok=True)
        placement = placement_for_child(self.directory, self.root / str(self.workflow_ship))
        return archive_type.create(
            self.directory / name,
            constitution=constitution,
            _initialize_git=placement.initialize,
            **archive_options,
        )

    def create_dictionary(self, name: str, *, constitution: str) -> ArchiveFolder:
        return self.create_archive(name, ArchiveFolder, constitution=constitution)

    def create_vector(self, name: str, *, constitution: str) -> ArchiveList:
        return self.create_archive(name, ArchiveList, constitution=constitution)


@dataclass(frozen=True)
class ArchiveLocation:
    container: ArchiveObject
    parts: tuple[str, ...]
    parent: ArchiveLocation | None = None


class ArchiveExplorer(Explorer[ArchiveLocation], ArchiveType):
    """A route through Archive containers with independent visit history."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("0b52f5f4-f0cf-4ca7-a7eb-fd0e6605054b"),
            name="Tarav.RecordArchive.Explorer",
            workflow=RECORD_ARCHIVE_WORKFLOW_SHIP,
        )

    def __init__(self, root: ArchiveObject | None = None) -> None:
        selected = root if root is not None else ARCHIVE
        if not isinstance(selected, ArchiveObject):
            raise TypeError("Archive explorer root must be an ArchiveObject")
        self.root = selected
        parts = selected.parts if isinstance(selected, ArchivePartition) else ()
        super().__init__(ArchiveLocation(selected, parts))

    def ls(self) -> tuple[ArchiveEntry, ...]:
        entries = self._container(self.current.container).ls()
        if any(not isinstance(entry, ArchiveEntry) for entry in entries):
            raise TypeError("Archive container must expose ArchiveEntry values")
        return entries

    def get(self, key: str | int) -> ArchiveEntry:
        entry = self._select(self.current.container, key)
        if not isinstance(entry, ArchiveEntry):
            raise TypeError("Archive container must expose ArchiveEntry values")
        return entry

    def cd(self, key: str | int) -> Self:
        if isinstance(key, str) and "/" in key and key != "/":
            previous = self.current, list(self._back_stack), list(self._forward_stack)
            try:
                if key.startswith("/"):
                    self.cd("/")
                for part in key.split("/"):
                    if part:
                        self.cd(part)
            except Exception:
                self._current, self._back_stack, self._forward_stack = previous
                raise
            return self
        if key == "/":
            root = self.current
            while root.parent is not None:
                root = root.parent
            if root is not self.current:
                self._visit(root)
            return self
        if key == ".":
            return self
        if key == "..":
            if self.current.parent is not None:
                self._visit(self.current.parent)
            return self
        if isinstance(self.current.container, ExplorerList) and isinstance(key, str):
            if not key.isdecimal() or (len(key) > 1 and key.startswith("0")):
                raise TypeError(
                    "Archive list path must use a canonical integer position"
                )
            key = int(key)
        entry = self.get(key)
        target = entry.open()
        self._container(target)
        if not isinstance(target, ArchiveObject):
            raise TypeError("Archive destination must be an ArchiveObject")
        self._visit(
            ArchiveLocation(target, (*self.current.parts, entry.name), self.current)
        )
        return self

    def pwd(self) -> str:
        return "/" + "/".join(self.current.parts)


def _open_directory(directory: Path) -> TaravObject:
    return current_records().load(directory)


ARCHIVE = ArchiveRoot()


__all__ = [
    "ARCHIVE",
    "ArchiveExplorer",
    "ArchiveLocation",
    "ArchivePartition",
    "ArchiveRoot",
]
