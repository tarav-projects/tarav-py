"""`tarav context` opens the Context of an identifier; reports advertise it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite
from tarav.l1.checks.poi_contract import (
    POIContextRoundTripCheck,
)
from tarav.l1.context.query import (
    ContextCandidate, ContextQuery, ContextQueryService, IdentityContextQuery,
)
from tarav.l1.poi.reporting import (
    REPORTED_POI_VIEW, ReportedPOI, ReportedPOIContext, ReportedPOIResolver,
    ReportedPOIStore, context_instruction, reported_record,
)
from tarav.l1.poi.rendering import POISelection, renderer
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
def reported(tmp_path: Path, monkeypatch) -> list[str]:
    monkeypatch.setenv("TARAV_CHECK_REPORTS", str(tmp_path / "reports"))
    run = CheckSuite()
    run.add(SampleCheck().run())
    ReportedPOIStore().retain(run.pois(), project={"id": "p1", "name": "sample"})
    return [poi.identity for poi in run.pois()]


def _service(store: ReportedPOIStore | None = None) -> ContextQueryService:
    service = ContextQueryService()
    service.register_resolver("reported-poi", ReportedPOIResolver(store))
    service.register_view(REPORTED_POI_VIEW, ReportedPOIContext)
    return service


# tarav.breadcrumb 818a901104c6130a1a3802829620962e62f290ac7b7202ba84b1465c834e9825
def test_an_identity_query_opens_the_requested_view(reported: list[str]) -> None:
    answer = _service().open(IdentityContextQuery(reported[0][:12], view=REPORTED_POI_VIEW))

    assert isinstance(answer.subject, ReportedPOI)
    assert [entry.name for entry in answer.target.ls()] == [
        "poi-type", "raised-by", "occurrence", "notes", "action"]
    assert answer.views == (REPORTED_POI_VIEW,)


def test_the_general_view_is_the_default_and_names_other_views(reported: list[str]) -> None:
    answer = _service().open(IdentityContextQuery(reported[0]))

    assert "summary" in [entry.name for entry in answer.target.ls()]
    assert answer.views == (REPORTED_POI_VIEW,)


def test_a_path_is_followed_to_a_value(reported: list[str]) -> None:
    answer = _service().open(
        IdentityContextQuery(reported[0], view=REPORTED_POI_VIEW, path=["notes"]))

    assert answer.location == ("notes",)
    assert answer.target.records.to_record()["value"] == [
        "It is described in the sample note.", "It is no longer raised once the sample is fixed."]


def test_several_matches_are_candidates_and_none_is_empty(reported: list[str]) -> None:
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
    assert _service().open(IdentityContextQuery("ffffffffffff")).candidates == ()


def test_queries_validate_their_parts() -> None:
    with pytest.raises(ValueError):
        IdentityContextQuery("  ")
    with pytest.raises(TypeError):
        ContextQuery(path="a/b")
    with pytest.raises(KeyError):
        ContextQueryService().open(IdentityContextQuery("x", view="missing"))


def test_notes_belong_to_the_poi_type_and_not_to_the_poi_record() -> None:
    poi = GuidedPOI(SampleCheck(), "Something was found", situation={"where": "a"})
    assert CheckPOI.context_notes == ()
    assert "notes" not in poi.as_dict(detail=True) and "context_notes" not in poi.as_dict(detail=True)
    assert reported_record(poi)["notes"] == ["It is described in the sample note.",
                                             "It is no longer raised once the sample is fixed."]


# tarav.breadcrumb 74712dcf68e97f58fe0e4ee967aac259d1ae2d412c8eb34f0fb4864be1b10b9a
# tarav.breadcrumb 9b5c21419a84b555a93bf7f45e6d5cc16156f43c1f4406d7cf135057a48e3318
def test_a_report_with_pois_opens_with_one_instruction() -> None:
    run = CheckSuite()
    run.add(SampleCheck().run())
    rendered = renderer().render(POISelection.from_check_report(
        run.report(by="identity"))).splitlines()

    first = run.pois()[0].identity
    assert rendered[2:4] == context_instruction(first)  # two lines, before the list
    assert f"e.g. tarav context --id {first[:12]} --view {REPORTED_POI_VIEW}" in rendered[3]
    assert sum("Before acting on any POI" in line for line in rendered) == 1

    empty = CheckSuite()
    assert "tarav context" not in renderer().render(
        POISelection.from_check_report(empty.report()))


def test_the_command_lists_opens_and_reports_misses(reported: list[str], capsys) -> None:
    assert main(["context", "--id", reported[0][:12], "--view", REPORTED_POI_VIEW]) == 0
    listing = capsys.readouterr().out
    assert "occurrence" in listing and "notes" in listing

    assert main(["context", "--id", reported[0], "--view", REPORTED_POI_VIEW,
                 "--path", "occurrence", "--json"]) == 0
    value = json.loads(capsys.readouterr().out)["value"]["value"]
    assert value["situation"] == {"where": "a"}

    assert main(["context", "--id", "Tarav.POI"]) == 0
    assert "entity" in capsys.readouterr().out

    assert main(["context", "--id", "0000000000"]) != 0
    capsys.readouterr()


def test_the_contract_checks_report_through_the_check_system(tmp_path: Path) -> None:
    assert POIContextRoundTripCheck().run().pois() == ()

