from tarav.l0.kernel import TaravClass, TypeShip
import pytest
from tarav.l1.checks import Check, CheckPOI, CheckProvider, CheckResult, run_checks
from tarav.l1.poi import POI, NotificationPOI, POICheck, POICollector, POIError


class ExamplePOI(POICheck):
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
                           pois=(ExamplePOI.finding({"subject": self.subject}),))


class ExampleProvider(CheckProvider):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("76d74fa5-9b8e-40d4-9d07-d2bbdf484f52"),
                          name="Test.Checks.ExampleProvider")

    def __init__(self, subjects, runs):
        self.subjects = subjects
        self.runs = runs

    @property
    def checks(self):
        return tuple(ExampleCheck(subject, self.runs) for subject in self.subjects)


# tarav.breadcrumb deba349a12b1413c1a834413f6ac1640a9cbeffe4e9972aa2940b6bf96548484
def test_check_results_are_snapshots_and_poi_emission_is_explicit():
    runs = []
    check = ExampleCheck("one", runs)
    result = check.run()
    first = result.pois()
    assert result.status == "completed" and runs == ["one"]
    assert result.pois() is first and runs == ["one"]
    collector = POICollector()
    assert collector.findings == []
    collector.emit(first[0])
    assert collector.findings == [first[0]]
    try:
        first[0].error()
    except POIError as exc:
        assert exc.poi is first[0]
    else:
        raise AssertionError("POI.error() should raise only when explicitly called")


def test_provider_and_explicit_pool_use_the_same_runner():
    runs = []
    provider = ExampleProvider(("one", "two"), runs)
    results = run_checks((*provider.checks, ExampleCheck("cross-subject", runs)))
    assert runs == ["one", "two", "cross-subject"]
    assert [result.pois()[0].subject["subject"] for result in results] == runs


# tarav.breadcrumb e73444ba05e865201671436a374aa312fd999aa1cf64d4b89f76f2f60138980b
def test_neutral_and_bound_pois_share_collection_without_blessing_metadata():
    from tarav.l3.runtime import get_runtime

    get_runtime()
    check = ExampleCheck("one", [])
    plain = POI()
    notice = NotificationPOI("position-updated", "Position recorded.")
    failure = CheckPOI(check, "position-stale", "Position needs attention.",
                       details={"line": 3})
    positive = CheckPOI(check, "position-current", "Position is current.",
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
    assert notice.context().open("details").to_record()["value"] == {}
    assert [entry.name for entry in failure.context().ls()] == [
        "class", "check", "details",
    ]
    assert failure.context().open("check") is check
    assert failure.context().open("details").to_record()["value"] == {"line": 3}
    with pytest.raises(ValueError, match="another Check"):
        CheckResult(ExampleCheck("two", []), status="completed", pois=(failure,))
