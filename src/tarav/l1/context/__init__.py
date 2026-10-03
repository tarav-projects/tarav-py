"""Read-only Context directories and explorer-bound navigation entries."""

from __future__ import annotations

import builtins

from collections.abc import Callable, Iterable, Mapping
from copy import copy
from dataclasses import dataclass
from typing import ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict

from tarav.l0.kernel.identity import TypeShip, WorkflowShip
from tarav.l0.kernel.explorer import Explorer, ExplorerEntry, ExplorerFolder, ExplorerList
from tarav.l0.kernel.records import TaravClass, TaravObject, TaravType, entity


CONTEXT_WORKFLOW_SHIP = WorkflowShip("ae6fb02b-b82f-4f64-82e8-67f28a76d179")


class ContextType(TaravType):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("23a0bf64-9212-49ea-8bbb-7e8f47bb8189"),
            name="Tarav.Context.Type",
            workflow=CONTEXT_WORKFLOW_SHIP,
        )


class ContextObject(TaravObject, ContextType):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("f9ce7e42-be5c-4a8c-927c-4da193b9a2e7"),
            name="Tarav.Context.Object",
            workflow=CONTEXT_WORKFLOW_SHIP,
        )


ContextSubject = type[TaravType] | TaravObject
ContextPopulator = Callable[["ContextBuilder"], None]
ContextContributor = Callable[[ContextSubject, "ContextBuilder"], None]


@dataclass(frozen=True)
class ContextLocation:
    folder: ContextObject
    parts: tuple[str, ...]
    parent: ContextLocation | None = None


class ContextEntry(ExplorerEntry, ContextObject):
    """Context-owned wrapper around one lazily opened cargo object."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("473b6a26-a397-4aa4-97fe-8b81af6ca603"),
            name="Tarav.Context.Entry",
            workflow=CONTEXT_WORKFLOW_SHIP,
        )

    class RecordInterface(ExplorerEntry.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: Literal["Tarav.Context.Entry"]
        cargo: dict[str, object] | None = None
        description: str | None = None

    def __init__(
        self,
        placement: str | int | None = None,
        opener: Callable[[], TaravObject] | None = None,
        *,
        cargo: Mapping[str, object] | TaravObject | None = None,
        description: str | None = None,
        backing: TaravObject | None = None,
    ) -> None:
        super().__init__()
        if isinstance(placement, str):
            if (
                not placement
                or placement in {".", ".."}
                or any(separator in placement for separator in ("/", "\\"))
            ):
                raise ValueError("Context entry name must be one ordinary path segment")
        elif placement is not None and (
            not isinstance(placement, int)
            or isinstance(placement, bool)
            or placement < 0
        ):
            raise ValueError("Context entry position must be a non-negative integer")
        if opener is not None and not callable(opener):
            raise TypeError("Context entry opener must be callable")
        if backing is not None and not isinstance(backing, TaravObject):
            raise TypeError("Context entry backing must be a TaravObject")
        if description is not None and not isinstance(description, str):
            raise TypeError("Context entry description must be a string")
        self.placement = placement
        self.backing = backing
        self._opener = opener
        self._cargo = (
            cargo.to_record()
            if isinstance(cargo, TaravObject)
            else dict(cargo)
            if cargo is not None
            else None
        )
        self._cargo_object = cargo if isinstance(cargo, TaravObject) else None
        self._cargo_loader: Callable[[object], TaravObject] | None = None
        self._description = description
        self.explorer: ContextExplorer | None = None
        self._origin: ContextLocation | None = None
        self._origin_history: tuple[ContextLocation, ...] = ()

    @property
    def name(self) -> str:
        if self.placement is None:
            raise ValueError("Unbound Context entry has no placement")
        return str(self.placement)

    @property
    def description(self) -> str | None:
        if self._description is None and self.backing is not None:
            retained = self.backing.open()
            if isinstance(retained, ContextEntry):
                self._description = retained.description
        return self._description

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls(
            cargo=record_data.cargo,
            description=record_data.description,
        )

    def _to_record(self) -> Mapping[str, object]:
        if self._cargo is None and self.backing is not None:
            retained = self.backing.open()
            if isinstance(retained, ContextEntry):
                return retained.to_record()
        record: dict[str, object] = {"type": entity(type(self)).name}
        if self._cargo is not None:
            record["cargo"] = self._cargo
        if self._description is not None:
            record["description"] = self._description
        return record

    def archive_entry(self) -> TaravObject | None:
        """Return optional Archive backing without requiring it for navigation."""

        return self.backing

    def open(self) -> TaravObject:
        """Open the cargo; Reference cargo remains a Reference."""

        if self._opener is not None:
            value = self._opener()
        elif self._cargo_object is not None:
            value = self._cargo_object
        elif self._cargo is not None:
            if self._cargo_loader is None:
                raise RuntimeError("Context entry cargo needs a trusted Type loader")
            value = self._cargo_loader(self._cargo)
            if self.source is not None and value.source is None:
                value.source = self.source
        else:
            raise ValueError("Context entry has no cargo")
        if not isinstance(value, TaravObject):
            raise TypeError("Context entry opener must return a TaravObject")
        return value

    def _bind_record_loader(self, loader: Callable[[object], TaravObject]) -> None:
        self._cargo_loader = loader

    def _bind(
        self,
        explorer: ContextExplorer,
        origin: ContextLocation,
        history: tuple[ContextLocation, ...],
    ) -> ContextEntry:
        """Give one explorer its own runtime handle for this placement."""

        entry = copy(self)
        entry.explorer = explorer
        entry._origin = origin
        entry._origin_history = history
        return entry


class ContextBuilder(ContextType):
    """Mutable collector passed to Type, object, and retained contributors."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("3f8e52d9-82e5-4df7-b36d-591c9029820a"),
            name="Tarav.Context.Builder",
        )

    __slots__ = ("subject", "placement_type", "_entries", "_names")

    def __init__(
        self, subject: ContextSubject, *, placement_type: type[str] | type[int] = str
    ) -> None:
        self.subject = subject
        self.placement_type = placement_type
        self._entries: list[ContextEntry] = []
        self._names: set[str] = set()

    def add(
        self,
        placement: str | int,
        *,
        opener: Callable[[], TaravObject],
        backing: TaravObject | None = None,
        description: str | None = None,
    ) -> None:
        """Add one entry without resolving its target."""

        if type(placement) is not self.placement_type:
            raise TypeError(f"Context placement must be {self.placement_type.__name__}")
        entry = ContextEntry(
            placement, opener, backing=backing, description=description
        )
        self.add_entry(entry)

    def add_entry(self, entry: ContextEntry) -> None:
        """Add a specialized Context entry without erasing its Type."""

        if type(entry.placement) is not self.placement_type:
            raise TypeError(f"Context placement must be {self.placement_type.__name__}")
        if entry.name in self._names:
            raise ValueError(f"Duplicate Context entry: {entry.name}")
        self._names.add(entry.name)
        self._entries.append(entry)

    def entries(self) -> tuple[ContextEntry, ...]:
        return tuple(self._entries)


class Context(ContextObject):
    """A read-only Context folder; navigation state belongs to the explorer."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("234f19ba-18bd-4700-a5fb-3d2631d0a348"),
            name="Tarav.Context",
            workflow=CONTEXT_WORKFLOW_SHIP,
        )

    __slots__ = ("subject", "_populator", "_entries")
    placement_type: ClassVar[type[str] | type[int]] = str

    @classmethod
    def for_subject(cls, subject):
        """Specializations explicitly declare the subjects they support."""
        raise TypeError(f"Unsupported context type: {cls.__name__}")

    def __init__(self, subject: ContextSubject, populator: ContextPopulator) -> None:
        super().__init__()
        self.subject = subject
        self._populator = populator
        self._entries: tuple[ContextEntry, ...] | None = None

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls(cls, lambda builder: None)

    def ls(self) -> tuple[ContextEntry, ...]:
        if self._entries is None:
            builder = ContextBuilder(self.subject, placement_type=self.placement_type)
            self._populator(builder)
            self._entries = builder.entries()
        return self._entries

    def get(self, name: str | int) -> ContextEntry:
        if type(name) is not self.placement_type:
            raise TypeError(f"Context key must be {self.placement_type.__name__}")
        for entry in self.ls():
            if entry.name == str(name):
                return entry
        raise KeyError(name)

    def open(self, name: str | int) -> TaravObject:
        return self.get(name).open()


class ContextFolder(Context, ExplorerFolder):
    """Named Context directory, including an identified subject's root."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("9e669284-3799-4c9b-b320-cd71f5c86be6"),
            name="Tarav.Context.Folder",
        )


class ContextList(Context, ExplorerList):
    """Positional Context directory whose indexes are not identities."""

    placement_type: ClassVar[type[str] | type[int]] = int

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("b41f1e67-71b3-4740-b9ba-5bb56b3429cb"),
            name="Tarav.Context.List",
        )


class ContextExplorer(Explorer[ContextLocation], ContextType):
    """One navigation session through Context directories and subject jumps."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("258de0ca-9624-475d-a45b-967501ae6055"),
            name="Tarav.Context.Explorer",
            workflow=CONTEXT_WORKFLOW_SHIP,
        )

    def __init__(
        self,
        root: ContextObject,
        open_subject: Callable[[ContextSubject], Context],
    ) -> None:
        if not isinstance(root, ContextObject):
            raise TypeError("Context explorer root must be a ContextObject")
        super().__init__(ContextLocation(root, ()))
        self.root = root
        self._open_subject = open_subject

    @property
    def subject(self) -> ContextSubject:
        return self.current.folder.subject

    def ls(self) -> tuple[ContextEntry, ...]:
        origin = self.current
        history = tuple(self._back_stack)
        entries = self._container(origin.folder).ls()
        if any(not isinstance(entry, ContextEntry) for entry in entries):
            raise TypeError("Context container must expose ContextEntry values")
        return tuple(entry._bind(self, origin, history) for entry in entries)

    def get(self, name: str | int) -> ContextEntry:
        entry = self._select(self.current.folder, name)
        if not isinstance(entry, ContextEntry):
            raise TypeError("Context container must expose ContextEntry values")
        return entry._bind(self, self.current, tuple(self._back_stack))

    def cd(self, name: str | int) -> ContextExplorer:
        if name == "/":
            root = self.current
            while root.parent is not None:
                root = root.parent
            if root is not self.current:
                self._visit(root)
            return self
        if name == ".":
            return self
        if name == "..":
            if self.current.parent is not None:
                self._visit(self.current.parent)
            return self
        entry = self.get(name)
        target = entry.open()
        self._container(target)
        if not isinstance(target, ContextObject):
            raise TypeError("Context destination must be a ContextObject")
        self._visit(
            ContextLocation(target, (*self.current.parts, entry.name), self.current)
        )
        return self

    def follow(self, entry: ContextEntry) -> ContextExplorer:
        """Enter an entry's cargo context and preserve its exact origin."""

        if entry.explorer is not self or entry._origin is None:
            raise ValueError("Context entry belongs to another explorer")
        target = entry.open()
        if isinstance(target, Context):
            next_location = ContextLocation(
                target,
                (*entry._origin.parts, entry.name),
                entry._origin,
            )
        else:
            next_location = ContextLocation(self._open_subject(target), ())
        self._container(next_location.folder)
        if not isinstance(next_location.folder, ContextObject):
            raise TypeError("Context destination must be a ContextObject")
        self._resume(entry._origin, entry._origin_history)
        self._visit(next_location)
        return self

    def pwd(self) -> str:
        return "/" + "/".join(self.current.parts)


def _view(
    subject: ContextSubject,
    *,
    contributors: tuple[ContextContributor, ...],
) -> ContextFolder:
    if isinstance(subject, type) and issubclass(subject, TaravType):

        def populate_class(builder: ContextBuilder) -> None:
            builder.add("entity", opener=lambda: entity(subject))
            subject.class_context(builder)
            for contribute in contributors:
                contribute(subject, builder)

        return ContextFolder(subject, populate_class)

    if isinstance(subject, TaravObject):

        def populate_object(builder: ContextBuilder) -> None:
            builder.add(
                "class",
                opener=lambda: _view(type(subject), contributors=contributors),
            )
            subject.obj_context(builder)
            if isinstance(subject, TaravClass):
                def populate_bases(bases_builder: ContextBuilder) -> None:
                    for index, base in enumerate(subject.bases()):
                        bases_builder.add(index, opener=lambda base=base: base)

                builder.add("bases", opener=lambda: ContextList(subject, populate_bases))
                builder.add(
                    "target",
                    opener=lambda: _view(subject.target, contributors=contributors),
                )
            for contribute in contributors:
                contribute(subject, builder)

        return ContextFolder(subject, populate_object)

    raise TypeError("context subject must be a TaravType class or TaravObject")


def explore(
    subject: ContextSubject | ContextEntry,
    *,
    contributors: Iterable[ContextContributor] = (),
    type: builtins.type[Context] | None = None,
) -> ContextExplorer | Context:
    """Start a new exploration, or continue through an explorer-bound entry."""

    if type is not None:
        if not isinstance(type, builtins.type) or not issubclass(type, Context):
            raise TypeError("context type must be a Context subclass")
        view = type.for_subject(subject)
        if not isinstance(view, type):
            raise TypeError("Context factory returned an incompatible view")
        return view
    if isinstance(subject, ContextEntry):
        if subject.explorer is None:
            raise ValueError("Context entry is not bound to an explorer")
        return subject.explorer.follow(subject)
    contributions = tuple(contributors)
    return ContextExplorer(
        _view(subject, contributors=contributions),
        lambda target: _view(target, contributors=contributions),
    )
