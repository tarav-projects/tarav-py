"""Product reviews are per-batch completion claims over committed map states."""

from datetime import datetime, timezone
import json
import subprocess
from uuid import uuid4

import pytest

from tarav.l1.product_mapping import ContinuityDecision, ProductMapper
from tarav.l0.kernel import entity
from tarav.l1.product_review import Batch
from tarav.l2.product_review import ReviewTracker
from tarav.l3.runtime import create_runtime


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def tracker(tmp_path, monkeypatch):
    monkeypatch.setenv("TARAV_RECORDS", str(tmp_path / "records"))
    create_runtime()
    repo = tmp_path / "product"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    mapper = ProductMapper(repo, "example-product", root=tmp_path / "maps", exclude=[".tarav/*"])
    return ReviewTracker(mapper, root=tmp_path / "reviews")


def mapped(tracker, files):
    mapper = tracker.mapper
    for path, value in files.items():
        target = mapper.product.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if value is None:
            target.unlink()
        else:
            target.write_bytes(value)
    git(mapper.product.root, "add", "-A")
    git(mapper.product.root, "commit", "-qm", "Product change")
    if not mapper.track():
        mapper.create(target_bytes=8, boundary_bytes=0)
    proposal = mapper.propose()
    decisions = [ContinuityDecision(source_ids=[c["id"]] if c["before"] else [],
                                    target_ids=[c["id"]] if c["after"] else [], reason="Test transition")
                 for c in mapper.changes(proposal)]
    return mapper.confirm(proposal, decisions=decisions, actor="test-agent", reason="Test transition")


def batch(tracker, mapping, *, chunks=None, title="Related material"):
    tracker.create()
    return tracker.create_batch(subject=str(entity(Batch).id), map_id=mapping.typed.id,
                                chunk_ids=chunks if chunks is not None else [c.id for c in mapping.typed.chunks],
                                title=title, purpose="Discuss design and capture outcomes",
                                actor="test-agent", reason="A coherent review subject")


@pytest.fixture
def chat(monkeypatch):
    """Valid Normal Model events/messages/turns; actual references and snapshot retention."""
    from tarav.l1.chatlas import references
    from tarav.l1.chatlas.normal_model import (
        compute_event_hash, compute_chat_message_hash, compute_chat_turn_hash,
    )
    from tarav.l1.chatlas.references import ChatlasTurnReference
    from tarav.l1.chatlas.turn_snapshots import TurnSnapshot
    from tarav.l2.product_review import tracker as tracker_module

    example = TurnSnapshot.records.record_example()
    model = {"session": example["session"], "sources": example["sources"],
             "metadata": {"commit": None}, "turns": [], "messages": [], "events": []}

    def add(side, text):
        index = len(model["turns"]) + 1
        address = f"{index:064x}"
        event = {"type": "User.Event" if side == "user" else "Agent.Event", "origin": side,
                 "event_address": address, "started_at": f"2026-10-22T00:00:{index:02d}Z",
                 "opaque_payload_hash": f"{index + 100:064x}", "content": {"text": text},
                 "observations": example["events"][0]["observations"]}
        event["event_hash"] = compute_event_hash(event)
        event_ref = {k: event[k] for k in ("event_address", "event_hash")}
        message = {"type": "Chat.Message", "side": side, "text": text,
                   "message_address": address, "event_refs": [event_ref]}
        message["message_hash"] = compute_chat_message_hash(message)
        turn = {"type": "Chat.Turn", "side": side, "turn_address": address,
                "event_refs": [event_ref], "message_refs": [{k: message[k] for k in ("message_address", "message_hash")}]}
        turn["turn_hash"] = compute_chat_turn_hash(turn, opaque_payload_hashes=[event["opaque_payload_hash"]])
        model["events"].append(event)
        model["messages"].append(message)
        model["turns"].append(turn)
        return ChatlasTurnReference.records.from_record({
            "type": "Tarav.Chatlas.Reference.Turn", "locator": {
                "session_identity": model["session"]["identity_hash"],
                "turn_address": address, "turn_hash": turn["turn_hash"]}})

    monkeypatch.setattr(references, "provide_normal_model", lambda **kw: model)
    monkeypatch.setattr(tracker_module, "provide_normal_model", lambda **kw: model)
    return add


def finish(tracker, revision, chat, *, outcomes=()):
    presentation = chat("agent", tracker.presentation(revision.typed.id))
    completion = chat("user", "::reviewed review:" + revision.typed.id)
    return tracker.complete(revision.typed.id, presentation=presentation, completion=completion, outcomes=outcomes)


# tarav.breadcrumb 591c26621a0e
def test_completeness_and_overlapping_batch_reviews_are_independent(tracker, chat):
    mapping = mapped(tracker, {"a.txt": b"alpha", "b.txt": b"beta"})
    a = next(c.id for c in mapping.typed.chunks if c.path == "a.txt")
    assert tracker.batches() == ()
    assert not tracker.store.root.exists()
    assert len(tracker.inspect(map_id=mapping.typed.id)["uncovered"]) == 2
    assert not tracker.store.root.exists()
    first = batch(tracker, mapping, chunks=[a])
    second = batch(tracker, mapping, title="Another perspective")
    report = tracker.inspect(map_id=mapping.typed.id)
    assert report["uncovered"] == []
    assert [b["state"] for b in report["batches"]] == ["pending", "pending"]
    finish(tracker, tracker.current(first.typed.id), chat)
    states = {b["batch_id"]: b["state"] for b in tracker.inspect(map_id=mapping.typed.id)["batches"]}
    assert states == {first.typed.id: "reviewed", second.typed.id: "pending"}


# tarav.breadcrumb 2e226f21af7c
def test_completion_retains_evidence_and_open_followup_without_approving_content(tracker, chat):
    from tarav.l1.chatlas.turn_snapshots import TurnSnapshotStore
    from tarav.l1.references import FileReference

    mapping = mapped(tracker, {"a.txt": b"Needs a design change"})
    current = tracker.current(batch(tracker, mapping).typed.id)
    outcome = FileReference(tracker.mapper.product.root / "followup-that-is-still-open.md")
    result = finish(tracker, current, chat, outcomes=[outcome])
    loaded = tracker.completion(current.typed.id)
    assert loaded.records.to_record() == result.records.to_record()
    assert loaded.typed.outcomes[0].locator == outcome.records.to_record()["locator"]
    for ref in (loaded.typed.presentation, loaded.typed.completion):
        assert TurnSnapshotStore().find(ref.locator) is not None
    assert tracker.inspect(map_id=mapping.typed.id)["batches"][0]["state"] == "reviewed"


def test_changed_chunks_require_batch_maintenance_and_new_review(tracker, chat):
    first = mapped(tracker, {"a.txt": b"before"})
    item = batch(tracker, first)
    original = tracker.current(item.typed.id)
    finish(tracker, original, chat)
    second = mapped(tracker, {"a.txt": b"after"})
    assert tracker.inspect(map_id=second.typed.id)["batches"][0]["state"] == "stale"
    updated = tracker.revise(item.typed.id, base=original.typed.id, map_id=second.typed.id,
                             chunk_ids=[c.id for c in second.typed.chunks], actor="agent", reason="Reconcile edited material")
    assert tracker.inspect(map_id=second.typed.id)["batches"][0]["state"] == "pending"
    assert tracker.read(original.typed.id)[0]["content"] == b"before"
    finish(tracker, updated, chat)
    assert tracker.inspect(map_id=second.typed.id)["batches"][0]["state"] == "reviewed"
    assert len(tracker.history(item.typed.id)) == 2
    assert all(r["completion"] is not None for r in tracker.history(item.typed.id))
    with pytest.raises(ValueError, match="Stale batch"):
        tracker.revise(item.typed.id, base=original.typed.id, map_id=second.typed.id,
                       chunk_ids=[c.id for c in second.typed.chunks], actor="a", reason="r")


def test_unrelated_edits_do_not_invalidate_unchanged_chunk_bytes(tracker, chat):
    first = mapped(tracker, {"a": b"abcdefgh12345678"})
    chunk = first.typed.chunks[0]
    item = batch(tracker, first, chunks=[chunk.id])
    finish(tracker, tracker.current(item.typed.id), chat)
    second = mapped(tracker, {"a": b"abcdefghABCDEFGH"})
    assert tracker.inspect(map_id=second.typed.id)["batches"][0]["state"] == "reviewed"


@pytest.mark.parametrize("failure", ["role", "token", "order", "presentation"])
def test_completion_requires_exact_presented_revision_and_later_user_token(tracker, chat, failure):
    mapping = mapped(tracker, {"a": b"data"})
    revision = tracker.current(batch(tracker, mapping).typed.id)
    early = chat("user", "::reviewed review:" + revision.typed.id) if failure == "order" else None
    presentation = chat("agent", "A vague summary" if failure == "presentation" else tracker.presentation(revision.typed.id))
    completion = early or chat("agent" if failure == "role" else "user",
                              "::reviewed review:" + ("wrong" if failure == "token" else revision.typed.id))
    with pytest.raises(ValueError):
        tracker.complete(revision.typed.id, presentation=presentation, completion=completion)
    assert tracker.completion(revision.typed.id) is None


def test_retirement_exposes_uncovered_chunks_and_retains_history(tracker):
    mapping = mapped(tracker, {"a": b"data"})
    item = batch(tracker, mapping)
    tracker.retire(item.typed.id, actor="agent", reason="Replace this grouping")
    assert tracker.batches() == ()
    assert len(tracker.batches(retired=True)) == 1
    assert len(tracker.inspect(map_id=mapping.typed.id)["uncovered"]) == 1
    assert len(tracker.history(item.typed.id)) == 1
    with pytest.raises(ValueError, match="absent"):
        batch(tracker, mapping, chunks=["00000000-0000-0000-0000-000000000000"])
    with pytest.raises(ValueError, match="unique"):
        batch(tracker, mapping, chunks=[mapping.typed.chunks[0].id] * 2)


def test_superseded_and_retired_revisions_cannot_be_completed(tracker, chat):
    mapping = mapped(tracker, {"a": b"data"})
    item = batch(tracker, mapping)
    previous = tracker.current(item.typed.id)
    presentation = chat("agent", tracker.presentation(previous.typed.id))
    completion = chat("user", "::reviewed review:" + previous.typed.id)
    current = tracker.revise(item.typed.id, base=previous.typed.id, map_id=mapping.typed.id,
                             chunk_ids=[c.id for c in mapping.typed.chunks], actor="agent", reason="New framing")
    with pytest.raises(ValueError, match="superseded"):
        tracker.complete(previous.typed.id, presentation=presentation, completion=completion)
    tracker.retire(item.typed.id, actor="agent", reason="Retired")
    with pytest.raises(ValueError, match="retired"):
        finish(tracker, current, chat)


def test_missing_maps_leave_scan_incomplete_and_never_provision(tracker):
    from tarav.l2.product_review.checks import ProductReviewSuite

    suite = ProductReviewSuite(tracker).run()
    results = suite.results
    assert len(results) == 1
    assert results[0].status == "incomplete"
    assert "No confirmed Product Map" in results[0].reason
    assert not tracker.store.root.exists()
    assert not tracker.mapper.store.root.exists()


def test_retained_batch_states_must_match_their_pinned_map(tracker):
    mapping = mapped(tracker, {"a": b"data"})
    revision = tracker.current(batch(tracker, mapping).typed.id)
    path = tracker.store.path("revision-" + revision.typed.id)
    record = json.loads(path.read_text())
    record["chunks"][0]["sha256"] = "0" * 64
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="pinned committed map"):
        tracker.read(revision.typed.id)


def test_horizon_is_based_on_commit_age_and_explicit_map_overrides(tracker):
    mapping = mapped(tracker, {"a": b"data"})
    with pytest.raises(ValueError, match="old enough"):
        tracker.select_map(now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert tracker.select_map(map_id=mapping.typed.id).typed.id == mapping.typed.id
    assert tracker.select_map(now=datetime(2100, 1, 1, tzinfo=timezone.utc)).typed.id == mapping.typed.id


def test_project_status_keeps_stable_independent_actions_and_preserves_them_if_scan_skips(tracker, chat, monkeypatch):
    from tarav.l1.project.config import ProjectConfig
    from tarav.l2.project import Project
    from tarav.l2.project.product_review import ProductReviewConfig

    first = mapped(tracker, {"a": b"before"})
    root = tracker.mapper.product.root
    (root / ".tarav").mkdir()
    (root / ".tarav/project.json").write_text(json.dumps({
        "type": "Tarav.Project", "project_id": str(uuid4()), "created_at": "2026-10-22T00:00:00Z"}))
    config = ProjectConfig(root)
    config.write_section("product_review", ProductReviewConfig(enabled=True, horizon_days=0))
    tracker.horizon_days = 0
    project = Project.from_path(root)
    monkeypatch.setattr(Project.Review, "open", lambda self: tracker)
    monkeypatch.setattr(Project.Checks, "suite", lambda self: self.obj.review.suite())
    project.status()
    coverage = project.actions.list()[0]
    assert coverage.data["action"] == "Tarav.ProductReview.Coverage.Required.Action"
    assert coverage.state == "running"
    assert not tracker.store.root.exists()
    item = batch(tracker, first)
    project.status()
    actions = {a.data["action"]: a for a in project.actions.list()}
    assert actions["Tarav.ProductReview.Coverage.Required.Action"].state == "closed"
    review_action = actions["Tarav.ProductReview.Batch.Required.Action"]
    assert review_action.state == "running"
    finish(tracker, tracker.current(item.typed.id), chat)
    project.status()
    assert project.actions.runs.find(str(review_action.id)).state == "closed"
    second = mapped(tracker, {"a": b"after"})
    project.status()
    assert project.actions.runs.find(str(review_action.id)).state == "running"
    project.status()
    assert len(project.actions.list()) == 2
    config.write_section("product_review", ProductReviewConfig(enabled=False))
    project.status()
    assert project.actions.runs.find(str(review_action.id)).state == "running"
    config.write_section("product_review", ProductReviewConfig(enabled=True))
    tracker.horizon_days = 100000
    project.status()
    assert project.actions.runs.find(str(review_action.id)).state == "running"
    tracker.horizon_days = 0
    revision = tracker.revise(item.typed.id, base=tracker.current(item.typed.id).typed.id,
                              map_id=second.typed.id, chunk_ids=[c.id for c in second.typed.chunks],
                              actor="agent", reason="Reconcile")
    finish(tracker, revision, chat)
    project.status()
    assert all(a.state == "closed" for a in project.actions.list())
    tracker.retire(item.typed.id, actor="agent", reason="Regroup")
    project.status()
    assert project.actions.runs.find(str(coverage.id)).state == "running"


def test_cli_and_project_config_select_same_maps_and_roundtrip_batch_history(tracker, tmp_path, capsys):
    from hashlib import sha256
    from tarav.l1.git.hooks import GitConfig
    from tarav.l1.project.config import ProjectConfig
    from tarav.l2.project import Project
    from tarav.l2.project.product_mapping import ProductMappingConfig
    from tarav.l2.project.product_review import ProductReviewConfig
    from tarav.l3.cli.cli import main

    root = tracker.mapper.product.root
    (root / ".tarav").mkdir()
    (root / ".tarav/project.json").write_text(json.dumps({
        "type": "Tarav.Project", "project_id": str(uuid4()), "created_at": "2026-10-22T00:00:00Z"}))
    config = ProjectConfig(root)
    rid = sha256(str(root).encode()).hexdigest()
    config.write_section("git", GitConfig(repository=rid))
    config.write_section("product_mapping", ProductMappingConfig(include=["*.txt"]))
    config.write_section("product_review", ProductReviewConfig(enabled=True, horizon_days=0))
    project = Project.from_path(root)
    selected = project.review.open()
    mapping = mapped(selected, {"a.txt": b"first", "ignored.md": b"not selected"})
    common = ["--repo", str(root), "--repository-id", rid]
    assert main(["product-review", "inspect", *common]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["map_id"] == mapping.typed.id
    assert report["chunks"] == 1
    assert not selected.store.root.exists()
    assert main(["product-review", "init", *common]) == 0
    capsys.readouterr()
    assert main(["product-review", "create", *common, "--subject", str(entity(Batch).id), "--chunk", mapping.typed.chunks[0].id,
                 "--title", "Design", "--purpose", "Discuss design", "--actor", "agent", "--reason", "Coherent subject"]) == 0
    revision = json.loads(capsys.readouterr().out)
    assert revision["commit"] == mapping.typed.commit
    assert revision["subject"] == str(entity(Batch).id)
    from tarav.l2.product_review import ClassBatch, ClassReviewTracker
    assert isinstance(selected, ClassReviewTracker)
    assert isinstance(selected.batch(revision["batch_id"]), ClassBatch)
    assert main(["product-review", "present", *common, "--revision", revision["id"]]) == 0
    assert "::reviewed review:" + revision["id"] in capsys.readouterr().out
    (root / "a.txt").write_text("uncommitted changes")
    assert main(["product-review", "read", *common, "--revision", revision["id"]]) == 0
    assert json.loads(capsys.readouterr().out)[0]["content"] == "Zmlyc3Q="
    assert main(["product-review", "history", *common, "--batch", revision["batch_id"]]) == 0
    history = json.loads(capsys.readouterr().out)
    assert history[0]["revision"]["id"] == revision["id"]
    assert history[0]["completion"] is None
    assert main(["product-review", "list", *common, "--subject", str(entity(Batch).id)]) == 0
    assert [b["batch_id"] for b in json.loads(capsys.readouterr().out)] == [revision["batch_id"]]
    assert main(["product-review", "create", *common, "--subject", str(entity(Batch).id), "--chunk", str(uuid4()),
                 "--title", "Invalid", "--purpose", "Invalid", "--actor", "agent", "--reason", "Invalid"]) != 0


# tarav.breadcrumb fada5041aab9
def test_generic_subject_is_required_and_preserved_in_revision_evidence(tracker, chat):
    mapping = mapped(tracker, {"a": b"data"})
    tracker.create()
    external_subject = "99de9103-7a1a-4a18-8e14-8493f71bbc35"
    item = tracker.create_batch(subject=external_subject, map_id=mapping.typed.id,
                                chunk_ids=[c.id for c in mapping.typed.chunks],
                                title="External product subject", purpose="Discuss", actor="agent", reason="Grouping")
    assert type(item) is Batch
    assert str(item.typed.subject) == external_subject
    revision = tracker.current(item.typed.id)
    assert str(revision.typed.subject) == external_subject
    assert "Subject: " + external_subject in tracker.presentation(revision.typed.id)
    finish(tracker, revision, chat)
    updated = tracker.revise(item.typed.id, base=revision.typed.id, map_id=mapping.typed.id,
                             chunk_ids=[c.id for c in mapping.typed.chunks], actor="agent", reason="Refine wording")
    assert str(updated.typed.subject) == external_subject
    assert tracker.history(item.typed.id)[0]["revision"]["subject"] == external_subject
    assert tracker.inspect(map_id=mapping.typed.id)["batches"][0]["subject"] == external_subject
    malformed = item.records.to_record()
    del malformed["subject"]
    with pytest.raises(ValueError, match="subject"):
        Batch.records.from_record(malformed)
    assert tracker.batches(subject=external_subject)[0].typed.id == item.typed.id


# tarav.breadcrumb e3cfc7674766
def test_class_attachment_reuses_existing_type_graph_and_survives_retirement(tracker):
    from tarav.l0.kernel import TaravObject
    from tarav.l1.product_review import ProductReviewWorkflow
    from tarav.l2.product_review import ClassBatch, ClassReviewTracker

    mapping = mapped(tracker, {"a": b"data"})
    selected = ClassReviewTracker(tracker.mapper, root=tracker.store.root).create()
    first = batch(selected, mapping)
    second = batch(selected, mapping, title="Another review of the same class")
    assert type(first) is ClassBatch
    assert first.subject_entity().target is Batch
    assert [base.id for base in first.subject_entity().bases()] == [entity(TaravObject).id]
    assert first.subject_entity().workflow.id == ProductReviewWorkflow().id
    assert {b.typed.id for b in selected.batches(subject=entity(Batch).id)} == {first.typed.id, second.typed.id}
    assert selected.batches(subject=entity(TaravObject).id) == ()
    workflow_batch = selected.create_batch(subject=entity(ProductReviewWorkflow).id,
                                           map_id=mapping.typed.id, chunk_ids=[mapping.typed.chunks[0].id],
                                           title="Workflow", purpose="Discuss", actor="agent", reason="Workflow subject")
    assert workflow_batch.subject_entity().target is ProductReviewWorkflow
    reloaded = selected.store.records.from_record(first.records.to_record())
    assert type(reloaded) is ClassBatch
    assert reloaded.subject_entity().id == entity(Batch).id
    retired = selected.retire(first.typed.id, actor="agent", reason="Replace grouping")
    assert type(retired) is ClassBatch
    assert str(retired.typed.subject) == str(entity(Batch).id)
    assert len(selected.history(first.typed.id)) == 1
    assert selected.batches(subject=entity(Batch).id)[0].typed.id == second.typed.id


def test_class_subject_refuses_instance_workflow_entity_and_unknown_ids_before_writes(tracker):
    from tarav.l1.product_review import ProductReviewWorkflow
    from tarav.l2.product_review import ClassReviewTracker

    mapping = mapped(tracker, {"a": b"data"})
    selected = ClassReviewTracker(tracker.mapper, root=tracker.store.root).create()
    values = dict(map_id=mapping.typed.id, chunk_ids=[c.id for c in mapping.typed.chunks],
                  title="Subject", purpose="Discuss", actor="agent", reason="Grouping")
    for invalid in (str(uuid4()), str(ProductReviewWorkflow().id), "not-a-uuid"):
        with pytest.raises(ValueError):
            selected.create_batch(subject=invalid, **values)
        assert selected.store.names() == ()
    instance_id = batch(selected, mapping).typed.id
    before = selected.store.names()
    with pytest.raises(ValueError):
        selected.create_batch(subject=instance_id, **values)
    assert selected.store.names() == before


def test_generic_and_class_batches_for_different_products_share_workflow_storage(tracker, tmp_path):
    from tarav.l2.product_review import ClassReviewTracker

    generic_map = mapped(tracker, {"a": b"data"})
    generic = batch(tracker, generic_map)
    mapper = ProductMapper(tracker.mapper.repository, "another-product", root=tmp_path / "other-maps")
    selected = ClassReviewTracker(mapper, root=tracker.store.root)
    class_map = mapped(selected, {"b": b"more"})
    attached = batch(selected, class_map)
    assert [b.typed.id for b in selected.batches()] == [attached.typed.id]
    assert [b.typed.id for b in tracker.batches()] == [generic.typed.id]


# tarav.breadcrumb 39c031e45c92
def test_chunk_limit_boundary_and_rejected_writes_preserve_existing_records(tracker, chat):
    mapping = mapped(tracker, {str(i): b"data" for i in range(9)})
    ids = [c.id for c in mapping.typed.chunks]
    item = batch(tracker, mapping, chunks=ids[:8])
    revision = tracker.current(item.typed.id)
    finish(tracker, revision, chat)
    before = {key: tracker.store.path(key).read_bytes() for key in tracker.store.names()}
    with pytest.raises(ValueError, match="9 chunks; maximum is 8"):
        batch(tracker, mapping)
    with pytest.raises(ValueError, match="maximum is 8"):
        tracker.revise(item.typed.id, base=revision.typed.id, map_id=mapping.typed.id,
                       chunk_ids=ids, actor="agent", reason="Too broad")
    assert {key: tracker.store.path(key).read_bytes() for key in tracker.store.names()} == before
    tracker.max_chunks = 7
    report = tracker.inspect(map_id=mapping.typed.id)["batches"][0]
    assert (report["state"], report["chunks"], report["max_chunks"]) == ("oversized", 8, 7)
    assert tracker.completion(revision.typed.id) is not None
    assert len(tracker.history(item.typed.id)) == 1
    with pytest.raises(ValueError, match="maximum is 7"):
        tracker.complete(revision.typed.id, presentation=None, completion=None)
    assert {key: tracker.store.path(key).read_bytes() for key in tracker.store.names()} == before


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "8"])
def test_maximum_chunk_count_must_be_positive_integer(tracker, value):
    from tarav.l2.project.product_review import ProductReviewConfig

    with pytest.raises(ValueError):
        ReviewTracker(tracker.mapper, max_chunks=value)
    with pytest.raises(ValueError):
        ProductReviewConfig(max_chunks=value)


def test_project_size_control_and_cli_enforce_same_boundary(tracker, capsys, chat, monkeypatch):
    from hashlib import sha256
    from tarav.l1.git.hooks import GitConfig
    from tarav.l1.project.config import ProjectConfig
    from tarav.l2.project import Project
    from tarav.l2.project.product_review import ProductReviewConfig
    from tarav.l2.project.product_mapping import ProductMappingConfig
    from tarav.l3.cli.cli import main

    root = tracker.mapper.product.root
    (root / ".tarav").mkdir()
    (root / ".tarav/project.json").write_text(json.dumps({
        "type": "Tarav.Project", "project_id": str(uuid4()), "created_at": "2026-10-22T00:00:00Z"}))
    rid = sha256(str(root).encode()).hexdigest()
    config = ProjectConfig(root)
    config.write_section("git", GitConfig(repository=rid))
    config.write_section("product_mapping", ProductMappingConfig(include=["[abc]"]))
    config.write_section("product_review", ProductReviewConfig(enabled=True, horizon_days=0, max_chunks=2))
    project = Project.from_path(root)
    selected = project.review.open()
    mapping = mapped(selected, {"a": b"a", "b": b"b", "c": b"c"})
    selected.create()
    common = ["--repo", str(root), "--repository-id", rid]
    create = ["product-review", "create", *common, "--subject", str(entity(Batch).id),
              "--title", "Subject", "--purpose", "Discuss", "--actor", "agent", "--reason", "Grouping"]
    chunks = [value for c in mapping.typed.chunks for value in ("--chunk", c.id)]
    assert main([*create, *chunks]) != 0
    assert "maximum is 2" in capsys.readouterr().err
    assert selected.store.names() == ()
    assert main([*create, *chunks[:4]]) == 0
    revision = json.loads(capsys.readouterr().out)
    assert len(revision["chunks"]) == 2
    monkeypatch.setattr(Project.Checks, "suite", lambda self: self.obj.review.suite())
    project.status()
    action = next(a for a in project.actions.list() if a.data["action"] == "Tarav.ProductReview.Batch.Required.Action")
    finish(selected, selected.revision(revision["id"]), chat)
    project.status()
    assert project.actions.runs.find(str(action.id)).state == "closed"
    config.write_section("product_review", ProductReviewConfig(enabled=True, horizon_days=0, max_chunks=1))
    report = project.review.open().inspect(map_id=mapping.typed.id)
    assert report["batches"][0]["state"] == "oversized"
    project.status()
    reopened = project.actions.runs.find(str(action.id))
    assert reopened.state == "running"
    assert reopened.data["event"]["poi"]["details"]["state"] == "oversized"
    smaller = project.review.open()
    updated = smaller.revise(revision["batch_id"], base=revision["id"], map_id=mapping.typed.id,
                              chunk_ids=[revision["chunks"][0]["id"]], actor="agent", reason="Smaller review subject")
    finish(smaller, updated, chat)
    project.status()
    assert project.actions.runs.find(str(action.id)).state == "closed"
