"""Decisions and optional tracking keep detection separate from review."""

import json
from uuid import uuid4

import pytest

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.poi.actionable import BlessablePOI
from tarav.l1.decisions import Decision
from tarav.l1.poi import SituationPOI
from tarav.l2.project import Project
from tarav.l2.project.decisions import ProjectDecisions
from tarav.l3.runtime import create_runtime


class ExamplePOI(SituationPOI, BlessablePOI):
    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("1120cd8e-d47d-49dd-884c-707117a963d4"),
            name="Example.TrackedPOI",
        )


class ExampleDecision(Decision):
    """A consumer-owned Decision type; the core workflow prescribes none."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("5b0f2a55-7b0c-4f0e-9d0b-0c2f6a1a7e31"),
            name="Example.Decision",
        )


def poi(path="one.md"):
    return ExamplePOI(
        "Inspect the file", situation={"path": path},
    )


# tarav.breadcrumb f7a0423ffc8b7ace60117c25dced069fe711e2984aeca2b13a54b39fe369cb00
def test_decision_types(tmp_path):
    runtime = create_runtime(archive_root=tmp_path / "archive",
                             record_types=(ExamplePOI, ExampleDecision))
    record = ExampleDecision.records.record_example()
    record["id"] = str(uuid4())
    decision = runtime.records.from_record(record)
    assert isinstance(decision, Decision)
    assert decision.records.to_record() == record
    assert decision.decider == record["actor"]
    assert decision.poi_ids == ()
    assert tuple(decision.assertions) == ("main",)


def test_a_blessing_is_a_closing_record_not_a_decision(tmp_path):
    from blessing_bench import Bench

    bench = Bench(tmp_path / "records", create_runtime(archive_root=tmp_path / "archive").records)
    occurrence = poi()
    blessing = bench.bless(occurrence, reason="Reviewed independently of a board")
    assert bench.pois.standing(occurrence) == "blessed"
    assert not isinstance(blessing, Decision)
    assert blessing.records.to_record()["poi"]["id"] == occurrence.identity


def _project(tmp_path):
    marker = tmp_path / ".tarav" / "project.json"
    marker.parent.mkdir()
    marker.write_text(json.dumps(Project.records.record_example()), encoding="utf-8")
    return Project.from_path(tmp_path)


# tarav.breadcrumb 759580814ab6b198d65103c278d4ca330779d6de41cd9eff7fb7559b296e626c
def test_project_store_holds_every_decision_type_and_filters_by_subtype(tmp_path):
    runtime = create_runtime(archive_root=tmp_path / "archive",
                             record_types=(ExamplePOI, ExampleDecision))
    project = _project(tmp_path)
    assert project.decisions().root == tmp_path / ".tarav" / "decisions"
    store = ProjectDecisions(project, record_types=runtime.records.record_types)
    assert store.snapshot() == {"records": [], "findings": []}
    assert not store.root.exists()

    record = ExampleDecision.records.record_example()
    record["id"] = str(uuid4())
    decision = runtime.records.from_record(record)
    store.add(decision)
    with pytest.raises(FileExistsError):
        store.add(decision)
    with pytest.raises(TypeError):
        store.add(object())

    everything = store.snapshot()
    assert {row["id"] for row in everything["records"]} == {record["id"]}
    assert everything["findings"] == []
    assert [row["id"] for row in store.snapshot(decision_type=ExampleDecision)["records"]] == [
        record["id"]]
    assert store.load(record["id"]).records.to_record() == record
    with pytest.raises(TypeError):
        store.snapshot(decision_type=dict)
    assert not hasattr(store, "blessings")  # blessings are closing records of actions

    unknown = {**record, "id": str(uuid4()), "type": "Example.Unregistered"}
    (store.root / f"{unknown['id']}.json").write_text(json.dumps(unknown), encoding="utf-8")
    findings = store.snapshot()["findings"]
    assert [row["kind"] for row in findings] == ["unknown-decision-type"]
    assert len(store.snapshot()["records"]) == 1
