"""Cited evidence survives projection changes without retargeting a reference."""
# tarav.breadcrumb 420038399a3f

from copy import deepcopy
import json

import pytest

from tarav.l1.chatlas.normal_model import build_normal_model_from_row
from tarav.l1.chatlas.references import ChatlasTurnReference
from tarav.l1.chatlas.turn_snapshots import TurnSnapshot, TurnSnapshotStore, retained_turn


@pytest.fixture
def model(tmp_path):
    raw = tmp_path / "rollout.jsonl"
    rows = [
        {"timestamp": "2026-10-22T00:00:00Z", "type": "session_meta", "payload": {"id": "test"}},
        {"timestamp": "2026-10-22T00:00:01Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "Keep my exact request."}]}},
    ]
    raw.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    return build_normal_model_from_row({
        "provider": "codex", "session_id": "test", "identity_hash": "a" * 64,
        "backing_artifacts": [{"role": "transcript", "path": str(raw)}]})


def test_retained_turn_resolves_after_current_projection_is_unavailable(tmp_path, model, monkeypatch):
    root = tmp_path / "chatlas"
    store = TurnSnapshotStore(chatlas_root=root)
    turn = next(t for t in model["turns"] if t["side"] == "user")
    snapshot = store.retain(model, turn)
    locator = {"session_identity": model["session"]["identity_hash"],
               **{k: turn[k] for k in ("turn_address", "turn_hash")}}
    assert retained_turn(locator, chatlas_root=root)["messages"] == model["messages"]
    path = store.map.path(store.key(locator))
    before = path.read_bytes()
    assert store.retain(model, turn).records.to_record() == snapshot.records.to_record()
    assert path.read_bytes() == before
    # A reference uses the same exact coordinates and explicitly names the representation.
    monkeypatch.setenv("TARAV_RECORDS", str(root / "records"))
    def unavailable(**kwargs):
        raise AssertionError("current model must not be needed")
    monkeypatch.setattr("tarav.l1.chatlas.references.provide_normal_model", unavailable)
    ref = ChatlasTurnReference.records.from_record({"type": "Tarav.Chatlas.Reference.Turn", "locator": locator})
    target = ref.locate(locator)
    assert target["representation"] == "retained-snapshot"
    assert target["messages"][0]["text"] == "Keep my exact request."


def test_snapshot_lookup_does_not_create_missing_storage(tmp_path):
    root = tmp_path / "missing"
    locator = {k: "a" * 64 for k in ("session_identity", "turn_address", "turn_hash")}
    assert retained_turn(locator, chatlas_root=root) is None
    assert not root.exists()


@pytest.mark.parametrize("kind", ["event", "message", "turn", "source", "membership"])
def test_snapshot_rejects_tampered_evidence(tmp_path, model, kind):
    turn = next(t for t in model["turns"] if t["side"] == "user")
    snapshot = TurnSnapshotStore(chatlas_root=tmp_path / "chatlas").retain(model, turn)
    data = deepcopy(snapshot.records.to_record())
    if kind == "event":
        data["events"][0]["content"]["text"] = "Changed"
    elif kind == "message":
        data["messages"][0]["text"] = "Changed"
    elif kind == "turn":
        data["turn"]["turn_hash"] = "b" * 64
    elif kind == "source":
        data["sources"] = []
    else:
        data["turn"]["event_refs"].append(data["turn"]["event_refs"][0])
    with pytest.raises(ValueError):
        TurnSnapshot.records.from_record(data)


def test_registered_snapshot_example_is_valid():
    example = TurnSnapshot.records.record_example()
    assert TurnSnapshot.records.from_record(example).records.to_record() == example
