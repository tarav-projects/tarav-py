from tarav.l0.kernel import TaravClass, TypeShip
import pytest
from tarav.l1.checks import (
    Check,
    CheckPOI,
    CheckProvider,
    CheckResult,
    CheckRun,
    CheckSuite,
    Situation,
    SituationCheck,
)
from tarav.l1.poi import POI, NotificationPOI, POICollector, POIError
from tarav.l1.poi.rendering import POISelection, renderer


class ExamplePOI(CheckPOI):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("e68c86e9-d41a-4330-b391-dcfad5b886fa"),
                          name="Test.Checks.ExamplePOI")


class ExampleCheck(Check):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("40f76eaf-ecbd-4178-85c7-e7b156b6a67d"),
                          name="Test.Checks.ExampleCheck")

    def __init__(self, subject, runs):
        super().__init__()
        self.subject = subject
        self.runs = runs

    def _run(self):
        self.runs.append(self.subject)
        return CheckResult(self, status="completed",
                           pois=(ExamplePOI(self, "Example POI",
                                            situation={"subject": self.subject},
                                            subject={"subject": self.subject}),))


class ExampleProvider(CheckProvider):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("76d74fa5-9b8e-40d4-9d07-d2bbdf484f52"),
                          name="Test.Checks.ExampleProvider")

    def __init__(self, subjects, runs):
        self.subjects = subjects
        self.runs = runs

    # tarav.breadcrumb 49dfd66b8b659cca0b7b1bf975a0d0e68d95074082d73d912c36a1086278a601
    class Checks(CheckProvider.Checks):
        def suite(self):
            return CheckSuite(
                ExampleCheck(subject, self.obj.runs) for subject in self.obj.subjects
            )


class DifferenceSituation(Situation):
    def __init__(self, value):
        super().__init__(value)
        if set(self) != {"before", "after"}:
            raise ValueError("DifferenceSituation requires before and after")


class DifferenceCheck(SituationCheck):
    SituationType = DifferenceSituation

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("c8439168-3b52-4cb2-a39e-290b4be59a89"),
            name="Test.Checks.DifferenceCheck",
        )

    def _run(self):
        pois = ()
        if self.situation["before"] != self.situation["after"]:
            pois = (self.poi(
                ExamplePOI,
                message="The values differ.",
            ),)
        return CheckResult(self, status="completed", pois=pois)


class MismatchedSituationCheck(SituationCheck):
    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("9b4088d5-0b7d-471d-af44-ff375d7bd9d7"),
            name="Test.Checks.MismatchedSituationCheck",
        )

    def _run(self):
        poi = ExamplePOI(
            self,
            "Wrong situation.",
            situation={"different": True},
        )
        return CheckResult(self, status="completed", pois=(poi,))


# tarav.breadcrumb deba349a12b1413c1a834413f6ac1640a9cbeffe4e9972aa2940b6bf96548484
def test_check_results_are_snapshots_and_poi_emission_is_explicit():
    runs = []
    check = ExampleCheck("one", runs)
    result = check.run()
    first = result.pois()
    assert result.status == "completed" and runs == ["one"]
    assert result.pois() is first and runs == ["one"]
    collector = POICollector()
    assert collector.pois == []
    collector.emit(first[0])
    assert collector.pois == [first[0]]
    try:
        first[0].throw()
    except POIError as exc:
        assert exc.poi is first[0]
    else:
        raise AssertionError("POI.throw() should raise only when explicitly called")


def test_provider_and_explicit_pool_use_the_same_runner():
    runs = []
    provider = ExampleProvider(("one", "two"), runs)
    results = CheckSuite((provider.checks.suite(), ExampleCheck("cross-subject", runs))).run().results
    assert runs == ["one", "two", "cross-subject"]
    assert [result.pois()[0].subject["subject"] for result in results] == runs


def test_suite_runs_nested_and_run_dependent_sources_without_iteration():
    runs = []
    first = ExampleCheck("first", runs)
    skipped = ExampleCheck("skipped", runs)

    def dependent(run):
        yield first
        assert len(run.results) == 1
        yield CheckResult(skipped, status="incomplete", reason="not ready")
        yield CheckSuite.of((ExampleCheck("last", runs),))

    suite = CheckSuite(dependent)
    with pytest.raises(TypeError, match="not iterable"):
        iter(suite)
    observed = []
    result = suite.run(on_result=observed.append)
    assert runs == ["first", "last"]
    assert observed == result.results
    assert [row.status for row in result.results] == ["completed", "incomplete", "completed"]
    assert result.summary()["incomplete"] == 1


def test_suite_catches_crashing_check_and_keeps_later_results():
    class CrashingCheck(ExampleCheck):
        @classmethod
        def class_entity(cls):
            return TaravClass(target=cls, id=TypeShip("7547db9a-b060-4c90-987a-6159c986a87a"),
                              name="Test.Checks.CrashingCheck")

        def _run(self):
            raise RuntimeError("boom")

    runs = []
    result = CheckSuite.of((CrashingCheck("bad", runs), ExampleCheck("good", runs))).run()
    assert [row.status for row in result.results] == ["failed", "completed"]
    assert result.results[0].reason == "RuntimeError: boom"
    assert runs == ["good"]
    assert not result.clean()


# tarav.breadcrumb c1d8e1fc5d14330556280f20990a300b3f0ce01766b40e42602933df7a7be80d
def test_run_groups_pois_by_type_and_identity_without_codes():
    check = ExampleCheck("one", [])
    first = ExamplePOI(check, "First", situation={"subject": "one"})
    second = ExamplePOI(check, "Second", situation={"subject": "one"})
    notice = NotificationPOI("An event")
    run = CheckRun()
    run.add(CheckResult(check, status="completed", pois=(first, second, notice)))
    assert first.identity == second.identity
    assert run.summary()["pois"] == 3
    assert run.report()["matching"] == 2
    by_identity = run.report(by="identity")
    assert by_identity["matching"] == 2
    assert by_identity["items"][0]["pois"] == 2
    assert "codes" not in by_identity["items"][0] and "by_code" not in run.summary()
    assert "code" not in first.as_dict() and "code" not in notice.as_dict()
    with pytest.raises(ValueError):
        run.report(by="code")
    assert len(run.report(by="identity", type="Tarav.POI.Notification")["items"]) == 1
    assert "POIs by type" in renderer().render(POISelection.from_check_report(run.report()))


def test_run_pages_groups_and_blessings_do_not_hide_other_pois():
    check = ExampleCheck("one", [])
    run = CheckRun()
    run.add(CheckResult(check, status="completed", pois=(
        ExamplePOI(check, "First", situation={"case": 1}),
    )))

    class Actions:
        def standing(self, poi):
            return "blessed" if isinstance(poi, ExamplePOI) else "open"

    actions = Actions()
    assert run.clean(actions=actions)
    assert not run.clean()
    report = run.report(actions=actions, limit=1)
    assert (report["items"][0]["blessed"], report["items"][0]["open"]) == (1, 0)
    assert report["next_offset"] is None
    with pytest.raises(ValueError, match="positive limit"):
        run.report(limit=0)


def test_run_pages_distinct_identities_after_grouping():
    run = CheckSuite.of(ExampleCheck(str(number), []) for number in range(25)).run()
    grouped = run.report()
    assert grouped["matching"] == 1
    assert grouped["items"][0]["pois"] == 25

    first = run.report(by="identity")
    second = run.report(by="identity", offset=first["next_offset"])
    assert (first["matching"], first["shown"], first["next_offset"]) == (25, 20, 20)
    assert (second["shown"], second["next_offset"]) == (5, None)
    assert run.report(by="check", sort="count")["items"][0]["checks"] == 25


# tarav.breadcrumb f80da43bcc2b842c5857008fb9145baf66db8ca4efdd591b34e9a69f8e7f0ad0
def test_situation_checks_snapshot_validate_and_bind_poi_identity():
    source = {"before": 1, "after": 2}
    check = DifferenceCheck(situation=source)
    source["after"] = 1

    poi = check.run().pois()[0]
    assert check.situation.to_json_value() == {"before": 1, "after": 2}
    assert check.context().open("situation").records.to_record()["value"] == {
        "before": 1,
        "after": 2,
    }
    assert poi.situation == check.situation.to_json_value()
    assert DifferenceCheck(situation=Situation(source)).run().pois() == ()

    with pytest.raises(ValueError, match="requires before and after"):
        DifferenceCheck(situation={"before": 1})
    with pytest.raises(ValueError, match="different situation"):
        MismatchedSituationCheck(situation={"value": 1}).run()


# tarav.breadcrumb e73444ba05e865201671436a374aa312fd999aa1cf64d4b89f76f2f60138980b
def test_neutral_and_bound_pois_share_collection_without_blessing_metadata():
    from tarav.l3.runtime import get_runtime

    get_runtime()
    check = ExampleCheck("one", [])
    plain = POI()
    notice = NotificationPOI("Position recorded.")
    failure = CheckPOI(check, "Position needs attention.",
                       situation={"state": "stale", "line": 3},
                       details={"line": 3})
    positive = CheckPOI(check, "Position is current.",
                        situation={"state": "current"},
                        failure=False)
    result = CheckResult(check, status="completed",
                         pois=(plain, notice, failure, positive))
    assert result.status == "completed"
    assert result.pois()[2].check is check
    assert failure.as_dict()["details"] == {"line": 3}
    collector = POICollector()
    for poi in result.pois():
        collector.emit(poi)
    report = collector.report()
    assert report["total"] == 4
    assert report["by_blessing"] == {}
    assert all("blessing" not in item for item in report["items"])
    assert [entry.name for entry in notice.context().ls()] == ["class", "details"]
    assert notice.context().open("details").records.to_record()["value"] == {}
    assert [entry.name for entry in failure.context().ls()] == [
        "class", "situation", "coordinate", "evidence", "check", "details",
    ]
    assert failure.context().open("check") is check
    assert failure.context().open("details").records.to_record()["value"] == {"line": 3}
    with pytest.raises(ValueError, match="another Check"):
        CheckResult(ExampleCheck("two", []), status="completed", pois=(failure,))
