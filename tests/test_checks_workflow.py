from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import Check, CheckProvider, CheckResult, run_checks
from tarav.l1.poi import POI, POICollector, POIError


class ExamplePOI(POI):
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
