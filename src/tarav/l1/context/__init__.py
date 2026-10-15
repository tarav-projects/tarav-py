"""Read-only Context directories and explorer-bound navigation entries."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from copy import copy
from dataclasses import dataclass
from types import MethodType
from typing import ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict

from tarav.l0.kernel.identity import TypeShip, WorkflowShip
from tarav.l0.kernel.explorer import Explorer, ExplorerEntry, ExplorerFolder, ExplorerList
from tarav.l0.kernel.records import TaravClass, TaravEntity, TaravObject, TaravType, entity


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


class UnsupportedContextView(TypeError):
    """A requested view does not support this subject and accumulated context."""


# tarav.context 473c89a0:926997d41da95b26
@dataclass(frozen=True)
class ContextScope(ContextType):
    """A subject under ordered, active contextualization qualifications."""

    subject: ContextSubject
    views: tuple[type[ContextView] | ContextViewRequest, ...] = ()

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("a4f5ac66-b982-49df-bd5b-1f0b95ca986a"),
            name="Tarav.Context.Scope", workflow=CONTEXT_WORKFLOW_SHIP,
        )


class ContextViewRequest(ContextObject):
    """A parameterized request declaring accepts(scope) and apply(current).

    Request subclasses own their parameter schemas and compatibility rules.
    The dispatcher attaches the resulting cumulative scope centrally.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("becb8f0a-4cea-47b6-85f6-13fd9bc3ace9"),
            name="Tarav.Context.ViewRequest", workflow=CONTEXT_WORKFLOW_SHIP,
        )

    def apply(self, current: ContextView) -> ContextView:
        raise UnsupportedContextView(f"Unsupported view request: {type(self).__name__}")

    def accepts(self, scope: ContextScope) -> bool:
        """Declare compatibility without opening a view or any of its values."""
        return False


def _same_subject(left: ContextSubject, right: ContextSubject) -> bool:
    return left is right or (
        isinstance(left, TaravEntity) and isinstance(right, TaravEntity)
        and left.id == right.id
    )


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
            cargo.records.to_record()
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
        self._context_view: ContextView | None = None

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
                return retained.records.to_record()
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
        parent = self._context_view
        if isinstance(value, ContextView) and parent is not None:
            if _same_subject(value.subject, parent.subject):
                current = parent.context_scope.views
                selected = value.context_scope.views
                if not selected:
                    value = value._with_scope(parent.context_scope)
                elif selected[:len(current)] != current:
                    raise UnsupportedContextView("Opened view drops active qualifications")
            value = value._with_scope(
                value.context_scope, view_contributors=parent._view_contributors
            )
        return value

    def _for_view(self, view: ContextView) -> ContextEntry:
        entry = copy(self)
        entry._context_view = view
        entry.explorer = None
        entry._origin = None
        entry._origin_history = ()
        return entry

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

    __slots__ = ("subject", "context_scope", "placement_type", "_entries", "_names")

    def __init__(
        self, subject: ContextSubject, *, placement_type: type[str] | type[int] = str,
        scope: ContextScope | None = None,
    ) -> None:
        self.subject = subject
        self.context_scope = scope or ContextScope(subject)
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
        if isinstance(entry, ContextViewEntry) and not entry.accepts(self.context_scope):
            return
        if entry.name in self._names:
            raise ValueError(f"Duplicate Context entry: {entry.name}")
        self._names.add(entry.name)
        self._entries.append(entry)

    def add_view(
        self, placement: str | int, *, views: Iterable[ViewSelection],
        description: str | None = None,
    ) -> None:
        """Advertise a step using the same derivation as direct view selection."""
        self.add_entry(ContextViewEntry(placement, views=views, description=description))

    def entries(self) -> tuple[ContextEntry, ...]:
        return tuple(self._entries)


class ContextView(ContextObject):
    """A read-only contextualized folder; navigation belongs to the explorer.

    Static view Types declare accepts(scope) and for_context(current). Each
    derivation receives the preceding view and retains earlier qualifications.
    The ontology Ship and Record label remain those of the original Context.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("234f19ba-18bd-4700-a5fb-3d2631d0a348"),
            name="Tarav.Context",
            workflow=CONTEXT_WORKFLOW_SHIP,
        )

    __slots__ = ("subject", "context_scope", "_view_contributors", "_populator", "_entries")
    placement_type: ClassVar[type[str] | type[int]] = str

    @classmethod
    def for_context(cls, current: ContextView) -> ContextView:
        """Specializations explicitly interpret the accumulated input context."""
        raise UnsupportedContextView(f"Unsupported Context view: {cls.__name__}")

    @classmethod
    def accepts(cls, scope: ContextScope) -> bool:
        """Specializations explicitly declare supported cumulative contexts."""
        return False

    def __init__(self, subject: ContextSubject, populator: ContextPopulator) -> None:
        super().__init__()
        self.subject = subject
        self.context_scope = ContextScope(subject)
        self._view_contributors: tuple[ContextContributor, ...] = ()
        self._populator = populator
        self._entries: tuple[ContextEntry, ...] | None = None

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls(cls, lambda builder: None)

    def ls(self) -> tuple[ContextEntry, ...]:
        if self._entries is None:
            builder = ContextBuilder(
                self.subject, placement_type=self.placement_type, scope=self.context_scope
            )
            self._populator(builder)
            for contribute in self._view_contributors:
                contribute(self.subject, builder)
            self._entries = tuple(entry._for_view(self) for entry in builder.entries())
        return self._entries

    def _with_scope(
        self, scope: ContextScope, *,
        view_contributors: tuple[ContextContributor, ...] | None = None,
    ) -> ContextView:
        """Bind a view without sharing scope or cached entries between routes."""
        result = copy(self)
        result.subject = scope.subject
        result.context_scope = scope
        if view_contributors is not None:
            result._view_contributors = view_contributors
        result._entries = None
        if isinstance(self._populator, MethodType) and self._populator.__self__ is self:
            result._populator = self._populator.__func__.__get__(result)
        return result

    def refine(self, *, views: Iterable[ViewSelection]) -> ContextView:
        """Apply ordered views while keeping every earlier qualification."""
        current = self
        for selector in _view_selections(views):
            if not selector.accepts(current.context_scope):
                label = selector.__name__ if isinstance(selector, type) else type(selector).__name__
                raise UnsupportedContextView(f"{label} does not support the current ContextScope")
            value = (
                selector.for_context(current) if isinstance(selector, type)
                else selector.apply(current)
            )
            if not isinstance(value, ContextView) or value is current:
                raise TypeError("A contextualization must return a new ContextView")
            if isinstance(selector, type) and not isinstance(value, selector):
                raise TypeError("View factory returned an incompatible ContextView Type")
            if not _same_subject(value.subject, current.subject):
                raise UnsupportedContextView("A view cannot silently change its subject")
            selected_scope = (*current.context_scope.views, selector)
            if value.context_scope.views not in ((), current.context_scope.views, selected_scope):
                raise UnsupportedContextView("View factory returned unrelated qualifications")
            scope = ContextScope(current.subject, selected_scope)
            current = value._with_scope(scope, view_contributors=current._view_contributors)
        return current

    def get(self, name: str | int) -> ContextEntry:
        if type(name) is not self.placement_type:
            raise TypeError(f"Context key must be {self.placement_type.__name__}")
        for entry in self.ls():
            if entry.name == str(name):
                return entry
        raise KeyError(name)

    def open(self, name: str | int) -> TaravObject:
        return self.get(name).open()


class ContextFolder(ContextView, ExplorerFolder):
    """Named Context directory, including an identified subject's root."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("9e669284-3799-4c9b-b320-cd71f5c86be6"),
            name="Tarav.Context.Folder",
        )


class ContextList(ContextView, ExplorerList):
    """Positional Context directory whose indexes are not identities."""

    placement_type: ClassVar[type[str] | type[int]] = int

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("b41f1e67-71b3-4740-b9ba-5bb56b3429cb"),
            name="Tarav.Context.List",
        )


ViewSelection = type[ContextView] | ContextViewRequest


def _view_selections(views: Iterable[ViewSelection]) -> tuple[ViewSelection, ...]:
    if isinstance(views, (str, bytes, type, ContextViewRequest)):
        raise TypeError("views must be an iterable of view classes or typed requests")
    selected = tuple(views)
    if any(not (
        isinstance(view, type) and issubclass(view, ContextView)
        or isinstance(view, ContextViewRequest)
    ) for view in selected):
        raise TypeError("Each view must be a ContextView class or ContextViewRequest")
    return selected


# tarav.context 473c89a0:9b167562b00b0279
class ContextViewEntry(ContextEntry):
    """A computed step that extends the containing view's contextualization."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls, id=TypeShip("da11f81f-41cc-4cdd-8f61-e317727b2d99"),
            name="Tarav.Context.ViewEntry", workflow=CONTEXT_WORKFLOW_SHIP,
        )

    def __init__(
        self, placement: str | int, *, views: Iterable[ViewSelection],
        description: str | None = None,
    ) -> None:
        super().__init__(placement, description=description)
        self.views = _view_selections(views)
        if not self.views:
            raise ValueError("A view entry must declare a contextualization")

    def open(self) -> ContextView:
        if self._context_view is None:
            raise ValueError("View entry is not bound to a containing ContextView")
        if not self.accepts(self._context_view.context_scope):
            raise UnsupportedContextView("View entry does not support the current ContextScope")
        return self._context_view.refine(views=self.views)

    def accepts(self, scope: ContextScope) -> bool:
        """Check the whole proposed step without running any view factory."""
        for selector in self.views:
            if not selector.accepts(scope):
                return False
            scope = ContextScope(scope.subject, (*scope.views, selector))
        return True

    @property
    def context_scope(self) -> ContextScope:
        if self._context_view is None:
            raise ValueError("View entry is not bound to a containing ContextView")
        return self._context_view.context_scope

    def _to_record(self):
        raise TypeError("Computed view steps have no retained request schema")


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
        open_subject: Callable[[ContextSubject], ContextView],
    ) -> None:
        if not isinstance(root, ContextObject):
            raise TypeError("Context explorer root must be a ContextObject")
        super().__init__(ContextLocation(root, ()))
        self.root = root
        self._open_subject = open_subject

    @property
    def subject(self) -> ContextSubject:
        return self.current.folder.subject

    @property
    def context_scope(self) -> ContextScope:
        return self.current.folder.context_scope

    def refine(self, *, views: Iterable[ViewSelection]) -> ContextView:
        return self.current.folder.refine(views=views)

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
        if isinstance(target, ContextView):
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
    view_contributors: Iterable[ContextContributor] = (),
    views: Iterable[ViewSelection] = (),
) -> ContextExplorer | ContextView:
    """Start a new exploration, or continue through an explorer-bound entry."""

    selected = _view_selections(views)
    if isinstance(subject, ContextEntry):
        if subject.explorer is None:
            raise ValueError("Context entry is not bound to an explorer")
        explorer = subject.explorer.follow(subject)
        return explorer.refine(views=selected) if selected else explorer
    contributions = tuple(contributors)
    next_steps = tuple(view_contributors)

    def open_subject(subject):
        root = _view(subject, contributors=contributions)
        root._view_contributors = next_steps
        return root

    root = open_subject(subject)
    if selected:
        return root.refine(views=selected)
    return ContextExplorer(
        root,
        open_subject,
    )
