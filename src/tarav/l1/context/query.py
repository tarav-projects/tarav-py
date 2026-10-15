"""Typed Context queries: find a subject, then open its Context.

Scripts that already hold an object call `.context`. A caller that only has
an identifier builds a query; resolvers find the subject and the same
`explore()` opens it. The CLI is one adapter over this service.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from functools import partial

from tarav.l0.kernel import TaravClass, TaravObject, TaravType, TypeShip, entity
from tarav.l1.search import SearchEngine, SearchHit, SearchQuery, SearchService

from . import (
    CONTEXT_WORKFLOW_SHIP, ContextViewEntry, ContextSubject,
    UnsupportedContextView, ViewSelection, explore,
)


# tarav.breadcrumb d128fb8aa9f239546a23d18b6e3f7eb3520bc13a1b888977dacf0f64a4c0f489
class ContextQuery(SearchQuery):
    """A request for Context: which view is wanted and where to go inside it."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("0d6a3d0e-2c5d-4f43-a0f5-5d3b6a0f7c11"),
                          name="Tarav.Context.Query", workflow=CONTEXT_WORKFLOW_SHIP)

    # tarav.context 473c89a0:4c4bb8bf8f117d07
    def __init__(self, *, views: Iterable[str] = (), path: Iterable[str] = (),
                 max_hits: int | None = None, engines: Iterable[str] | None = None) -> None:
        super().__init__(max_hits=max_hits, engines=engines)
        if isinstance(views, str):
            raise TypeError("views must be an iterable of names")
        self.views = tuple(views)
        if any(not isinstance(view, str) or not view for view in self.views):
            raise ValueError("view names must be nonempty strings")
        if isinstance(path, str):
            raise TypeError("path must be an iterable of entry names")
        self.path = tuple(path)
        if any(not isinstance(part, str) or not part for part in self.path):
            raise ValueError("path entries must be nonempty names")


class IdentityContextQuery(ContextQuery):
    """The default query: this identifier is the identity of something."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("5b0c2f4e-9a43-4b63-8d1e-3f1d2c7a9e52"),
                          name="Tarav.Context.Query.Identity", workflow=CONTEXT_WORKFLOW_SHIP)

    def __init__(self, identifier: str, **options) -> None:
        super().__init__(**options)
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("identifier must be nonempty text")
        self.identifier = identifier.strip()


@dataclass(frozen=True, slots=True)
class ContextCandidate:
    """One subject a resolver offers for a query."""

    subject: ContextSubject
    identifier: str
    label: str = ""


@dataclass(frozen=True, slots=True)
class ContextAnswer:
    """What a query found: no candidate, several, or one opened Context."""

    candidates: tuple[tuple[str, ContextCandidate], ...]
    subject: ContextSubject | None = None
    target: object = None
    location: tuple[str, ...] = ()
    views: tuple[str, ...] = ()


class TypeResolver(SearchEngine):
    """Resolve a Tarav Type by its exact name or by a prefix of its Ship."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("c1a4f0b7-7b2e-4d0a-9d36-0a8f5e4b6d73"),
                          name="Tarav.Context.TypeResolver", workflow=CONTEXT_WORKFLOW_SHIP)

    def __init__(self, types: Callable[[], Iterable[type[TaravType]]]) -> None:
        self._types = types

    class Search(SearchEngine.Search):
        def accepts(self, query: SearchQuery) -> bool:
            return isinstance(query, IdentityContextQuery)

        def _iter_hits(self, query: IdentityContextQuery) -> Iterator[SearchHit]:
            wanted = query.identifier
            for candidate in self.obj._types():
                described = entity(candidate)
                ship = str(described.id)
                if described.name == wanted or (len(wanted) >= 8 and ship.startswith(wanted)):
                    yield SearchHit(ContextCandidate(candidate, ship, described.name))


class ContextQueryService(TaravType):
    """Resolvers and named views behind one `open()`."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8e2b9d15-3f6c-4a18-b7e4-6c9a1d0e2f84"),
                          name="Tarav.Context.QueryService", workflow=CONTEXT_WORKFLOW_SHIP)

    def __init__(
        self, *, opener: Callable[..., object] = explore,
        views: dict[str, ViewSelection] | None = None,
    ) -> None:
        self.resolvers = SearchService()
        self.views = views if views is not None else {}
        self._open = (
            partial(explore, view_contributors=(self.contribute_views,))
            if opener is explore else opener
        )

    def contribute_views(self, subject, builder) -> None:
        for name, view in self.views.items():
            builder.add_view(name, views=(view,))

    def register_resolver(self, name: str, resolver: SearchEngine) -> None:
        self.resolvers.register(name, resolver)

    # tarav.breadcrumb 0c6ec926fa98b0a8fa6aac3808baabcf0b8a5fc01764dc8236ab316a4d733583
    def register_view(self, name: str, view: ViewSelection) -> None:
        ContextViewEntry(name, views=(view,))
        if name in self.views:
            raise ValueError(f"View already registered: {name}")
        self.views[name] = view

    def views_for(self, subject: ContextSubject, *, views: Iterable[str] = ()) -> tuple[str, ...]:
        """Next supported views, without opening their values or their factories."""
        current = self._open(subject, views=tuple(self.views[name] for name in views))
        return tuple(name for name, view in self.views.items()
                     if view.accepts(current.context_scope))

    def resolve(self, query: ContextQuery) -> tuple[tuple[str, ContextCandidate], ...]:
        found: dict[tuple[int, str], tuple[str, ContextCandidate]] = {}
        for hit in self.resolvers.search.run(query).hits:
            candidate = hit.value
            if isinstance(candidate, ContextCandidate):
                found.setdefault((id(type(candidate.subject)), candidate.identifier),
                                 ("/".join(hit.engines), candidate))
        return tuple(found.values())

    def open(self, query: ContextQuery) -> ContextAnswer:
        """Resolve, open the requested view, and walk the query's path."""
        for name in query.views:
            if name in self.views:
                continue
            known = ", ".join(sorted(self.views)) or "none"
            raise KeyError(f"Unknown context view: {name} (known: {known})")
        candidates = self.resolve(query)
        selectors = tuple(self.views[name] for name in query.views)
        if selectors and len(candidates) > 1:
            supported = []
            for found in candidates:
                try:
                    self._open(found[1].subject, views=selectors)
                except UnsupportedContextView:
                    continue
                supported.append(found)
            supported = tuple(supported)
            candidates = supported or candidates
        if len(candidates) != 1:
            return ContextAnswer(candidates)
        subject = candidates[0][1].subject
        target: object = self._open(subject, views=selectors)
        walked: list[str] = []
        for index, part in enumerate(query.path):
            if not hasattr(target, "get"):
                raise KeyError(f"/{'/'.join(walked)} has no entries to follow")
            try:
                entry = target.get(part)
            except (KeyError, TypeError, IndexError) as exc:
                raise KeyError(f"No entry {part!r} at /{'/'.join(walked)}") from exc
            target = entry.open()
            walked.append(part)
            if isinstance(target, TaravObject) and not hasattr(target, "ls") \
                    and index < len(query.path) - 1:
                target = self._open(target)
        scope = getattr(target, "context_scope", None)
        available = (
            tuple(name for name, view in self.views.items() if view.accepts(scope))
            if scope is not None else ()
        )
        return ContextAnswer(candidates, subject, target, tuple(walked), available)


__all__ = [
    "ContextAnswer",
    "ContextCandidate",
    "ContextQuery",
    "ContextQueryService",
    "IdentityContextQuery",
    "TypeResolver",
]
