from copy import deepcopy

import pytest

from tarav.l0.kernel import TaravClass, TaravEntity, TypeShip, entity
from tarav.l1.actions.blessing import Blessing
from tarav.l1.blessings import BlessingsWorkflow
from tarav.l1.poi.actionable import BlessablePOI
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


def poi(*, details=None, situation=None):
    check = ExampleCheck()
    return ExampleBlessablePOI(
        check,
        "Example concern",
        situation=(
            {"path": "sample.md", "line": 12}
            if situation is None
            else situation
        ),
        details=details or {"text": "x"},
    )


def test_blessable_check_poi_composes_by_type():
    occurrence = poi()
    assert isinstance(occurrence, (CheckPOI, BlessablePOI))
    # what a check observed is not part of the identity: the Type and the situation are
    changed = poi(details={"text": "y"})
    assert changed.identity == occurrence.identity
    assert changed.details != occurrence.details


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "bad"),
        ("situation", {"$tarav.lite": {"type": "unknown", "value": "bad"}}),
    ],
)
def test_a_blessing_with_an_invalid_poi_is_rejected(field, value):
    record = deepcopy(Blessing.records.record_example())
    record["poi"][field] = value
    with pytest.raises(ValueError):
        Blessing.records.parse_record(record)


def test_runtime_collector_and_blessings_workflow(tmp_path):
    runtime = create_runtime(
        archive_root=tmp_path,
        record_types=(ExampleCheck, ExampleBlessablePOI),
    )
    occurrence = runtime.pois.emit(poi())
    assert runtime.pois.get(occurrence.identity) is occurrence
    assert runtime.pois.report()["total"] == 1
    assert runtime.workflows.get("Tarav.Workflow.Blessings") is BlessingsWorkflow
    assert entity(Blessing).workflow is BlessingsWorkflow()


def test_a_blessing_roundtrips_as_the_closing_record_of_its_action(tmp_path):
    from blessing_bench import Bench

    runtime = create_runtime(
        archive_root=tmp_path / "archive",
        record_types=(ExampleCheck, ExampleBlessablePOI),
    )
    bench = Bench(tmp_path / "records", runtime.records)
    occurrence = poi()
    blessing = bench.bless(occurrence, reason="Fixture review")
    record = blessing.records.to_record()
    assert isinstance(blessing, TaravEntity)
    assert runtime.records.from_record(record).id == blessing.id
    assert bench.pois.of(occurrence).closing_record() == record
    assert (record["exit"], record["by"], record["reason"]) == ("blessed", "operator", "Fixture review")
    assert record["actor"] == {"provider": "example", "session_id": "reviewer", "since": record["at"]}
    assert record["poi"]["id"] == occurrence.identity
    assert bench.pois.standing(poi(details={"text": "changed"})) == "blessed"
    assert bench.pois.standing(poi(situation={"path": "other.md"})) == "open"
