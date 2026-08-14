# $kw: ^compaction-normalization-tests --from Compaction.Event --from Compaction.Summary --from Normal.Turn --note [CT] provider compaction fixtures converge without granting synthetic recap text user authority ^c20260807-2u
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from tarav.chatlas.event_ref import resolve_event_ref
from tarav.chatlas.normalization.session_model._claude import (
    _claude_tail_has_compaction,
    _load_claude_raw_session_records,
    _normalize_claude_session,
)
from tarav.chatlas.normalization.session_model._codex import (
    _normalize_codex_session,
)
from tarav.chatlas.normalization.session_model.events import normal_turn_id, normal_turn_kind


@dataclass(frozen=True)
class _FakeClaudeSession:
    transcript_path: Path
    source_ref_id: str | None = "source-1"


@dataclass(frozen=True)
class _FakeCodexSession:
    rollout_path: Path
    source_ref_id: str | None = "source-1"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )


def _claude_user(uuid: str, text: str, parent: str | None) -> dict:
    return {
        "type": "user",
        "uuid": uuid,
        "parentUuid": parent,
        "timestamp": "2026-08-07T10:00:00.000Z",
        "sessionId": "claude-compact",
        "version": "2.1.223",
        "message": {"role": "user", "content": text},
    }


def _claude_assistant(uuid: str, text: str, parent: str) -> dict:
    return {
        "type": "assistant",
        "uuid": uuid,
        "parentUuid": parent,
        "timestamp": "2026-08-07T10:00:01.000Z",
        "sessionId": "claude-compact",
        "version": "2.1.223",
        "requestId": f"req-{uuid}",
        "message": {
            "id": f"msg-{uuid}",
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        },
    }


def _claude_records() -> list[dict]:
    records: list[dict] = []
    parent = None
    for index in range(1, 5):
        user_uuid = f"u{index}"
        assistant_uuid = f"a{index}"
        records.append(_claude_user(user_uuid, f"turn {index}", parent))
        records.append(_claude_assistant(assistant_uuid, f"answer {index}", user_uuid))
        parent = assistant_uuid

    records.append(_claude_user("command", "/compact", parent))
    records.append(
        {
            "type": "system",
            "subtype": "compact_boundary",
            "uuid": "boundary",
            "parentUuid": None,
            "logicalParentUuid": parent,
            "timestamp": "2026-08-07T10:01:00.000Z",
            "sessionId": "claude-compact",
            "version": "2.1.223",
            "compactMetadata": {
                "trigger": "manual",
                "preTokens": 12000,
                "postTokens": 1500,
                "cumulativeDroppedTokens": 10500,
                "durationMs": 2500,
                "preservedSegment": {
                    "headUuid": "u1",
                    "anchorUuid": "summary",
                    "tailUuid": parent,
                },
                "preservedMessages": {
                    "anchorUuid": "summary",
                    "allUuids": ["u1", parent],
                },
            },
        }
    )
    records.append(
        {
            **_claude_user(
                "summary", "Synthetic recap of turns one through four.", "boundary"
            ),
            "isCompactSummary": True,
            "isVisibleInTranscriptOnly": True,
        }
    )
    parent = "summary"
    for index in range(5, 9):
        user_uuid = f"u{index}"
        assistant_uuid = f"a{index}"
        records.append(_claude_user(user_uuid, f"turn {index}", parent))
        records.append(_claude_assistant(assistant_uuid, f"answer {index}", user_uuid))
        parent = assistant_uuid
    return records


def _codex_message(message_id: str, turn_id: str, text: str) -> dict:
    return {
        "timestamp": "2026-08-07T11:00:00.000Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "id": message_id,
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
            "internal_chat_message_metadata_passthrough": {"turn_id": turn_id},
        },
    }


def _codex_records() -> list[dict]:
    messages = [
        _codex_message(f"msg-{index}", f"turn-{index}", f"turn {index}")
        for index in range(1, 5)
    ]
    retained = [record["payload"] for record in messages]
    return [
        {
            "timestamp": "2026-08-07T10:59:59.000Z",
            "type": "session_meta",
            "payload": {
                "id": "codex-compact",
                "originator": "codex_cli_rs",
                "cwd": "/tmp",
            },
        },
        *messages,
        {
            "timestamp": "2026-08-07T11:01:00.000Z",
            "type": "compacted",
            "payload": {
                "message": "",
                "replacement_history": retained,
                "window_number": 1,
                "first_window_id": "window-0",
                "previous_window_id": "window-0",
                "window_id": "window-1",
            },
        },
    ]


def _user_turn_texts(events: list[dict]) -> list[str]:
    texts = []
    for event in events:
        payload = event.get("payload") or {}
        if (
            event.get("kind") != "message"
            or payload.get("role") != "user"
            or normal_turn_kind(event) != "user"
        ):
            continue
        texts.append("".join(block.get("text", "") for block in payload["content"]))
    return texts


def test_claude_compaction_is_structural_and_summary_is_synthetic(tmp_path):
    path = tmp_path / "claude.jsonl"
    _write_jsonl(path, _claude_records())
    result = _normalize_claude_session(_FakeClaudeSession(path))
    assert result is not None

    (compaction,) = [event for event in result.events if event["kind"] == "compaction"]
    (summary,) = [
        event
        for event in result.events
        if (event.get("annotations") or {}).get("compaction_summary") is True
    ]
    assert compaction["sequence"] < summary["sequence"]
    assert (summary["payload"]["role"], summary["producer"]["type"]) == (
        "system",
        "provider",
    )
    assert summary["surfaces"]["model_input"] == "hidden"
    assert normal_turn_id(summary) is None
    assert (
        resolve_event_ref(result.events, compaction["payload"]["summary_ref"]).event
        == summary
    )
    assert len(compaction["payload"]["retained_event_refs"]) == 2
    assert not [event for event in result.events if event["kind"] == "lineage.rollback"]
    assert _user_turn_texts(result.events) == [
        f"turn {index}" for index in range(1, 9)
    ]


def test_codex_compaction_retains_event_references_without_summary(tmp_path):
    path = (
        tmp_path
        / "rollout-2026-08-07T11-00-00-019fd977-c106-7830-a17b-62d074a4bfa3.jsonl"
    )
    _write_jsonl(path, _codex_records())
    result = _normalize_codex_session(_FakeCodexSession(path))
    assert result is not None

    (compaction,) = [event for event in result.events if event["kind"] == "compaction"]
    refs = compaction["payload"]["retained_event_refs"]
    assert len(refs) == 4
    assert all(resolve_event_ref(result.events, ref).event is not None for ref in refs)
    assert "summary_ref" not in compaction["payload"]
    assert not [
        event
        for event in result.events
        if (event.get("annotations") or {}).get("compaction_summary") is True
    ]


def test_codex_content_amendment_preserves_event_places_and_count(tmp_path):
    path = (
        tmp_path
        / "rollout-2026-08-07T11-00-00-019fd977-c106-7830-a17b-62d074a4bfa3.jsonl"
    )
    before_records = _codex_records()
    _write_jsonl(path, before_records)
    before = _normalize_codex_session(_FakeCodexSession(path))
    assert before is not None

    after_records = deepcopy(before_records)
    after_records[1]["payload"]["content"][0]["text"] = "turn 1, amended"
    _write_jsonl(path, after_records)
    after = _normalize_codex_session(_FakeCodexSession(path))
    assert after is not None

    assert [event["event_address"] for event in after.events] == [
        event["event_address"] for event in before.events
    ]
    assert len(after.events) == len(before.events)
    assert [event["event_hash"] for event in after.events] != [
        event["event_hash"] for event in before.events
    ]


def test_codex_append_preserves_existing_event_address_prefix(tmp_path):
    path = (
        tmp_path
        / "rollout-2026-08-07T11-00-00-019fd977-c106-7830-a17b-62d074a4bfa3.jsonl"
    )
    before_records = _codex_records()
    _write_jsonl(path, before_records)
    before = _normalize_codex_session(_FakeCodexSession(path))
    assert before is not None

    after_records = [
        *before_records,
        _codex_message("msg-5", "turn-5", "turn 5"),
    ]
    _write_jsonl(path, after_records)
    after = _normalize_codex_session(_FakeCodexSession(path))
    assert after is not None

    assert [event["event_address"] for event in after.events[: len(before.events)]] == [
        event["event_address"] for event in before.events
    ]


def test_claude_compaction_tail_requires_full_derivation(tmp_path):
    path = tmp_path / "claude.jsonl"
    _write_jsonl(path, _claude_records())
    raw = _load_claude_raw_session_records(path, source_ref_id="source-1")

    assert _claude_tail_has_compaction(raw.records)
