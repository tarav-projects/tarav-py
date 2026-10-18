"""`tarav context` finds what an identifier identifies and opens its Context."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.l0.kernel import RDF_TYPE, TaravClass, TypeShip, entity
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite
from tarav.l1.actions.project import ProjectActions
from tarav.l1.actions.pois import action_id
from tarav.l1.actions.views import ActionResolver
from tarav.l1.context.query import ContextCandidate, ContextQueryService, IdentityContextQuery
from tarav.l1.poi.rendering import POISelection, renderer
from tarav.l1.actions import ActionRun, ActionRunStore
from tarav.l1.records import RecordRegistry
from tarav.l3.runtime import create_runtime, set_runtime
from tarav.l1.search import SearchEngine, SearchHit
from tarav.l3.cli.cli import main


class SampleCheck(Check):
    """A check used only by these tests."""

    __test__ = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("11a1f1de-0000-4000-8000-0000000008a1"),
                          name="Tarav.Test.ContextSampleCheck")

    def _run(self) -> CheckResult:
        return CheckResult(self, status="completed", pois=[
            GuidedPOI(self, "Something was found", situation={"where": place},
                      details={"where": place}) for place in ("a", "b")])


class GuidedPOI(CheckPOI):
    """A sample POI raised by the sample check."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("11a1f1de-0000-4000-8000-0000000008a2"),
                          name="Tarav.Test.GuidedPOI")


@pytest.fixture
def opened(tmp_path: Path, monkeypatch):
    """Two sample POIs escalated to actions of one Project, in a registry of their own."""
    monkeypatch.setenv("TARAV_RECORDS", str(tmp_path / "records"))
    set_runtime(create_runtime())
    suite = CheckSuite([SampleCheck()]).run()
    ProjectActions({"id": "p1", "name": "sample", "root": str(tmp_path)}).update(suite)
    yield list(suite.pois())
    set_runtime(None)


def _service(opened) -> ContextQueryService:
    service = ContextQueryService()
    service.register_resolver("action", ActionResolver())
    return service


# tarav.breadcrumb 818a901104c6
# tarav.breadcrumb 7d1ed0ce36ce
def test_an_action_is_found_by_its_id_and_by_the_id_of_its_poi(opened) -> None:
    poi = opened[0]
    by_action = _service(opened).find(str(action_id(poi))[:13])
    by_poi = _service(opened).find(poi.identity[:12])
    assert by_action.id == by_poi.id == action_id(poi)

    # its Context holds what it contributes: by default, its type
    [edge] = by_action.context().ls()
    assert (edge.direction, edge.predicate, edge.node.name) == ("out", RDF_TYPE, "Tarav.Actions.Run")


def test_several_matches_are_candidates_and_none_is_empty(opened) -> None:
    class Both(SearchEngine):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(target=cls, id=TypeShip("11a1f1de-0000-4000-8000-0000000008a3"),
                              name="Tarav.Test.BothResolver")

        class Search(SearchEngine.Search):
            def accepts(self, query) -> bool:
                return isinstance(query, IdentityContextQuery)

            def _iter_hits(self, query):
                for name in ("one", "two"):
                    yield SearchHit(ContextCandidate(SampleCheck(), name, name))

    service = ContextQueryService()
    service.register_resolver("both", Both())

    assert len(service.resolve(IdentityContextQuery("anything"))) == 2
    with pytest.raises(KeyError, match="2 things"):
        service.find("anything")
    assert _service(opened).resolve(IdentityContextQuery("ffffffffffff")) == ()


def test_queries_validate_their_parts() -> None:
    with pytest.raises(ValueError):
        IdentityContextQuery("  ")


# tarav.breadcrumb fae0e168d36f
def test_a_pois_record_holds_the_occurrence_and_nothing_of_its_type(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TARAV_RECORDS", str(tmp_path / "records"))
    poi = GuidedPOI(SampleCheck(), "Something was found", situation={"where": "a"})
    record = poi.records.to_record()
    assert set(record) == {"type", "class_id", "id", "message", "situation", "check",
                           "details", "failure"}
    assert record["check"] == "Tarav.Test.ContextSampleCheck"
    assert not ActionRunStore(RecordRegistry()).exists()  # a record is a form, not a store


def test_a_printed_report_points_at_no_stored_context() -> None:
    run = CheckSuite()
    run.add(SampleCheck().run())
    rendered = renderer().render(POISelection.from_check_report(run.report(by="identity")))
    assert "tarav context" not in rendered and "Before acting" not in rendered
    assert rendered.splitlines()[0] == "1 checks ran, all completed. 2 POIs."


def test_the_command_opens_an_action_and_reports_misses(opened, capsys) -> None:
    poi = opened[0]
    key = str(action_id(poi))
    assert main(["context", "--id", key[:13]]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith(key)
    assert lines[1] == f"focus: <urn:uuid:{key}>  Tarav.Actions.Run"
    assert lines[2:] == ["edges:", f"  0  → <{RDF_TYPE}>  <urn:uuid:{entity(ActionRun).id}>  Tarav.Actions.Run"]

    assert main(["context", "--id", poi.identity[:12], "--json"]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert answer["focus"] == {"node": f"<urn:uuid:{key}>", "type": "Tarav.Actions.Run"}
    assert [(edge["direction"], edge["predicate"], edge["type"]) for edge in answer["edges"]] == [
        ("out", RDF_TYPE, "Tarav.Actions.Run")]

    assert main(["context", "--id", "Tarav.POI"]) == 0
    assert "Tarav.Class" in capsys.readouterr().out

    assert main(["context", "--id", "0000000000"]) != 0
    capsys.readouterr()


def test_a_named_view_is_an_explicit_error(opened, capsys) -> None:
    assert main(["context", "--id", "Tarav.POI", "--view", "object-group"]) != 0
    assert "'object-group' is not implemented in the graph Context model" in capsys.readouterr().err
