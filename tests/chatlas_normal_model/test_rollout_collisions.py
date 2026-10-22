"""Independent native tapes must not overwrite events at reused record indexes."""
# tarav.breadcrumb 9dba4a89c7d4

import json

from tarav.l1.chatlas.normal_model import build_normal_model_from_row


def source(tmp_path, name, text, second):
    path = tmp_path / name
    records = [
        {"timestamp": "2026-10-22T00:00:00Z", "type": "session_meta", "payload": {"id": "same"}},
        {"timestamp": f"2026-10-22T00:00:{second:02d}Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": text}]}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return {"role": "transcript", "path": str(path)}


def test_conflicting_rollouts_retain_both_messages_and_their_real_observations(tmp_path):
    first = source(tmp_path, "original.jsonl", "Original user request", 1)
    second = source(tmp_path, "resumed.jsonl", "Independent later request", 2)
    row = {"provider": "codex", "session_id": "same", "identity_hash": "a" * 64,
           "backing_artifacts": [first, second]}
    model = build_normal_model_from_row(row)
    assert [m["text"] for m in model["messages"]] == [
        "Original user request", "Independent later request"]
    events = {e["event_address"]: e for e in model["events"]}
    for message in model["messages"]:
        event = events[message["event_refs"][0]["event_address"]]
        assert event["content"]["text"] == message["text"]
        assert len(event["observations"]) == 1
    # An identical copied prefix is one event with two real observations.
    metadata = [e for e in model["events"] if "content" not in e]
    assert len(metadata) == 1 and len(metadata[0]["observations"]) == 2
    row["backing_artifacts"].reverse()
    again = build_normal_model_from_row(row)
    assert [(m["message_address"], m["text"]) for m in again["messages"]] == [
        (m["message_address"], m["text"]) for m in model["messages"]]
