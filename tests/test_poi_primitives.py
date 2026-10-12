import json
from pathlib import Path

import pytest

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.poi.actionable import BlessablePOI
from tarav.l1.poi import SituationPOI, POICollector


class AppReview(SituationPOI, BlessablePOI):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("c49acb13-c9f7-4184-a7c9-eae3d7826c88"),
            name="Example.AppReview",
        )

    # a specialization adds its own field, named for what it holds
    def __init__(self, message, *, situation, observed=None):
        super().__init__(message, situation=situation)
        self.observed = json.loads(json.dumps(observed or {}))

    @classmethod
    def finding(cls, situation, *, observed=None):
        return cls("Review application", situation=situation, observed=observed)


class AppError(SituationPOI):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("0068a0ed-bd9c-455e-af40-14248e0e0e27"),
            name="Example.AppError",
        )

    @classmethod
    def finding(cls, situation):
        return cls("Application error", situation=situation)


ACTOR = {"type": "Example.Agent", "locator": {"session": "test-session"}}


def test_lookup_prefixes_and_repeated_emission_indexes():
    collector = POICollector()
    first = collector.emit(AppReview.finding({"index": 0}))
    second = collector.emit(AppReview.finding({"index": 0}))
    with pytest.raises(ValueError, match="multiple emissions"):
        collector.get(first.identity)
    assert collector.get(first.identity[:12], index=0) is first
    assert collector.get(first.identity, index=1) is second
    with pytest.raises(ValueError, match="does not exist"):
        collector.get(first.identity, index=2)
    for invalid in ("", None):
        with pytest.raises(ValueError, match="nonempty"):
            collector.get(invalid)
    with pytest.raises(ValueError, match="does not exist"):
        collector.get("not-an-id")
    for i in range(1, 17):
        collector.emit(AppReview.finding({"index": i}))
    prefixes = [finding.identity[0] for finding in collector.pois[2:]]
    prefix = next(value for value in prefixes if prefixes.count(value) > 1)
    with pytest.raises(ValueError, match="Ambiguous"):
        collector.get(prefix)


def test_app_subclass_snapshot_and_source():
    data = {"value": 1}
    first = AppReview.finding({"file": "a"}, observed=data)
    data["value"] = 2
    second = AppReview.finding({"file": "a"}, observed=data)
    assert first.identity == second.identity
    assert first.observed["value"] == 1
    assert Path(first.as_dict()["help"]["source_path"]) == Path(__file__).resolve()


def test_blessing_remains_visible_and_matches_situation(tmp_path):
    from blessing_bench import Bench
    from tarav.l3.runtime import create_runtime

    bench = Bench(tmp_path / "records", create_runtime(archive_root=tmp_path / "archive").records)
    collector = POICollector()
    occurrence = collector.emit(
        AppReview.finding({"file": "a"}, observed={"value": 1})
    )
    blessing = bench.bless(occurrence, reason="Reviewed against the test contract.")
    # the POI is still collected and listed; whether it is blessed is asked of the Project
    report = collector.report()
    assert report["total"] == 1 and "blessing" not in report["items"][0]
    assert "by_blessing" not in report
    assert bench.pois.blessing(occurrence).id == blessing.id
    changed_evidence = AppReview.finding({"file": "a"}, observed={"value": 2})
    assert bench.pois.standing(changed_evidence) == "blessed"
    changed_situation = AppReview.finding(
        {"file": "a", "revision": 2}, observed={"value": 2}
    )
    assert bench.pois.standing(changed_situation) == "open"


def test_a_poi_that_is_not_blessable_reports_no_blessing(tmp_path):
    from blessing_bench import Bench
    from tarav.l3.runtime import create_runtime

    bench = Bench(tmp_path / "records", create_runtime(archive_root=tmp_path / "archive").records)
    collector = POICollector()
    error = collector.emit(AppError.finding({}))
    assert bench.pois.blessing(error) is None and bench.pois.of(error) is None
    assert bench.pois.standing(error) == "open"
    assert not bench.runs.exists()  # reading never creates the registry


def test_bounded_report_counts_all_and_retains_evidence():
    collector = POICollector()
    for i in range(25):
        collector.emit(
            AppReview.finding({"index": i}, observed={"payload": "x" * 500})
        )
    report = collector.report(limit=2)
    assert report["total"] == 25 and report["shown"] == 2
    assert report["next_offset"] == 2
    assert "observed" not in report["items"][0]  # a listing shows the base, not a Type's own fields
    assert len(collector.get(report["items"][0]["id"]).observed["payload"]) == 500


# tarav.breadcrumb 60ad34642493726fbf971cf722a95e7eaeda0049c5dd3660a97ca55f7692c6e2
def test_pois_are_atomic_and_carry_no_code():
    import inspect

    from tarav.l1.poi import NotificationPOI

    poi = AppError.finding({"path": "a"})
    assert not hasattr(poi, "code") and "code" not in poi.as_dict(detail=True)
    notice = NotificationPOI("Something happened")
    assert not hasattr(notice, "code") and "code" not in notice.as_dict()

    def subclasses(cls):
        for item in cls.__subclasses__():
            yield item
            yield from subclasses(item)

    for base in (SituationPOI, NotificationPOI):
        for poi_type in (base, *subclasses(base)):
            assert "code" not in inspect.signature(poi_type.__init__).parameters, poi_type


# tarav.breadcrumb 3412dc1bc71d3a44a4afba8328b173c8b241bb66f6738f123df2f0d851444ba4
def test_any_poi_can_be_thrown_and_the_error_carries_it():
    from tarav.l1.poi import NotificationPOI, POIError

    review = AppReview.finding({"app": "a"})
    notice = NotificationPOI("Something happened")
    for poi in (review, notice):
        with pytest.raises(POIError) as raised:
            poi.throw()
        assert raised.value.poi is poi
    with pytest.raises(POIError, match=review.identity):
        review.throw()


# tarav.breadcrumb 3fa8f026ab9acb15efdf4281afae2cc1c176ea7b9f2f6aa94e832bab8a1da8b3
def test_a_situation_poi_has_a_type_a_message_and_a_situation_and_nothing_else():
    poi = AppError.finding({"file": "a"})
    assert (poi.message, poi.situation) == ("Application error", {"file": "a"})
    assert set(poi.as_dict()) == {"type", "class_id", "id", "message", "situation", "help"}
    for gone in ("subject", "evidence", "coordinate"):
        assert not hasattr(poi, gone)
    with pytest.raises(TypeError):
        AppError("Application error", situation={"file": "a"}, evidence={"value": 1})
    with pytest.raises(TypeError):
        AppError("Application error", situation={"file": "a"}, subject={"file": "a"})

    # the same Type with the same situation is the same POI, whatever a Type adds beside it
    first = AppReview.finding({"file": "a"}, observed={"value": 1})
    second = AppReview.finding({"file": "a"}, observed={"value": 2})
    assert first.identity == second.identity and first.observed != second.observed
    assert AppReview.finding({"file": "b"}).identity != first.identity
    assert AppError.finding({"file": "a"}).identity != first.identity

    # the situation needs no structure common to all POIs: any description will do
    nested = AppError.finding({"where": {"file": "a", "line": 3}, "state": ["x", "y"]})
    assert nested.situation["where"]["line"] == 3
