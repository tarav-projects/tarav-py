"""Typed, incremental search across independently registered engines."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from tarav.l0.kernel import (
    NamespaceBase,
    TaravClass,
    TaravObject,
    TaravType,
    TaravWorkflow,
    TypeShip,
    WorkflowShip,
)


SEARCH_WORKFLOW_SHIP = WorkflowShip("c5f5d32b-b903-469a-a6b5-e6956ae11348")


# tarav.breadcrumb 6cbe95bad425
class SearchQuery(TaravObject):
    """Typed search request with controls for the dispatch that runs it."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("c9717332-b2ce-409a-90eb-f33012055c98"),
            name="Tarav.Search.Query",
            workflow=SEARCH_WORKFLOW_SHIP,
        )

    def __init__(
        self, *, max_hits: int | None = None, engines: Iterable[str] | None = None
    ) -> None:
        super().__init__()
        if max_hits is not None and (
            isinstance(max_hits, bool) or not isinstance(max_hits, int) or max_hits < 1
        ):
            raise ValueError("max_hits must be a positive integer or None")
        if isinstance(engines, str):
            raise TypeError("engines must be an iterable of engine names")
        selected = None if engines is None else frozenset(engines)
        if selected is not None and any(
            not isinstance(name, str) or not name for name in selected
        ):
            raise ValueError("engine names must be nonempty strings")
        self.max_hits = max_hits
        self.engines = selected


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One hit; meta engines prepend their registered name to its route."""

    value: object
    engines: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SearchResult:
    accepted: bool
    hits: tuple[SearchHit, ...]

    @property
    def declined(self) -> bool:
        return not self.accepted


# tarav.breadcrumb 2fc0f3565f4d
class SearchStream(Iterator[SearchHit]):
    """Closable iterator that keeps decline separate from an empty search."""

    def __init__(
        self, accepted: bool, hits: Iterator[SearchHit], *, max_hits: int | None
    ) -> None:
        self.accepted = accepted
        self._hits = hits
        self._remaining = max_hits
        self._closed = False

    @property
    def declined(self) -> bool:
        return not self.accepted

    def __iter__(self) -> SearchStream:
        return self

    def __next__(self) -> SearchHit:
        if self._closed:
            raise StopIteration
        try:
            hit = next(self._hits)
        except StopIteration:
            self.close()
            raise
        except BaseException:
            self.close()
            raise
        if not isinstance(hit, SearchHit):
            self.close()
            raise TypeError("Search engines must yield SearchHit objects")
        if self._remaining is not None:
            self._remaining -= 1
            if self._remaining == 0:
                self.close()
        return hit

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            close = getattr(self._hits, "close", None)
            if close is not None:
                close()


# tarav.breadcrumb b00e7efd22d1
class SearchEngine(TaravType):
    """Capability for a Type that can answer some typed queries."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("fa7d30b2-3e09-4de0-a83e-b99d43c3902e"),
            name="Tarav.Search.Engine",
            workflow=SEARCH_WORKFLOW_SHIP,
        )

    class Search(NamespaceBase["SearchEngine"]):
        def accepts(self, query: SearchQuery) -> bool:
            """Return whether this engine understands the query."""
            raise NotImplementedError

        def _iter_hits(self, query: SearchQuery) -> Iterator[SearchHit]:
            """Produce hits for a query already accepted by this engine."""
            raise NotImplementedError

        def iter_hits(self, query: SearchQuery) -> SearchStream:
            if not isinstance(query, SearchQuery):
                raise TypeError("Search requires a SearchQuery")
            accepted = self.accepts(query)
            if not isinstance(accepted, bool):
                raise TypeError("Search.accepts() must return a bool")
            hits = iter(self._iter_hits(query)) if accepted else iter(())
            return SearchStream(accepted, hits, max_hits=query.max_hits)

        def run(self, query: SearchQuery) -> SearchResult:
            """Collect an incremental search, applying its acceptance gate."""
            stream = self.iter_hits(query)
            try:
                return SearchResult(stream.accepted, tuple(stream))
            finally:
                stream.close()

    @property
    def search(self) -> Search:
        return type(self).Search(self)


# tarav.breadcrumb 87764ef9d098
class SearchService(SearchEngine):
    """A registry-backed meta engine, independent of any one search domain."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("be5ed181-c63d-4408-81bb-288e436bfe07"),
            name="Tarav.Search.Service",
            workflow=SEARCH_WORKFLOW_SHIP,
        )

    def __init__(self) -> None:
        self.engines: dict[str, SearchEngine] = {}

    def register(self, name: str, engine: SearchEngine) -> None:
        if not isinstance(name, str) or not name or "/" in name:
            raise ValueError("Engine name must be one nonempty path component")
        if name in self.engines:
            raise ValueError(f"Engine already registered: {name}")
        if not isinstance(engine, SearchEngine):
            raise TypeError("Engine must implement SearchEngine")
        if engine is self:
            raise ValueError("A SearchService cannot register itself")
        self.engines[name] = engine

    def _selected(self, query: SearchQuery) -> Iterator[tuple[str, SearchEngine]]:
        if query.engines is not None:
            unknown = query.engines.difference(self.engines)
            if unknown:
                raise KeyError(f"Unknown search engine: {sorted(unknown)[0]}")
        for name, engine in self.engines.items():
            if query.engines is None or name in query.engines:
                yield name, engine

    class Search(SearchEngine.Search):
        def accepts(self, query: SearchQuery) -> bool:
            return isinstance(query, SearchQuery)

        def _iter_hits(self, query: SearchQuery) -> Iterator[SearchHit]:
            for name, engine in self.obj._selected(query):
                stream = engine.search.iter_hits(query)
                try:
                    if stream.declined:
                        continue
                    for hit in stream:
                        yield SearchHit(hit.value, (name, *hit.engines))
                finally:
                    stream.close()


class SearchWorkflow(TaravWorkflow):
    constitution = "Dispatch typed search queries to independently registered engines."

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("5c4e8380-a79a-4de3-90f4-9725c56b4ff8"),
            name="Tarav.Workflow.Search",
            workflow=SEARCH_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls) -> WorkflowShip:
        return SEARCH_WORKFLOW_SHIP

    @staticmethod
    def service() -> SearchService:
        return SearchService()


__all__ = [
    "SEARCH_WORKFLOW_SHIP",
    "SearchEngine",
    "SearchHit",
    "SearchQuery",
    "SearchResult",
    "SearchService",
    "SearchStream",
    "SearchWorkflow",
]
