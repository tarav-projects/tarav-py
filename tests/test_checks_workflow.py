from tarav.l0.kernel import TaravClass, TypeShip
import pytest
from tarav.l1.checks import (
    Check,
    CheckPOI,
    CheckProvider,
    CheckResult,
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

    def dependent(suite):
        yield first
        assert len(suite.results) == 1  # the source reads what ran before it
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
    run = CheckSuite()
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
    text = renderer().render(POISelection.from_check_report(run.report()))
    assert text.splitlines()[0].endswith("checks ran, all completed. 3 POIs.")
    assert "POIs by type" not in text and "Checks by type" not in text


def test_run_pages_groups_and_blessings_do_not_hide_other_pois():
    check = ExampleCheck("one", [])
    run = CheckSuite()
    run.add(CheckResult(check, status="completed", pois=(
        ExamplePOI(check, "First", situation={"case": 1}),
    )))

    def label(poi):
        return "blessed" if isinstance(poi, ExamplePOI) else "open"

    assert not run.clean()  # a finding is a finding here; who settles it is not known
    assert "standing" not in run.report(limit=1)["items"][0]
    report = run.report(label=label, limit=1)
    assert report["items"][0]["standing"] == {"blessed": 1}
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


class KeptSuite(CheckSuite):
    """A suite with an identity of its own."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("2a6c9e14-7b3d-4f80-a5e1-9d0c4b8f7a36"),
                          name="Test.Checks.KeptSuite")


class SlowSuite(KeptSuite):
    routine = False

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("5e1b7d92-0f4a-4c63-8a2e-6b9d3c1f0e57"),
                          name="Test.Checks.SlowSuite")


# tarav.breadcrumb 70319c686e0b870849756c043ded64102d407771a8c2dbf716e1c4e478c8d499
def test_a_suite_holds_its_one_run_and_a_new_run_replaces_it():
    runs = []
    suite = CheckSuite([ExampleCheck("one", runs)])
    assert (suite.ran, suite.complete, suite.results) == (False, False, [])
    assert suite.run() is suite
    assert (suite.ran, suite.complete, len(suite.results), len(suite.pois())) == (True, True, 1, 1)
    suite.run()
    assert len(suite.results) == 1 and runs == ["one", "one"]
    suite.reset()
    assert (suite.ran, suite.results) == (False, [])


# tarav.breadcrumb fc1800cb2561bc56815b9e1a33aabdf7f03242145276bed14fc6b2197fc8654d
def test_a_suite_has_an_identity_from_its_type_and_key_and_a_grouping_has_none():
    assert CheckSuite([]).identity is None
    assert CheckSuite([], key="docs").identity == {"type": "Tarav.Checks.Suite", "key": "docs"}
    assert KeptSuite([]).identity == {"type": "Test.Checks.KeptSuite", "key": None}

    inner = KeptSuite([ExampleCheck("deep", [])], key="a")
    outer = KeptSuite([ExampleCheck("top", []), CheckSuite([inner])])
    chains = [[item["key"] for item in chain] for chain, _ in outer.run().walk()]
    assert chains == [[None], [None, "a"]]  # the grouping in between is not in the chain
    assert outer.suites()[-1] is inner


# tarav.breadcrumb c251c964c8d8bd667e4dbc6d75de2488d88efca85294cf02dba64444084c49ab
def test_a_filtered_run_is_not_complete_and_keeps_what_it_refused_as_not_run():
    runs = []
    slow = SlowSuite([ExampleCheck("slow", runs)], key="slow")
    kept = KeptSuite([ExampleCheck("quick", runs)], key="quick")
    whole = CheckSuite([kept, slow])

    def routine(item):
        return not (isinstance(item, CheckSuite) and not item.routine)

    whole.run(select=routine)
    assert runs == ["quick"]
    assert (kept.complete, slow.ran, slow.complete, whole.complete) == (True, False, False, False)
    # what the suite itself ran is conclusive; what a nested suite did not run is its own matter
    assert (whole.conclusive, kept.conclusive, slow.conclusive) == (True, True, False)
    assert whole.summary()["not_run"] == [
        {"type": "Test.Checks.SlowSuite", "key": "slow", "name": None}]
    assert slow in whole.suites()

    whole.run()
    assert runs == ["quick", "quick", "slow"] and whole.complete
    assert whole.summary()["not_run"] == []

    # a refused check also leaves the suite incomplete, and a failed one does too
    partial = CheckSuite([ExampleCheck("a", []), ExampleCheck("b", [])]).run(
        select=lambda item: item.subject != "b")
    assert (len(partial.results), partial.complete, partial.conclusive) == (1, False, False)
    failed = CheckSuite([CheckResult(ExampleCheck("c", []), status="failed", reason="x")]).run()
    assert not failed.complete and not failed.conclusive


def test_suites_that_ran_can_be_gathered_to_read_them_together():
    first = KeptSuite([ExampleCheck("one", [])], key="one").run()
    second = KeptSuite([ExampleCheck("two", [])], key="two").run()
    whole = CheckSuite.gathered([first, second], name="both")
    assert (len(whole.results), whole.complete, whole.summary()["checks"]) == (2, True, 2)
    assert whole.report()["summary"]["pois"] == 2

