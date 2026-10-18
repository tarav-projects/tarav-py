from __future__ import annotations

from collections.abc import Iterator

import pytest

from tarav.l0.kernel import TaravClass, TaravObject, TypeShip
from tarav.l1.search import (
    SearchEngine,
    SearchHit,
    SearchQuery,
    SearchWorkflow,
    SEARCH_WORKFLOW_SHIP,
)


class TextQuery(SearchQuery):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("fc8d2a17-a916-448f-b0da-1dcb85915fb7"),
            name="Tarav.Tests.Search.TextQuery",
            workflow=SEARCH_WORKFLOW_SHIP,
        )

    def __init__(self, text: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.text = text


class MemoryEngine(SearchEngine):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("64e0de2e-de23-4301-8799-b596f8b0c548"),
            name="Tarav.Tests.Search.MemoryEngine",
            workflow=SEARCH_WORKFLOW_SHIP,
        )

    def __init__(self, *values: str, accepts: bool = True) -> None:
        self.values = values
        self.enabled = accepts
        self.seen = 0
        self.closed = False
        self.checked = 0

    class Search(SearchEngine.Search):
        def accepts(self, query: SearchQuery) -> bool:
            self.obj.checked += 1
            return self.obj.enabled and isinstance(query, TextQuery)

        def _iter_hits(self, query: SearchQuery) -> Iterator[SearchHit]:
            try:
                for value in self.obj.values:
                    self.obj.seen += 1
                    if query.text in value:
                        yield SearchHit(value)
            finally:
                self.obj.closed = True


def test_acceptance_and_empty_results_are_distinct() -> None:
    engine = MemoryEngine("unrelated")
    empty = engine.search.run(TextQuery("target"))
    assert empty.accepted and empty.hits == ()
    assert engine.checked == 1

    declined_engine = MemoryEngine("target", accepts=False)
    declined = declined_engine.search.run(TextQuery("target"))
    assert declined.declined and declined.hits == ()
    assert declined_engine.seen == 0
    assert declined_engine.checked == 1


# tarav.breadcrumb b560e0cad1b0
def test_meta_search_selection_provenance_and_global_limit() -> None:
    first = MemoryEngine("a1", "a2", "a3")
    second = MemoryEngine("a4", "a5")
    service = SearchWorkflow.service()
    service.register("first", first)
    service.register("second", second)

    one = service.search.run(TextQuery("a", max_hits=1))
    assert [(hit.value, hit.engines) for hit in one.hits] == [("a1", ("first",))]
    assert first.seen == 1 and first.closed
    assert second.seen == 0

    first.seen = 0
    second.seen = 0
    three = service.search.run(TextQuery("a", max_hits=3))
    assert [hit.value for hit in three.hits] == ["a1", "a2", "a3"]
    assert second.seen == 0

    selected = service.search.run(TextQuery("a", engines={"second"}))
    assert [hit.value for hit in selected.hits] == ["a4", "a5"]
    assert all(hit.engines == ("second",) for hit in selected.hits)


def test_stream_is_incremental_closable_and_validates_selection() -> None:
    engine = MemoryEngine("a1", "a2")
    service = SearchWorkflow.service()
    service.register("memory", engine)

    stream = service.search.iter_hits(TextQuery("a", max_hits=1))
    assert engine.seen == 0
    assert next(stream).value == "a1"
    assert engine.seen == 1 and engine.closed
    assert list(stream) == []

    with pytest.raises(KeyError, match="Unknown search engine"):
        service.search.run(TextQuery("a", engines={"missing"}))
    with pytest.raises(ValueError, match="max_hits"):
        TextQuery("a", max_hits=0)


def test_accepted_engine_failure_propagates() -> None:
    class BrokenEngine(MemoryEngine):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("5131a8ae-2a45-4855-850b-775ac9a1d895"),
                name="Tarav.Tests.Search.BrokenEngine",
                workflow=SEARCH_WORKFLOW_SHIP,
            )

        class Search(MemoryEngine.Search):
            def _iter_hits(self, query: SearchQuery) -> Iterator[SearchHit]:
                raise RuntimeError("broken backend")
                yield  # pragma: no cover

    service = SearchWorkflow.service()
    service.register("broken", BrokenEngine())
    with pytest.raises(RuntimeError, match="broken backend"):
        service.search.run(TextQuery("a"))


def test_existing_object_type_can_add_search_capability() -> None:
    class Catalog(TaravObject, SearchEngine):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("06d5d173-c57d-48fd-959c-ac789e535445"),
                name="Tarav.Tests.Search.Catalog",
                workflow=SEARCH_WORKFLOW_SHIP,
            )

        class Search(SearchEngine.Search):
            def accepts(self, query: SearchQuery) -> bool:
                return isinstance(query, TextQuery)

            def _iter_hits(self, query: SearchQuery) -> Iterator[SearchHit]:
                yield SearchHit(query.text)

    catalog = Catalog()
    assert catalog.search.run(TextQuery("hello")).hits == (SearchHit("hello"),)
    assert "type" in catalog.records.to_record()


def test_runtime_owns_an_independent_search_service() -> None:
    from tarav.l3.runtime import create_runtime

    first = create_runtime()
    second = create_runtime()
    assert first.workflows.get("Tarav.Workflow.Search") is SearchWorkflow
    first.search.register("memory", MemoryEngine("one"))
    assert second.search.engines == {}
