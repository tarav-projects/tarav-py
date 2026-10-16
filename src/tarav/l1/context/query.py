"""Find what an identifier identifies, then open its Context.

A caller that already holds an object calls ``obj.context()``. A caller that
only has an identifier builds a query; resolvers find the subject. The CLI
is one adapter over this service.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from tarav.l0.kernel import TaravClass, TaravType, TypeShip, entity
from tarav.l1.search import SearchEngine, SearchHit, SearchQuery, SearchService

from . import CONTEXT_WORKFLOW_SHIP


# tarav.breadcrumb d128fb8aa9f239546a23d18b6e3f7eb3520bc13a1b888977dacf0f64a4c0f489
class ContextQuery(SearchQuery):
    """A request to find the subject of a Context."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("0d6a3d0e-2c5d-4f43-a0f5-5d3b6a0f7c11"),
                          name="Tarav.Context.Query", workflow=CONTEXT_WORKFLOW_SHIP)


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

    subject: TaravType | type[TaravType]
    identifier: str
    label: str = ""


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
    """The resolvers that find what an identifier identifies."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8e2b9d15-3f6c-4a18-b7e4-6c9a1d0e2f84"),
                          name="Tarav.Context.QueryService", workflow=CONTEXT_WORKFLOW_SHIP)

    def __init__(self) -> None:
        self.resolvers = SearchService()

    def register_resolver(self, name: str, resolver: SearchEngine) -> None:
        self.resolvers.register(name, resolver)

    def resolve(self, query: ContextQuery) -> tuple[tuple[str, ContextCandidate], ...]:
        found: dict[tuple[int, str], tuple[str, ContextCandidate]] = {}
        for hit in self.resolvers.search.run(query).hits:
            candidate = hit.value
            if isinstance(candidate, ContextCandidate):
                found.setdefault((id(type(candidate.subject)), candidate.identifier),
                                 ("/".join(hit.engines), candidate))
        return tuple(found.values())

    def find(self, identifier: str) -> TaravType | type[TaravType]:
        """The one subject an identifier identifies; KeyError for none or several."""
        candidates = self.resolve(IdentityContextQuery(identifier))
        if len(candidates) != 1:
            raise KeyError(f"{len(candidates)} things match {identifier!r}")
        return candidates[0][1].subject


__all__ = [
    "ContextCandidate",
    "ContextQuery",
    "ContextQueryService",
    "IdentityContextQuery",
    "TypeResolver",
]
