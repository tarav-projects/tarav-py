from pathlib import Path

import pytest

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.poi.actionable import BlessablePOI
from tarav.l1.poi import IdentifiedPOI, POICollector


class AppReview(IdentifiedPOI, BlessablePOI):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("c49acb13-c9f7-4184-a7c9-eae3d7826c88"),
            name="Example.AppReview",
        )

    @classmethod
    def finding(cls, subject, *, evidence=None, situation=None):
        return cls(
            "Review application",
            situation=subject if situation is None else situation,
            subject=subject,
            evidence=evidence,
        )


class AppError(IdentifiedPOI):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("0068a0ed-bd9c-455e-af40-14248e0e0e27"),
            name="Example.AppError",
        )

    @classmethod
    def finding(cls, subject, *, evidence=None):
        return cls(
            "Application error",
            situation=subject,
            subject=subject,
            evidence=evidence,
        )


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
    first = AppReview.finding({"file": "a"}, evidence=data)
    data["value"] = 2
    second = AppReview.finding({"file": "a"}, evidence=data)
    assert first.identity == second.identity
    assert first.evidence["value"] == 1
    assert Path(first.as_dict()["help"]["source_path"]) == Path(__file__).resolve()


def test_blessing_remains_visible_and_matches_situation(tmp_path):
    from blessing_bench import Bench
    from tarav.l3.runtime import create_runtime

    bench = Bench(tmp_path / "records", create_runtime(archive_root=tmp_path / "archive").records)
    collector = POICollector()
    occurrence = collector.emit(
        AppReview.finding({"file": "a"}, evidence={"value": 1})
    )
    blessing = bench.bless(occurrence, reason="Reviewed against the test contract.")
    report = collector.report(actions=bench.pois)
    assert report["total"] == 1 and report["by_blessing"] == {"blessed": 1}
    assert report["items"][0]["blessing"] == {"status": "blessed", "blessing": str(blessing.id)}
    changed_evidence = AppReview.finding({"file": "a"}, evidence={"value": 2})
    assert bench.pois.blessing_standing(changed_evidence)["status"] == "blessed"
    changed_situation = AppReview.finding(
        {"file": "a", "revision": 2}, evidence={"value": 2}
    )
    assert bench.pois.blessing_standing(changed_situation)["status"] == "unblessed"
    assert collector.report(actions=bench.pois, blessing="unblessed")["matching"] == 0


def test_a_poi_that_is_not_blessable_reports_no_blessing(tmp_path):
    from blessing_bench import Bench
    from tarav.l3.runtime import create_runtime

    bench = Bench(tmp_path / "records", create_runtime(archive_root=tmp_path / "archive").records)
    collector = POICollector()
    error = collector.emit(AppError.finding({}))
    assert bench.pois.blessing_standing(error) is None and bench.pois.of(error) is None
    report = collector.report(actions=bench.pois)
    assert report["by_blessing"] == {} and "blessing" not in report["items"][0]
    assert not bench.runs.exists()  # reading never creates the registry


def test_bounded_report_counts_all_and_retains_evidence():
    collector = POICollector()
    for i in range(25):
        collector.emit(
            AppReview.finding({"index": i}, evidence={"payload": "x" * 500})
        )
    report = collector.report(limit=2)
    assert report["total"] == 25 and report["shown"] == 2
    assert report["next_offset"] == 2
    assert "evidence" not in report["items"][0]
    assert len(collector.get(report["items"][0]["id"]).evidence["payload"]) == 500


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

    for base in (IdentifiedPOI, NotificationPOI):
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
