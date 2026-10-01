from pathlib import Path

import pytest

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.blessings import BlessablePOI, BlessingStore
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
            "app-review",
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
            "app-error",
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
    store = BlessingStore(tmp_path / ".tarav/acceptances")
    collector = POICollector()
    occurrence = collector.emit(
        AppReview.finding({"file": "a"}, evidence={"value": 1})
    )
    record = store.bless(
        occurrence,
        actor=ACTOR,
        rationale="Reviewed against the test contract.",
    )
    report = collector.report(store=store)
    assert report["total"] == 1 and report["by_blessing"] == {"blessed": 1}
    assert report["items"][0]["blessing"]["assessment"] == "unassessed"
    changed_evidence = AppReview.finding({"file": "a"}, evidence={"value": 2})
    assert store.standing(changed_evidence)["status"] == "blessed"
    changed_situation = AppReview.finding(
        {"file": "a", "revision": 2}, evidence={"value": 2}
    )
    assert store.standing(changed_situation)["status"] == "unblessed"
    store.assess(
        record["id"],
        actor=ACTOR,
        assertion="acceptance-justified",
        score=0.2,
        rationale="The stated justification covers only part of the evidence.",
    )
    assert store.standing(occurrence)["scores"][0]["score"] == 0.2
    assert len(list(store.root.glob("*.json"))) == 2


def test_refusal_and_invalid_actor_do_not_write(tmp_path):
    store = BlessingStore(tmp_path / "records")
    with pytest.raises(ValueError, match="does not permit"):
        store.bless(AppError.finding({}), actor=ACTOR, rationale="test")
    with pytest.raises(ValueError, match="reference"):
        store.bless(AppReview.finding({}), actor={}, rationale="test")
    assert not store.root.exists()


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


def test_corrupt_record_does_not_hide_pois(tmp_path):
    store = BlessingStore(tmp_path)
    (tmp_path / "bad.json").write_text("{}")
    (tmp_path / "not-an-object.json").write_text("[]")
    collector = POICollector()
    collector.emit(AppError.finding({}))
    report = collector.report(store=store)
    assert report["total"] == 1 and len(report["store_findings"]) == 2
