"""Archive-backed retained Context for identified Tarav subjects."""

from __future__ import annotations

from collections.abc import Callable
from copy import copy
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from tarav.l0._core.data_root import default_tarav_data_root
from tarav.l0._core.persistence import atomic_write_json
from tarav.l0.kernel.current import current_records
from tarav.l1.context import (
    CONTEXT_WORKFLOW_SHIP,
    ContextView,
    ContextBuilder,
    ContextEntry,
    ContextObject,
    ContextSubject,
    ContextFolder,
    ContextList,
    ContextScope,
    ContextViewEntry,
    ViewSelection,
)
from tarav.l0.kernel.identity import Ship, TypeShip
from tarav.l0.kernel.records import TaravClass, TaravEntity, TaravObject, TaravType, entity
from tarav.l0.kernel.types import TypeRegistry
from tarav.l1.context.models import ModelProvider, TypeModel, TypePath
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

    class Records(ContextFolder.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
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

    class Records(ContextList.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
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

    class Records(ContextObject.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
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
        self._model_providers: list[ModelProvider] = []
        self.views: dict[str, ViewSelection] = {}

    def register_view(self, name: str, view: ViewSelection) -> None:
        """Offer a named contextualization through both discovery and queries."""
        ContextViewEntry(name, views=(view,))  # Validate the name and selector once.
        if name in self.views:
            raise ValueError(f"View already registered: {name}")
        self.views[name] = view

    def register_model_provider(self, provider: ModelProvider) -> None:
        """Contribute Type nodes from an external workflow, without copying them."""
        if not callable(provider):
            raise TypeError("Type model provider must be callable")
        if provider not in self._model_providers:
            self._model_providers.append(provider)

    # tarav.context 473c89a0:568b173e6f7d5c24
    def model(self, subject: type[TaravType]) -> TypeModel:
        """Compose class, retained and external nodes lazily without writing."""
        def nodes():
            yield from subject.context.model_nodes()
            archive = self._model_archive(subject)
            if archive is not None:
                for listed in archive.ls():
                    backing = archive.get(listed.placement)
                    node = self._open_stored_entry(backing)
                    if not isinstance(node, TypePath) or str(node.id) != backing.name:
                        raise ValueError("Retained Type model node does not match its Ship key")
                    yield node
            for provider in tuple(self._model_providers):
                yield from provider(subject)

        model = TypeModel(subject, nodes)
        model._view_contributors = (self.contribute_views,)
        return model

    def put_model_node(self, subject: type[TaravType], node: TypePath) -> ContextEntry:
        """Retain a new node under its Ship, preserving Archive's create-only policy."""
        if not isinstance(subject, type) or not issubclass(subject, TaravType):
            raise TypeError("Type models require a TaravType class")
        if not isinstance(node, TypePath):
            raise TypeError("Type model members must be TypePath entities")
        archive = self._model_archive(subject, create=True)
        return self.write(archive, str(node.id), node, description=node.path)

    def _model_archive(
        self, subject: type[TaravType], *, create: bool = False
    ) -> ArchiveFolder | None:
        root = self.subject_archive(subject)
        if root is None:
            if not create:
                return None
            root = self.create_subject_archive(
                subject, constitution="Retained Context for this identified Type."
            )
        try:
            entry = root.get("model")
        except KeyError:
            if not create:
                return None
            self.create_folder(
                root, "model", ArchiveFolder, subject=subject,
                constitution="Type model nodes keyed by Ship; paths are current labels.",
            )
            entry = root.get("model")
        attachment = self._folder_attachment(entry).open()
        archive = self._records().load(entry.artifact_location(), expected_type=ArchiveFolder)
        if not isinstance(attachment, StoredDictionaryContext) or attachment.archive != archive.id:
            raise ValueError("Type model folder does not match its Context attachment")
        return archive

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
            SubjectContextRoot(ship, archive.id).records.to_record(),
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

    # tarav.context 473c89a0:ba32e41d46ab46db
    def put_entry(
        self, subject: ContextSubject, name: str, entry: ContextEntry
    ) -> ContextEntry:
        """Retain a registered typed relationship entry without rewrapping it."""
        archive = self.subject_archive(subject)
        if archive is None:
            raise FileNotFoundError("Create the subject Context Archive first")
        return self.write_entry(archive, name, entry)

    def write(
        self,
        archive: ArchiveFolder | ArchiveList,
        placement: str | int | None,
        cargo: TaravObject,
        *,
        description: str | None = None,
    ) -> ContextEntry:
        """Wrap selected cargo in Context semantics at one Archive placement."""

        if isinstance(cargo, ContextView):
            raise TypeError("Create Context folders with create_folder()")
        return self.write_entry(archive, placement, ContextEntry(cargo=cargo, description=description))

    def write_entry(
        self, archive: ArchiveFolder | ArchiveList, placement: str | int | None,
        entry: ContextEntry,
    ) -> ContextEntry:
        """Write one concrete entry Type using ordinary Archive placement."""
        if not isinstance(entry, ContextEntry):
            raise TypeError("Context writer requires a ContextEntry")
        if isinstance(archive, ArchiveFolder):
            if not isinstance(placement, str):
                raise TypeError("Dictionary Context placement must be a name")
            backing = archive.put(placement, entry)
        elif isinstance(archive, ArchiveList):
            if placement is None:
                backing = archive.append(entry)
            elif isinstance(placement, int) and not isinstance(placement, bool):
                backing = archive.insert(placement, entry)
            else:
                raise TypeError("Vector Context placement must be an index or None")
        else:
            raise TypeError("Context writer requires a Dictionary or Vector Archive")
        result = copy(entry)
        result.placement = backing.placement
        result.backing = backing
        result.source = backing.artifact_location()
        result._bind_record_loader(self._records().from_record)
        return result

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
            ContextEntry(cargo=folder, description=description).records.to_record(),
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

        is_type = isinstance(subject, type) and issubclass(subject, TaravType)
        if is_type:
            builder.add("model", opener=lambda: self.model(subject))
        archive = self.subject_archive(subject)
        if archive is not None:
            self._populate(subject, archive, builder, exclude=("model",) if is_type else ())

    def contribute_views(self, subject: ContextSubject, builder: ContextBuilder) -> None:
        """Offer supported steps on every derived view, preserving its scope."""
        for name, view in self.views.items():
            builder.add_view(name, views=(view,))

    def _populate(
        self,
        subject: ContextSubject,
        archive: ArchiveFolder | ArchiveList,
        builder: ContextBuilder,
        *,
        exclude: tuple[str, ...] = (),
    ) -> None:
        for listed in archive.ls():
            if listed.placement in exclude:
                continue
            entry = archive.get(listed.placement)
            placement = entry.placement
            if placement is None:
                raise ValueError("Archive entry has no Context placement")
            if entry.directory:
                retained = self._folder_attachment(entry)
                handle = copy(retained)
                handle._opener = lambda entry=entry: self._open_entry(subject, entry)
            else:
                retained = self._records().load(entry.artifact_location())
                if not isinstance(retained, ContextEntry):
                    raise TypeError("Context Archive leaf must contain a ContextEntry")
                handle = copy(retained)
            handle.placement = placement
            handle.backing = entry
            builder.add_entry(handle)

    def _folder_attachment(self, entry: ArchiveEntry) -> ContextEntry:
        if not entry.directory:
            raise NotADirectoryError(entry.name)
        attachment = self._records().load(entry.artifact_location() / "context.json")
        if not isinstance(attachment, ContextEntry):
            raise TypeError("Context folder attachment must be a ContextEntry")
        return attachment

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
                return folder._with_scope(ContextScope(subject))
            if isinstance(target, ArchiveList) and isinstance(
                folder, StoredVectorContext
            ):
                if folder.archive != target.id:
                    raise ValueError("Context folder Archive Ship does not match")
                return folder._with_scope(ContextScope(subject))
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
    TypePath,
)


__all__ = [
    "ContextService",
    "CONTEXT_RECORD_TYPES",
    "CONTEXT_WORKFLOW_SHIP",
    "SubjectContextRoot",
    "StoredDictionaryContext",
    "StoredVectorContext",
]
