"""Decisions and optional tracking keep detection separate from review."""

import json
from copy import deepcopy
from uuid import uuid4

import pytest

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.blessings import BlessablePOI, BlessingRecord, BlessingStore
from tarav.l1.decisions import Decision
from tarav.l1.poi import IdentifiedPOI
from tarav.l2.project import Project
from tarav.l2.project.decisions import ProjectDecisions
from tarav.l3.runtime import create_runtime


class ExamplePOI(IdentifiedPOI, BlessablePOI):
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
        subject={"path": path}, evidence={"source": path},
    )


# tarav.breadcrumb f7a0423ffc8b7ace60117c25dced069fe711e2984aeca2b13a54b39fe369cb00
def test_decision_types_and_unchanged_blessing_schema(tmp_path):
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
    old_record = deepcopy(BlessingRecord.records.record_example())
    blessing = runtime.records.from_record(old_record)
    assert isinstance(blessing, Decision)
    assert blessing.records.to_record() == old_record
    assert "decider" not in blessing.records.to_record()
    assert "subjects" not in blessing.records.to_record()
    assert blessing.decider == old_record["actor"]
    assert blessing.poi_ids == (old_record["poi"]["id"],)


def test_blessing_still_works_without_tracking(tmp_path):
    create_runtime(archive_root=tmp_path / "archive")
    store = BlessingStore(tmp_path / "blessings")
    occurrence = poi()
    record = store.bless(
        occurrence,
        actor={"type": "Example.Actor", "locator": {"name": "reviewer"}},
        rationale="Reviewed independently of a board",
    )
    assert store.standing(occurrence)["status"] == "blessed"
    assert store.load(record["id"]).poi_ids == (occurrence.identity,)
    assert not (tmp_path / "tracked").exists()


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

    occurrence = poi()
    blessing = store.blessings().bless(
        occurrence,
        actor={"type": "Example.Actor", "locator": {"name": "reviewer"}},
        rationale="Reviewed for now",
    )
    everything = store.snapshot()
    assert {row["id"] for row in everything["records"]} == {record["id"], blessing["id"]}
    assert everything["findings"] == []
    assert [row["id"] for row in store.snapshot(decision_type=BlessingRecord)["records"]] == [
        blessing["id"]]
    assert [row["id"] for row in store.snapshot(decision_type=ExampleDecision)["records"]] == [
        record["id"]]
    assert store.load(record["id"]).records.to_record() == record
    with pytest.raises(TypeError):
        store.snapshot(decision_type=dict)

    # tarav.breadcrumb f34b06cac58de0d8085404d8c0e31d487f5e132a44f75e470e3184f2ee1f104c
    blessings = store.blessings()
    assert blessings.standing(occurrence)["status"] == "blessed"
    assert blessings.snapshot()["findings"] == []
    assert [row["id"] for row in blessings.snapshot()["records"]] == [blessing["id"]]

    unknown = {**record, "id": str(uuid4()), "type": "Example.Unregistered"}
    (store.root / f"{unknown['id']}.json").write_text(json.dumps(unknown), encoding="utf-8")
    findings = store.snapshot()["findings"]
    assert [row["kind"] for row in findings] == ["unknown-decision-type"]
    assert len(store.snapshot()["records"]) == 2
