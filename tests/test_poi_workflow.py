from copy import deepcopy

import pytest

from tarav.l0.kernel import TaravClass, TaravEntity, TypeShip, entity
from tarav.l1.blessings import (
    BlessablePOI,
    BlessingRecord,
    BlessingStore,
    BlessingsWorkflow,
)
from tarav.l1.checks import Check, CheckPOI
from tarav.l3.runtime import create_runtime


class ExampleCheck(Check):
    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("082c8223-a19a-4817-8235-7f405002f446"),
            name="Example.Check",
        )


class ExampleBlessablePOI(CheckPOI, BlessablePOI):
    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("98db26a0-1bbc-45e8-89a8-98e2bce59f68"),
            name="Example.BlessablePOI",
        )


class ReviewedBlessing(BlessingRecord):
    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("28b0ec48-2fe9-49f4-bb0e-d944aece9bdd"),
            name="Example.ReviewedBlessing",
        )

    def assessment_findings(self, assessments):
        return [] if any(a["assertion"] == "reviewed" for a in assessments) else [
            {"kind": "review-required", "blessing": str(self.id)}
        ]


def poi(*, evidence=None):
    check = ExampleCheck()
    return ExampleBlessablePOI(
        check,
        "example",
        "Example concern",
        subject={"path": "sample.md", "line": 12},
        evidence=evidence or {"text": "x"},
    )


def test_blessable_check_poi_composes_by_type_and_context():
    occurrence = poi()
    assert isinstance(occurrence, (CheckPOI, BlessablePOI))
    assert occurrence.context().open("check") is occurrence.check
    assert occurrence.context().open("coordinate").to_record()["value"] == occurrence.subject
    assert occurrence.context().open("evidence").to_record()["value"] == {"text": "x"}
    changed = poi(evidence={"text": "y"})
    assert changed.identity == occurrence.identity
    assert changed.state != occurrence.state


@pytest.mark.parametrize("field,value", [("id", "bad"), ("state", "bad")])
def test_invalid_blessing_snapshot_is_rejected(field, value):
    record = deepcopy(BlessingRecord.record_example())
    record["poi"][field] = value
    with pytest.raises(ValueError):
        BlessingRecord.validate_record(record)


def test_runtime_collector_and_blessing_storage_partition(tmp_path):
    runtime = create_runtime(
        archive_root=tmp_path,
        record_types=(ExampleCheck, ExampleBlessablePOI, ReviewedBlessing),
    )
    occurrence = runtime.pois.emit(poi())
    assert runtime.pois.get(occurrence.identity) is occurrence
    assert runtime.pois.report()["total"] == 1
    assert runtime.blessings.root == tmp_path / str(runtime.workflows.get("poi")().id) / "blessings"
    assert runtime.workflows.get("blessings") is BlessingsWorkflow


def test_typed_blessing_policy_roundtrip_context_and_staleness(tmp_path):
    runtime = create_runtime(
        archive_root=tmp_path,
        record_types=(ExampleCheck, ExampleBlessablePOI, ReviewedBlessing),
    )
    store = BlessingStore(tmp_path, record_types=(ReviewedBlessing,))
    actor = {"type": "Example.Actor", "locator": {"session": "fixture"}}
    occurrence = poi()
    record = store.bless(
        occurrence,
        actor=actor,
        rationale="Fixture review",
        record_type=ReviewedBlessing,
    )
    loaded = store.load(record["id"])
    assert isinstance(loaded, TaravEntity)
    assert loaded.to_record() == record
    assert entity(type(occurrence)).id in loaded.ships()
    assert runtime.records.from_record(record).id == loaded.id
    assert runtime.context(loaded).open("acceptance").to_record()["value"] == record
    assert store.standing(occurrence)["assessment_findings"][0]["kind"] == "review-required"
    assessment = store.assess(
        record["id"],
        actor=actor,
        assertion="reviewed",
        score=1,
        rationale="Fixture assessment",
    )
    assert store.load(assessment["id"]).to_record() == assessment
    assert loaded.id in store.load(assessment["id"]).ships()
    assert store.standing(occurrence)["assessment_findings"] == []
    assert store.standing(poi(evidence={"text": "changed"}))["status"] == "stale"
    assert runtime.blessings.record_types["Example.ReviewedBlessing"] is ReviewedBlessing


def test_typed_append_preserves_extra_fields_and_refuses_overwrite(tmp_path):
    store = BlessingStore(tmp_path, record_types=(ReviewedBlessing,))
    record = ReviewedBlessing.record_example()
    record["review_ticket"] = "example-ticket"
    blessing = ReviewedBlessing.from_record(record)
    assert store.add(blessing) is blessing
    assert store.load(blessing.id).to_record()["review_ticket"] == "example-ticket"
    with pytest.raises(FileExistsError):
        store.add(blessing)
