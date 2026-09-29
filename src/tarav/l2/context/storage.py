"""Archive-backed retained Context for identified Tarav subjects."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from tarav.l0._core.data_root import default_tarav_data_root
from tarav.l0._core.persistence import atomic_write_json
from tarav.l0.kernel.current import current_records
from tarav.l1.context import (
    CONTEXT_WORKFLOW_SHIP,
    Context,
    ContextBuilder,
    ContextEntry,
    ContextObject,
    ContextSubject,
    ContextFolder,
    ContextList,
)
from tarav.l0.kernel.identity import Ship, TypeShip
from tarav.l0.kernel.records import TaravClass, TaravEntity, TaravObject, TaravType, entity
from tarav.l0.kernel.types import TypeRegistry
from tarav.l1.archive.records import (
    ArchiveEntry,
    ArchivePartition,
    ArchiveFolder,
    ArchiveEntity,
    ArchiveList,
)


class StoredDictionaryContext(ContextFolder):
    """A named Context folder whose children live in a Dictionary Archive."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("77002916-863d-4d99-80e9-c27490a8cf9e"),
            name="Tarav.Context.StoredDictionary",
            workflow=CONTEXT_WORKFLOW_SHIP,
        )

    class RecordInterface(ContextFolder.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: Literal["Tarav.Context.StoredDictionary"]
        archive: Ship

    def __init__(self, archive: Ship, subject: ContextSubject | None = None) -> None:
        super().__init__(subject if subject is not None else type(self), self._populate)
        self.archive = archive

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> StoredDictionaryContext:
        return cls(record_data.archive)

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {
            "type": entity(cls).name,
            "archive": "43c12f03-8699-4427-b780-a0c3ccf32289",
        }

    def _to_record(self) -> dict[str, object]:
        return {"type": entity(type(self)).name, "archive": str(self.archive)}

    def _populate(self, builder: ContextBuilder) -> None:
        _populate_stored_folder(self, ArchiveFolder, builder)


class StoredVectorContext(ContextList):
    """An ordered Context folder whose children live in a Vector Archive."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("82930532-5446-4d91-ac84-98bb6f97e086"),
            name="Tarav.Context.StoredVector",
            workflow=CONTEXT_WORKFLOW_SHIP,
        )

    class RecordInterface(ContextList.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: Literal["Tarav.Context.StoredVector"]
        archive: Ship

    def __init__(self, archive: Ship, subject: ContextSubject | None = None) -> None:
        super().__init__(subject if subject is not None else type(self), self._populate)
        self.archive = archive

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> StoredVectorContext:
        return cls(record_data.archive)

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {
            "type": entity(cls).name,
            "archive": "43c12f03-8699-4427-b780-a0c3ccf32289",
        }

    def _to_record(self) -> dict[str, object]:
        return {"type": entity(type(self)).name, "archive": str(self.archive)}

    def _populate(self, builder: ContextBuilder) -> None:
        _populate_stored_folder(self, ArchiveList, builder)


def _populate_stored_folder(
    folder: StoredDictionaryContext | StoredVectorContext,
    archive_type: type[ArchiveFolder] | type[ArchiveList],
    builder: ContextBuilder,
) -> None:
    if folder.source is None:
        raise ValueError("Stored Context folder has no Archive location")
    archive = current_records().load(
        folder.source.parent, expected_type=archive_type
    )
    if archive.id != folder.archive:
        raise ValueError("Context folder Archive Ship does not match its Record")
    current_context_service()._populate(folder.subject, archive, builder)


def _subject_ship(subject: ContextSubject) -> Ship | None:
    if isinstance(subject, type) and issubclass(subject, TaravType):
        return entity(subject).id
    if isinstance(subject, TaravEntity):
        return subject.id
    if isinstance(subject, TaravObject):
        return None
    raise TypeError("Context subject must be a TaravType class or TaravObject")


class SubjectContextRoot(ContextObject):
    """Context-owned binding beside a generic subject Archive."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("a49dcb0a-97dd-402d-a482-6386a1abc328"),
            name="Tarav.Context.SubjectRoot",
            workflow=CONTEXT_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: Literal["Tarav.Context.SubjectRoot"]
        subject: Ship
        archive: Ship

    def __init__(self, subject: Ship, archive: Ship) -> None:
        super().__init__()
        self.subject = subject
        self.archive = archive

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> SubjectContextRoot:
        return cls(record_data.subject, record_data.archive)

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {
            "type": entity(cls).name,
            "subject": "f1541079-b6ca-4e65-9d9c-4dd524597494",
            "archive": "43c12f03-8699-4427-b780-a0c3ccf32289",
        }

    def _to_record(self) -> dict[str, object]:
        return {
            "type": entity(type(self)).name,
            "subject": str(self.subject),
            "archive": str(self.archive),
        }


class ContextService:
    """Runtime-specific Context storage and composition."""

    def __init__(
        self,
        archive_root: Path | None = None,
        records: TypeRegistry[TaravObject] | None = None,
    ) -> None:
        self.archive_root = (
            (archive_root or default_tarav_data_root() / "archive")
            .expanduser()
            .resolve()
        )
        self.records = records

    @property
    def partition(self) -> ArchivePartition:
        return ArchivePartition(self.archive_root, CONTEXT_WORKFLOW_SHIP)

    def directory(self, subject: ContextSubject) -> Path:
        """Return one identified subject's Archive location without creating it."""

        ship = _subject_ship(subject)
        if ship is None:
            raise TypeError("Only identified subjects have retained Context")
        parent = self.partition.directory
        target = parent / str(ship)
        if not target.resolve().is_relative_to(parent):
            raise ValueError("Context Archive escapes its Workflow partition")
        return target

    def subject_archive(self, subject: ContextSubject) -> ArchiveFolder | None:
        """Open and verify an existing subject Archive; absence is not an error."""

        ship = _subject_ship(subject)
        if ship is None:
            return None
        root = self.directory(subject)
        if not root.exists() and not root.is_symlink():
            return None
        archive = self._records().load(root, expected_type=ArchiveFolder)
        binding = self._records().load(
            root / "context.json", expected_type=SubjectContextRoot
        )
        if binding.subject != ship or binding.archive != archive.id:
            raise ValueError("Context Archive subject does not match its placement")
        return archive

    def create_subject_archive(
        self, subject: ContextSubject, *, constitution: str
    ) -> ArchiveFolder:
        """Explicitly create a subject's retained Context root."""

        ship = _subject_ship(subject)
        if ship is None:
            raise TypeError("Only identified subjects have retained Context")
        archive = self.partition.create_dictionary(str(ship), constitution=constitution)
        atomic_write_json(
            archive.root / "context.json",
            SubjectContextRoot(ship, archive.id).to_record(),
        )
        return archive

    def put(
        self,
        subject: ContextSubject,
        name: str,
        cargo: TaravObject,
        *,
        description: str | None = None,
    ) -> ContextEntry:
        """Retain one named Context wrapper around a selected cargo Record."""

        archive = self.subject_archive(subject)
        if archive is None:
            raise FileNotFoundError("Create the subject Context Archive first")
        return self.write(archive, name, cargo, description=description)

    def put_folder(
        self,
        subject: ContextSubject,
        name: str,
        archive_type: type[ArchiveFolder] | type[ArchiveList],
        *,
        constitution: str,
        description: str | None = None,
    ) -> ContextEntry:
        """Create a named folder beneath an identified subject's Context root."""

        archive = self.subject_archive(subject)
        if archive is None:
            raise FileNotFoundError("Create the subject Context Archive first")
        return self.create_folder(
            archive,
            name,
            archive_type,
            constitution=constitution,
            description=description,
            subject=subject,
        )

    def write(
        self,
        archive: ArchiveFolder | ArchiveList,
        placement: str | int | None,
        cargo: TaravObject,
        *,
        description: str | None = None,
    ) -> ContextEntry:
        """Wrap selected cargo in Context semantics at one Archive placement."""

        if isinstance(cargo, Context):
            raise TypeError("Create Context folders with create_folder()")
        wrapper = ContextEntry(cargo=cargo, description=description)
        if isinstance(archive, ArchiveFolder):
            if not isinstance(placement, str):
                raise TypeError("Dictionary Context placement must be a name")
            backing = archive.put(placement, wrapper)
        elif isinstance(archive, ArchiveList):
            if placement is None:
                backing = archive.append(wrapper)
            elif isinstance(placement, int) and not isinstance(placement, bool):
                backing = archive.insert(placement, wrapper)
            else:
                raise TypeError("Vector Context placement must be an index or None")
        else:
            raise TypeError("Context writer requires a Dictionary or Vector Archive")
        return ContextEntry(
            backing.placement,
            opener=lambda: self._open_stored_entry(backing),
            backing=backing,
            description=description,
        )

    def create_folder(
        self,
        archive: ArchiveFolder | ArchiveList,
        placement: str | int | None,
        archive_type: type[ArchiveFolder] | type[ArchiveList],
        *,
        constitution: str,
        description: str | None = None,
        subject: ContextSubject | None = None,
    ) -> ContextEntry:
        """Create a retained folder with its own Context attachment Record."""

        if isinstance(archive, ArchiveFolder):
            if not isinstance(placement, str):
                raise TypeError("Dictionary Context placement must be a name")
            backing = archive.put_archive(
                placement, archive_type, constitution=constitution
            )
        elif isinstance(archive, ArchiveList):
            if placement is None:
                backing = archive.append_archive(
                    archive_type, constitution=constitution
                )
            elif isinstance(placement, int) and not isinstance(placement, bool):
                backing = archive.insert_archive(
                    placement, archive_type, constitution=constitution
                )
            else:
                raise TypeError("Vector Context placement must be an index or None")
        else:
            raise TypeError("Context writer requires a Dictionary or Vector Archive")
        child = backing.open()
        if not isinstance(child, ArchiveEntity):
            raise TypeError("Context folder must be backed by a typed Archive")
        if isinstance(child, ArchiveFolder):
            folder: StoredDictionaryContext | StoredVectorContext = (
                StoredDictionaryContext(child.id, subject)
            )
        elif isinstance(child, ArchiveList):
            folder = StoredVectorContext(child.id, subject)
        else:
            raise TypeError("Context folder requires a Dictionary or Vector Archive")
        # The Archive owns the directory; Context owns this path's attachment.
        atomic_write_json(
            child.root / "context.json",
            ContextEntry(cargo=folder, description=description).to_record(),
        )
        return ContextEntry(
            backing.placement,
            opener=lambda: self._open_entry(
                subject if subject is not None else child, backing
            ),
            backing=backing,
            description=description,
        )

    @staticmethod
    def _open_stored_entry(backing: ArchiveEntry) -> TaravObject:
        retained = backing.open()
        if not isinstance(retained, ContextEntry):
            raise TypeError("Archive entry does not contain a ContextEntry")
        return retained.open()

    def contribute(self, subject: ContextSubject, builder: ContextBuilder) -> None:
        """Mount retained entries after Type or object runtime contributions."""

        archive = self.subject_archive(subject)
        if archive is not None:
            self._populate(subject, archive, builder)

    def _populate(
        self,
        subject: ContextSubject,
        archive: ArchiveFolder | ArchiveList,
        builder: ContextBuilder,
    ) -> None:
        for listed in archive.ls():
            entry = archive.get(listed.placement)
            placement = entry.placement
            if placement is None:
                raise ValueError("Archive entry has no Context placement")
            attachment = self._folder_attachment(entry) if entry.directory else None
            builder.add(
                placement,
                opener=lambda entry=entry: self._open_entry(subject, entry),
                backing=entry,
                description=attachment.description if attachment is not None else None,
            )

    def _folder_attachment(self, entry: ArchiveEntry) -> ContextEntry:
        if not entry.directory:
            raise NotADirectoryError(entry.name)
        return self._records().load(
            entry.artifact_location() / "context.json", expected_type=ContextEntry
        )

    def _open_entry(self, subject: ContextSubject, entry: ArchiveEntry) -> TaravObject:
        target = self._records().load(entry.artifact_location())
        if entry.directory:
            attachment = self._folder_attachment(entry)
            folder = attachment.open()
            if isinstance(target, ArchiveFolder) and isinstance(
                folder, StoredDictionaryContext
            ):
                if folder.archive != target.id:
                    raise ValueError("Context folder Archive Ship does not match")
                folder.subject = subject
                return folder
            if isinstance(target, ArchiveList) and isinstance(
                folder, StoredVectorContext
            ):
                if folder.archive != target.id:
                    raise ValueError("Context folder Archive Ship does not match")
                folder.subject = subject
                return folder
            raise TypeError("Context folder attachment does not match its Archive")
        if not isinstance(target, ContextEntry):
            raise TypeError("Context Archive leaf must contain a ContextEntry")
        return target.open()

    def _records(self) -> TypeRegistry[TaravObject]:
        if self.records is not None:
            return self.records
        return current_records()


_context_service_provider: Callable[[], ContextService] | None = None


def configure_current_context_service(provider: Callable[[], ContextService]) -> None:
    global _context_service_provider
    _context_service_provider = provider


def current_context_service() -> ContextService:
    if _context_service_provider is None:
        raise RuntimeError("Current Context service has not been configured")
    return _context_service_provider()


CONTEXT_RECORD_TYPES = (
    ContextObject,
    ContextEntry,
    SubjectContextRoot,
    StoredDictionaryContext,
    StoredVectorContext,
)


__all__ = [
    "ContextService",
    "CONTEXT_RECORD_TYPES",
    "CONTEXT_WORKFLOW_SHIP",
    "SubjectContextRoot",
    "StoredDictionaryContext",
    "StoredVectorContext",
]
