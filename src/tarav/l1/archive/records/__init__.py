"""Archive's typed, explicitly located Record-storage workflow."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Literal, Self
from uuid import uuid4

from filelock import FileLock
from pydantic import BaseModel, ConfigDict, field_validator

from tarav.l0._core.persistence import atomic_write_json
from tarav.l0.kernel.current import current_records
from tarav.l0.kernel import (
    DirectoryRecord,
    ExplorerEntry,
    ExplorerFolder,
    ExplorerList,
    Ship,
    TaravClass,
    TaravEntity,
    TaravObject,
    TaravType,
    TypeShip,
    WorkflowShip,
    entity,
)
from tarav.l0.kernel.workflows import TaravWorkflow
from tarav.l1.records.storage import write_typed_record
# tarav.breadcrumb a64a1925bb13

from .git import (
    GIT_CONFIG_FILENAME,
    initialize_repository,
    placement_for_nested_child,
)


RECORD_ARCHIVE_WORKFLOW_SHIP = WorkflowShip("bf8ee310-60ac-40c2-a259-60412910fdba")
ENTRIES_FILENAME = "entries.json"


class ArchiveType(TaravType):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a8c878a0-f100-4228-aefb-12d6c851fabb"),
                          name="Tarav.RecordArchive.Type", workflow=RECORD_ARCHIVE_WORKFLOW_SHIP)


class ArchiveObject(TaravObject, ArchiveType):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e1372cef-2947-4376-a351-a82fc2733342"),
                          name="Tarav.RecordArchive.Object", workflow=RECORD_ARCHIVE_WORKFLOW_SHIP)


def _name(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("Archive name must be a string")
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError("Archive name must be one ordinary path segment")
    return value


def _relative_path(value: str, directory: str, *, json_file: bool = False) -> str:
    path = Path(value)
    if len(path.parts) != 2 or path.parts[0] != directory:
        raise ValueError(f"Archive path must be directly in {directory}/")
    _name(path.name)
    if json_file and path.suffix != ".json":
        raise ValueError(f"Archive Record path must be a JSON file in {directory}/")
    return value


class ArchiveEntry(ExplorerEntry, ArchiveObject):
    """A retained link from one Archive placement to an artifact."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("25fb37cf-e460-4d51-8e46-8898ca27fadd"),
            name="Tarav.RecordArchive.Entry",
            workflow=RECORD_ARCHIVE_WORKFLOW_SHIP,
        )

    class RecordInterface(ExplorerEntry.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: Literal["Tarav.RecordArchive.Entry"]
        archive: Ship | None = None
        artifact: str | None = None

        @field_validator("artifact")
        @classmethod
        def validate_artifact(cls, value: str | None) -> str | None:
            if value is None:
                return None
            return _relative_path(value, "artifacts")

    def __init__(
        self,
        placement: str | int | None = None,
        *,
        archive: Ship | None = None,
        artifact: str | None = None,
        root: Path | None = None,
        record_path: str | None = None,
        opener: Callable[[], TaravObject] | None = None,
        directory: bool = False,
        child_directory: Path | None = None,
    ) -> None:
        super().__init__()
        if isinstance(placement, str):
            _name(placement)
        elif placement is not None and (
            not isinstance(placement, int) or isinstance(placement, bool)
        ):
            raise TypeError("Archive placement must be a name or integer")
        if artifact is not None:
            self.RecordInterface.validate_artifact(artifact)
        if record_path is not None:
            _relative_path(record_path, "records", json_file=True)
        self.archive = archive
        self.placement = placement
        self.artifact = artifact
        self.root = root
        self.record_path = record_path
        self._opener = opener
        self.directory = directory
        self.child_directory = child_directory

    @property
    def name(self) -> str:
        if self.placement is None:
            raise ValueError("Unbound Archive entry has no placement")
        return str(self.placement)

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls(
            archive=record_data.archive,
            artifact=record_data.artifact,
        )

    class Records(ExplorerEntry.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return {
                "type": entity(cls).name,
                "archive": "ec885738-bd64-4ba8-a223-5a92f0f25843",
                "artifact": "artifacts/example.json",
            }


    def _to_record(self) -> Mapping[str, object]:
        record: dict[str, object] = {"type": entity(type(self)).name}
        if self.archive is not None:
            record["archive"] = str(self.archive)
        if self.artifact is not None:
            record["artifact"] = self.artifact
        return record

    def artifact_location(self) -> Path:
        if self.artifact is None or self.root is None:
            raise ValueError("Archive entry is not bound to a stored artifact")
        root = self.root.resolve()
        target = (root / self.artifact).resolve()
        if not target.is_relative_to(root / "artifacts"):
            raise ValueError("Archive entry escapes its artifacts directory")
        return target

    def open(self) -> TaravObject:
        if self._opener is not None:
            result = self._opener()
            if not isinstance(result, TaravObject):
                raise TypeError("Archive entry opener must return a TaravObject")
            return result
        if self.artifact is None:
            return self
        return current_records().load(self.artifact_location())

class ArchiveEntity(TaravEntity, DirectoryRecord, ArchiveObject):
    """Shared storage mechanics; concrete archive Types own their interface."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("541ebfc7-f9d0-4082-966a-0b03be11ea69"),
            name="Tarav.RecordArchive",
            workflow=RECORD_ARCHIVE_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravEntity.RecordInterface, DirectoryRecord.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: Literal["Tarav.RecordArchive"]
        constitution: str

    def __init__(self, id: Ship, constitution: str) -> None:
        super().__init__(id)
        if not constitution.strip():
            raise ValueError("Archive constitution must be non-empty")
        self.constitution = constitution

    @property
    def root(self) -> Path:
        return self.directory

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls(record_data.id, record_data.constitution)

    class Records(TaravEntity.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return {
                "type": entity(cls).name,
                "id": "43c12f03-8699-4427-b780-a0c3ccf32289",
                "constitution": "Example Archive.",
            }


    @classmethod
    def from_path(cls, root: Path) -> Self:
        return current_records().load(root, expected_type=cls)

    @classmethod
    def create(
        cls, root: Path, *, constitution: str, _initialize_git: bool = True
    ) -> Self:
        root = root.expanduser().absolute()
        root.mkdir(parents=True, exist_ok=False)
        if _initialize_git:
            initialize_repository(root)
        (root / "records").mkdir()
        (root / "artifacts").mkdir()
        result = cls(Ship(uuid4()), constitution)
        result.source = root / "main.json"
        result._initialize_entries()
        result._save()
        return result

    def _initialize_entries(self) -> None:
        """Concrete storage structures create their own empty entry registry."""

    def _save(self) -> None:
        atomic_write_json(self.root / "main.json", self.records.to_record())

    def _write_lock(self) -> FileLock:
        return FileLock(str(self.root / ".entries.lock"))

    def _storage_target(self, directory: str, name: str) -> Path:
        root = self.root.resolve()
        parent = (root / directory).resolve()
        if parent != root / directory:
            raise ValueError(f"Archive {directory}/ directory is redirected")
        return parent / name

    def _store(self, obj: TaravObject) -> str:
        if isinstance(obj, ArchiveEntity):
            raise TypeError("Create nested Archives in place with put_archive()")
        key = uuid4().hex
        artifact = f"artifacts/{key}.json"
        write_typed_record(self._storage_target("artifacts", f"{key}.json"), obj)
        return self._write_entry(key, artifact)

    def _write_entry(self, key: str, artifact: str) -> str:
        relative = f"records/{key}.json"
        entry = ArchiveEntry(archive=self.id, artifact=artifact)
        atomic_write_json(
            self._storage_target("records", f"{key}.json"), entry.records.to_record()
        )
        return relative

    def _create_archive_artifact(
        self, archive_type: type[ArchiveEntity], *, constitution: str
    ) -> str:
        if not isinstance(archive_type, type) or not issubclass(
            archive_type, ArchiveEntity
        ):
            raise TypeError("Nested Archive Type must extend ArchiveEntity")
        if (
            current_records().resolve({"type": entity(archive_type).name})
            is not archive_type
        ):
            raise ValueError("Nested Archive must have its exact registered Type")
        key = uuid4().hex
        artifact = f"artifacts/{key}"
        target = self._storage_target("artifacts", key)
        parent = target.parent
        initialize = placement_for_nested_child(parent, self.root).initialize
        archive_type.create(
            target,
            constitution=constitution,
            _initialize_git=initialize,
        )
        return self._write_entry(key, artifact)

    def _entry(self, placement: str | int, path: str) -> ArchiveEntry:
        relative = _relative_path(path, "records", json_file=True)
        root = self.root.resolve()
        target = (root / relative).resolve()
        if not target.is_relative_to(root / "records"):
            raise ValueError("Archive entry Record escapes its records directory")
        entry = current_records().load(target, expected_type=ArchiveEntry)
        if entry.archive != self.id or entry.artifact is None:
            raise ValueError("Archive entry does not belong to its containing Archive")
        entry.placement = placement
        entry.root = self.root
        entry.record_path = relative
        location = entry.artifact_location()
        if not location.exists():
            raise FileNotFoundError(f"Archive entry artifact is missing: {location}")
        if location.is_dir() and not (location / "main.json").is_file():
            raise FileNotFoundError(
                f"Archive entry directory has no main.json: {location}"
            )
        if not location.is_file() and not location.is_dir():
            raise ValueError(
                f"Archive entry artifact is not a file or directory: {location}"
            )
        entry.directory = location.is_dir()
        entry.child_directory = location if entry.directory else None
        return entry

    def _listed_entry(self, placement: str | int, path: str) -> ArchiveEntry:
        """Expose an indexed placement without opening its entry Record."""

        relative = _relative_path(path, "records", json_file=True)
        return ArchiveEntry(
            placement,
            archive=self.id,
            root=self.root,
            record_path=relative,
            opener=lambda: self.get(placement).open(),
        )

    def _to_record(self) -> Mapping[str, object]:
        return {**super()._to_record(), "constitution": self.constitution}

    @property
    def git_config_path(self) -> Path:
        return self.root / GIT_CONFIG_FILENAME

    @property
    def gitignore_path(self) -> Path:
        return self.root / ".gitignore"

    @property
    def gitignore_exists(self) -> bool:
        return self.gitignore_path.is_file()


class ArchiveFolder(ArchiveEntity, ExplorerFolder):
    """An Archive whose entries have ordinary names, independent of Ships."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("e67748c1-6ae8-4e9e-b868-913c57ec479d"),
            name="Tarav.RecordArchive.Dictionary",
            workflow=RECORD_ARCHIVE_WORKFLOW_SHIP,
        )

    class RecordInterface(ArchiveEntity.RecordInterface):
        type: Literal["Tarav.RecordArchive.Dictionary"]

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls(record_data.id, record_data.constitution)

    @property
    def entries(self) -> dict[str, str]:
        value = json.loads((self.root / ENTRIES_FILENAME).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Dictionary Archive entries must be a JSON object")
        for name, path in value.items():
            if not isinstance(name, str) or not isinstance(path, str):
                raise ValueError("Dictionary Archive entries must map names to paths")
            _name(name)
            _relative_path(path, "records", json_file=True)
        return value

    def _initialize_entries(self) -> None:
        self._save_entries({})

    def _save_entries(self, entries: dict[str, str]) -> None:
        atomic_write_json(self.root / ENTRIES_FILENAME, entries)

    def ls(self) -> tuple[ArchiveEntry, ...]:
        return tuple(
            self._listed_entry(name, path) for name, path in self.entries.items()
        )

    def get(self, name: str) -> ArchiveEntry:
        name = _name(name)
        return self._entry(name, self.entries[name])

    def put(self, name: str, obj: TaravObject) -> ArchiveEntry:
        return self._put(name, lambda: self._store(obj))

    def put_archive(
        self, name: str, archive_type: type[ArchiveEntity], *, constitution: str
    ) -> ArchiveEntry:
        return self._put(
            name,
            lambda: self._create_archive_artifact(
                archive_type, constitution=constitution
            ),
        )

    def _put(self, name: str, create_entry: Callable[[], str]) -> ArchiveEntry:
        name = _name(name)
        with self._write_lock():
            entries = self.entries
            if name in entries:
                raise FileExistsError(f"Archive name already exists: {name}")
            path = create_entry()
            entries[name] = path
            self._save_entries(entries)
        return self._entry(name, path)


class ArchiveList(ArchiveEntity, ExplorerList):
    """An ordered Archive; positions may change when entries are inserted."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("dfeddbd2-aa17-4d7a-8c9a-e6eb7064c7e4"),
            name="Tarav.RecordArchive.Vector",
            workflow=RECORD_ARCHIVE_WORKFLOW_SHIP,
        )

    class RecordInterface(ArchiveEntity.RecordInterface):
        type: Literal["Tarav.RecordArchive.Vector"]

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls(record_data.id, record_data.constitution)

    @property
    def entries(self) -> list[str]:
        value = json.loads((self.root / ENTRIES_FILENAME).read_text(encoding="utf-8"))
        if not isinstance(value, list) or any(
            not isinstance(path, str) for path in value
        ):
            raise ValueError("Vector Archive entries must be a JSON Record path list")
        for path in value:
            _relative_path(path, "records", json_file=True)
        return value

    def _initialize_entries(self) -> None:
        self._save_entries([])

    def _save_entries(self, entries: list[str]) -> None:
        atomic_write_json(self.root / ENTRIES_FILENAME, entries)

    def ls(self) -> tuple[ArchiveEntry, ...]:
        return tuple(
            self._listed_entry(position, path)
            for position, path in enumerate(self.entries)
        )

    def get(self, position: int) -> ArchiveEntry:
        return self._entry(position, self.entries[position])

    def insert(self, position: int, obj: TaravObject) -> ArchiveEntry:
        return self._insert(position, lambda: self._store(obj))

    def append(self, obj: TaravObject) -> ArchiveEntry:
        return self._insert(None, lambda: self._store(obj))

    def insert_archive(
        self,
        position: int,
        archive_type: type[ArchiveEntity],
        *,
        constitution: str,
    ) -> ArchiveEntry:
        return self._insert(
            position,
            lambda: self._create_archive_artifact(
                archive_type, constitution=constitution
            ),
        )

    def append_archive(
        self, archive_type: type[ArchiveEntity], *, constitution: str
    ) -> ArchiveEntry:
        return self._insert(
            None,
            lambda: self._create_archive_artifact(
                archive_type, constitution=constitution
            ),
        )

    def _insert(
        self, position: int | None, create_entry: Callable[[], str]
    ) -> ArchiveEntry:
        with self._write_lock():
            entries = self.entries
            selected = len(entries) if position is None else position
            if not isinstance(selected, int) or isinstance(selected, bool):
                raise TypeError("Vector position must be an integer")
            if not 0 <= selected <= len(entries):
                raise IndexError(selected)
            path = create_entry()
            entries.insert(selected, path)
            self._save_entries(entries)
        return self._entry(selected, path)


class RecordArchiveWorkflow(TaravWorkflow, ArchiveType):
    """Optional typed Record storage for workflows that choose an Archive root."""

    @property
    def workflow(self) -> TaravWorkflow:
        from tarav.l1.archive.workflow import ArchiveWorkflow

        return ArchiveWorkflow()

    @classmethod
    def _workflow_id(cls):
        return RECORD_ARCHIVE_WORKFLOW_SHIP

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("b6455e6c-54d5-4a1f-b88f-b1801c4471d5"),
            name="Tarav.Workflow.RecordArchive",
            workflow=RECORD_ARCHIVE_WORKFLOW_SHIP,
        )

    constitution = (
        "Provide explicitly located, typed Archives for retaining Tarav Records "
        "without owning the stored objects' domain meaning."
    )

    @classmethod
    def create_dictionary(
        cls, root: Path, *, constitution: str, _initialize_git: bool = True
    ) -> ArchiveFolder:
        return ArchiveFolder.create(
            root, constitution=constitution, _initialize_git=_initialize_git
        )

    @classmethod
    def create_vector(
        cls, root: Path, *, constitution: str, _initialize_git: bool = True
    ) -> ArchiveList:
        return ArchiveList.create(
            root, constitution=constitution, _initialize_git=_initialize_git
        )


# Navigation builds on the Archive Types above; import after their definitions.
from .navigation import ARCHIVE, ArchiveExplorer, ArchivePartition, ArchiveRoot  # noqa: E402


RECORD_ARCHIVE_TYPES = (
    ArchiveObject,
    ArchiveEntry,
    ArchiveEntity,
    ArchiveFolder,
    ArchiveList,
    ArchivePartition,
    ArchiveRoot,
)


__all__ = [
    "ArchiveType",
    "ArchiveObject",
    "ARCHIVE",
    "ArchiveExplorer",
    "ArchiveEntry",
    "ArchivePartition",
    "ArchiveFolder",
    "ArchiveEntity",
    "RecordArchiveWorkflow",
    "ArchiveRoot",
    "ArchiveList",
]
