"""`tarav context` opens the Context of an identifier; reports advertise it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite
from tarav.l1.actions.project import ProjectActions
from tarav.l1.actions.pois import action_id
from tarav.l1.actions.views import ActionResolver
from tarav.l1.context.query import (
    ContextCandidate, ContextQuery, ContextQueryService, IdentityContextQuery,
)
from tarav.l1.poi.rendering import POISelection, renderer
from tarav.l1.actions import ActionRunStore
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
    """A sample POI whose Type adds notes to its context."""

    context_notes = ("It is described in the sample note.",
                     "It is no longer raised once the sample is fixed.")

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


# tarav.breadcrumb 818a901104c6130a1a3802829620962e62f290ac7b7202ba84b1465c834e9825
# tarav.breadcrumb 7d1ed0ce36ce5a6522313fae4015436f8bbe952d270165c1a37f05d158db2018
def test_an_action_is_found_by_its_id_and_by_the_id_of_its_poi(opened) -> None:
    poi = opened[0]
    by_action = _service(opened).open(IdentityContextQuery(str(action_id(poi))[:13]))
    by_poi = _service(opened).open(IdentityContextQuery(poi.identity[:12]))

    assert by_action.subject.id == by_poi.subject.id == action_id(poi)
    # no view is named: the action contributes its own entries, and its Type adds the POI's
    assert [entry.name for entry in by_action.target.ls() if entry.name != "class"] == [
        "standing", "poi", "poi-type", "raised-by", "notes", "detection", "acting",
        "project", "closing", "closings", "history"]


def test_a_path_is_followed_to_a_value(opened) -> None:
    answer = _service(opened).open(IdentityContextQuery(opened[0].identity, path=["notes"]))

    assert answer.location == ("notes",)
    assert answer.target.records.to_record()["value"] == [
        "It is described in the sample note.", "It is no longer raised once the sample is fixed."]
    kind = _service(opened).open(IdentityContextQuery(opened[0].identity, path=["poi-type"]))
    assert kind.target.records.to_record()["value"]["type"] == "Tarav.Test.GuidedPOI"


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

    answer = service.open(IdentityContextQuery("anything"))
    assert answer.subject is None and len(answer.candidates) == 2
    assert _service(opened).open(IdentityContextQuery("ffffffffffff")).candidates == ()


def test_queries_validate_their_parts() -> None:
    with pytest.raises(ValueError):
        IdentityContextQuery("  ")
    with pytest.raises(TypeError):
        ContextQuery(path="a/b")
    with pytest.raises(KeyError):
        ContextQueryService().open(IdentityContextQuery("x", view="missing"))


# tarav.breadcrumb fae0e168d36f1e4818647e0f437ee4772014d06bb618074c67240e5ef86bf888
def test_a_poi_describes_itself_and_owns_nothing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TARAV_RECORDS", str(tmp_path / "records"))
    poi = GuidedPOI(SampleCheck(), "Something was found", situation={"where": "a"})
    assert CheckPOI.context_notes == ()
    assert "notes" not in poi.as_dict(detail=True) and "context_notes" not in poi.as_dict(detail=True)
    described = poi.describe()
    assert described["notes"] == ["It is described in the sample note.",
                                  "It is no longer raised once the sample is fixed."]
    assert described["poi_type"]["type"] == "Tarav.Test.GuidedPOI"
    assert described["raised_by"]["type"] == "Tarav.Test.ContextSampleCheck"
    assert not ActionRunStore(RecordRegistry()).exists()  # describing stores nothing


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
    listing = capsys.readouterr().out
    assert listing.splitlines()[0].startswith(key) and "view: general" in listing
    assert "notes" in listing and "detection" in listing

    assert main(["context", "--id", poi.identity[:12], "--path", "poi", "--json"]) == 0
    value = json.loads(capsys.readouterr().out)["value"]["value"]
    assert value["situation"] == {"where": "a"}

    assert main(["context", "--id", "Tarav.POI"]) == 0
    assert "entity" in capsys.readouterr().out

    assert main(["context", "--id", "0000000000"]) != 0
    capsys.readouterr()
