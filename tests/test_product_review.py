"""Product reviews are per-batch completion claims over committed map states."""

from datetime import datetime, timezone
import subprocess

import pytest

from tarav.l1.product_mapping import ContinuityDecision, ProductMapper
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
    mapper = ProductMapper(repo, "example-product", root=tmp_path / "maps")
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
    return tracker.create_batch(map_id=mapping.typed.id,
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


# tarav.context ec6cf584:f14fba928dd29981
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


# tarav.context ec6cf584:e9d7c7ce457bec3a
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
        assert TurnSnapshotStore().find(ref.locator.model_dump()) is not None
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


def test_horizon_is_based_on_commit_age_and_explicit_map_overrides(tracker):
    mapping = mapped(tracker, {"a": b"data"})
    with pytest.raises(ValueError, match="old enough"):
        tracker.select_map(now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert tracker.select_map(map_id=mapping.typed.id).typed.id == mapping.typed.id
    assert tracker.select_map(now=datetime(2100, 1, 1, tzinfo=timezone.utc)).typed.id == mapping.typed.id
