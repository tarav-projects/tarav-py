from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.l1.chatlas.normal_model.pipeline import build_normal_model_from_row
from tarav.l1.chatlas.normal_model_cache import NormalModelCache
from tarav.l1.chatlas.normal_models_index import NormalModelsIndex
from tarav.l1.chatlas.query import ChatlasQuery, ChatlasQueryEngine


def _record(second: int, kind: str, payload: dict) -> dict:
    return {"timestamp": f"2026-10-20T19:00:{second:02d}Z", "type": kind, "payload": payload}


def _source(tmp_path: Path, records: list[dict]) -> dict:
    path = tmp_path / "rollout.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in [
        _record(0, "session_meta", {"id": "voice-session"}), *records,
    ]) + "\n", encoding="utf-8")
    return {"provider": "codex", "session_id": "voice-session", "identity_hash": "a" * 64,
            "project_path": "/example/project", "last_activity_at": "2026-10-20T19:01:00Z",
            "backing_artifacts": [{"role": "transcript", "path": str(path)}]}


def _voice(second: int, role: str, text: str) -> dict:
    return _record(second, "realtime_item", {"id": f"segment-{second}",
                   "realtime_session_id": "voice-session", "type": "transcript_segment",
                   "role": role, "text": text})


# tarav.breadcrumb 891ba9df18b1
def test_native_voice_is_verbatim_queryable_and_indexed_alongside_typed_messages(tmp_path):
    row = _source(tmp_path, [
        _record(1, "response_item", {"type": "message", "role": "user",
                                   "content": [{"type": "input_text", "text": "Typed request"}]}),
        _record(2, "response_item", {"type": "message", "role": "assistant",
                                   "content": [{"type": "output_text", "text": "Typed answer"}]}),
        _record(3, "realtime_item", {"type": "realtime_session_started"}),
        _voice(4, "user", "  Keep this wording.\nExactly. "),
        _voice(5, "user", "Each support set has a User root."),
        _voice(6, "assistant", " Yes, separate support from review. "),
        _record(7, "realtime_item", {"type": "realtime_session_closed"}),
    ])
    reader = NormalModelCache(row, chatlas_root=tmp_path / "depot").build()
    messages = list(reader.iter_messages())
    assert [(m["side"], m["text"]) for m in messages] == [
        ("user", "Typed request"), ("agent", "Typed answer"),
        ("user", "  Keep this wording.\nExactly. "),
        ("user", "Each support set has a User root."),
        ("agent", " Yes, separate support from review. "),
    ]
    match, = ChatlasQueryEngine(reader).run(
        ChatlasQuery(side="user", text_contains="support set")
    ).matches
    assert [m["text"] for m in match.messages] == [
        "  Keep this wording.\nExactly. ", "Each support set has a User root.",
    ]
    assert match.turn["side"] == "user"
    assert match.started_at == "2026-10-20T19:00:04Z"
    events = list(reader.iter_events())
    voice_event = next(e for e in events if e["started_at"] == "2026-10-20T19:00:05Z")
    assert voice_event["type"] == "User.Event"
    assert voice_event["content"] == {"text": "Each support set has a User root."}
    assert voice_event["observations"][0]["source_ref"]["line"] == 6
    assert messages[3]["event_refs"][0]["event_address"] == voice_event["event_address"]
    # Existing typed context is retained; voice recording adds no inferred context links.
    assert [c["agent_event_ref"]["event_address"] for c in reader.iter_loaded_contexts()] == [
        messages[1]["event_refs"][0]["event_address"],
    ]
    index = NormalModelsIndex(chatlas_root=tmp_path / "depot")
    assert index.update([row], policy="all").indexed == ("a" * 64,)
    assert index.query("select side, text from messages where text like '%support set%'") == [
        {"side": "user", "text": "Each support set has a User root."},
    ]


@pytest.mark.parametrize("payload", [
    {"type": "realtime_session_started", "role": "user", "text": "Not speech"},
    {"type": "realtime_session_closed", "role": "assistant", "text": "Not speech"},
    {"type": "transcript_segment", "role": "tool", "text": "Unknown speaker"},
    {"type": "transcript_segment", "text": "Missing speaker"},
    {"type": "transcript_segment", "role": "user"},
    {"type": "transcript_segment", "role": "assistant", "text": None},
    {"type": "transcript_segment", "role": "user", "text": ["Not a string"]},
])
def test_voice_metadata_and_malformed_segments_do_not_fabricate_messages(tmp_path, payload):
    row = _source(tmp_path, [_record(1, "realtime_item", payload)])
    model = build_normal_model_from_row(row)
    assert model["messages"] == []
    event = model["events"][1]
    assert event["type"] == "Unresolved.Event"
    assert event["origin"] == "unresolved"
    assert "content" not in event


def test_voice_edits_keep_addresses_but_change_event_message_and_turn_hashes(tmp_path):
    before = build_normal_model_from_row(_source(tmp_path, [_voice(1, "user", "Original words.")]))
    after = build_normal_model_from_row(_source(tmp_path, [_voice(1, "user", "Amended words.")]))
    assert [m["text"] for m in before["messages"]] == ["Original words."]
    assert [m["text"] for m in after["messages"]] == ["Amended words."]
    for collection, address, digest in (
        ("events", "event_address", "event_hash"),
        ("messages", "message_address", "message_hash"),
        ("turns", "turn_address", "turn_hash"),
    ):
        # Session metadata is the first Event; the User voice is its own Turn.
        old = before[collection][-1]
        new = after[collection][-1]
        assert old[address] == new[address]
        assert old[digest] != new[digest]
