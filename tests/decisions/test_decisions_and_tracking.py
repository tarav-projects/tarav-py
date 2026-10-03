"""Decisions and optional tracking keep detection separate from review."""

import json
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.blessings import BlessablePOI, BlessingRecord, BlessingStore
from tarav.l1.decisions import Decision, DecisionStore
from tarav.l1.poi import IdentifiedPOI, POICollector, TrackedPOIStore
from tarav.l2.poi import TrackedPOIBoard
from tarav.l2.project import Project
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
        "example", "Inspect the file", situation={"path": path},
        subject={"path": path}, evidence={"source": path},
    )


def collector(*values):
    result = POICollector()
    for value in values:
        result.emit(value)
    return result


# tarav.breadcrumb f7a0423ffc8b7ace60117c25dced069fe711e2984aeca2b13a54b39fe369cb00
def test_decision_types_and_unchanged_blessing_schema(tmp_path):
    runtime = create_runtime(archive_root=tmp_path / "archive",
                             record_types=(ExamplePOI, ExampleDecision))
    record = ExampleDecision.record_example()
    record["id"] = str(uuid4())
    decision = runtime.records.from_record(record)
    assert isinstance(decision, Decision)
    assert decision.to_record() == record
    assert decision.decider == record["actor"]
    assert decision.poi_ids == ()
    assert tuple(decision.assertions) == ("main",)
    store = DecisionStore(tmp_path / "decisions", record_types=(ExampleDecision,))
    store.add(decision)
    assert store.load(decision.id).to_record() == record
    with pytest.raises(TypeError):
        DecisionStore(tmp_path / "unregistered").add(decision)

    old_record = deepcopy(BlessingRecord.record_example())
    blessing = runtime.records.from_record(old_record)
    assert isinstance(blessing, Decision)
    assert blessing.to_record() == old_record
    assert "decider" not in blessing.to_record()
    assert "subjects" not in blessing.to_record()
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


def test_scoped_detection_does_not_resolve_partial_or_other_scope(tmp_path):
    store = TrackedPOIStore(tmp_path / "tracked")
    first, second = poi("one.md"), poi("two.md")
    a, b = {"check": "sample", "subject": "one"}, {"check": "sample", "subject": "two"}
    clock = datetime(2026, 10, 3, tzinfo=timezone.utc)
    store.reconcile(collector(first), scope=a, completed=True, at=clock)
    store.reconcile(collector(second), scope=b, completed=True, at=clock)
    before = store.snapshot()
    store.reconcile(collector(), scope=a, completed=False, at=clock)
    assert store.snapshot() == before
    store.reconcile(collector(), scope=a, completed=True, at=clock)
    assert store.load(first.identity).to_record()["detected"] is False
    assert store.load(second.identity).to_record()["detected"] is True
    store.reconcile(collector(first), scope=a, completed=True, at=clock)
    record = store.load(first.identity).to_record()
    assert record["detected"] is True
    assert [item["detected"] for item in record["history"]] == [True, False, True]
    with pytest.raises(ValueError, match="another evaluation scope"):
        store.reconcile(collector(first), scope=b, completed=True, at=clock)


# tarav.breadcrumb 0ecd63d43977c7fcc8124b99dc848c9d451476d65383c2a5bbb9f13b9d6d773c
def test_board_keeps_detected_blessing_visible_and_filters(tmp_path):
    create_runtime(archive_root=tmp_path / "archive")
    occurrence = poi()
    tracking = TrackedPOIStore(tmp_path / "tracked")
    tracking.track(occurrence, scope={"check": "example"})
    blessings = BlessingStore(tmp_path / "blessings")
    blessings.bless(
        occurrence,
        actor={"type": "Example.Actor", "locator": {"name": "reviewer"}},
        rationale="Reviewed for now",
    )
    board = TrackedPOIBoard(tracking, blessings=blessings)
    report = board.report(disposition="blessed", detected=True,
                          workflow=entity(ExamplePOI).workflow_ship,
                          subject={"path": "one.md"})
    assert report["matching"] == 1
    assert report["items"][0]["detected"] is True
    assert report["items"][0]["disposition"] == "blessed"
    assert len(report["items"][0]["decisions"]) == 1
    assert board.report(disposition="unreviewed")["matching"] == 0


def test_new_evidence_for_same_situation_remains_in_history(tmp_path):
    store = TrackedPOIStore(tmp_path / "tracked")
    first = poi()
    revised = ExamplePOI("example", "Inspect the file",
                         situation={"path": "one.md"},
                         subject={"path": "one.md"}, evidence={"source": "new.md"})
    assert first.identity == revised.identity
    store.reconcile(collector(first), scope={"check": "example"}, completed=True)
    store.reconcile(collector(revised), scope={"check": "example"}, completed=True)
    record = store.load(first.identity).to_record()
    assert [row["poi"]["evidence"]["source"] for row in record["history"]] == [
        "one.md", "new.md",
    ]


def test_featured_project_exposes_a_caller_rooted_board(tmp_path):
    marker = tmp_path / ".tarav" / "project.json"
    marker.parent.mkdir()
    marker.write_text(json.dumps(Project.record_example()), encoding="utf-8")
    project = Project.from_path(tmp_path)
    board = project.poi_board()
    assert board.store.root == tmp_path / ".tarav" / "tracked-pois"
    assert board.report()["total"] == 0
