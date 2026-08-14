from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tarav.chatlas.normalization.session_model._claude import (
    _normalize_claude_session,
)


@dataclass(frozen=True)
class _FakeClaudeSession:
    transcript_path: Path
    source_ref_id: str | None = "src-1"


def _user_record(uuid: str, text: str, parent: str | None = None) -> dict:
    return {
        "type": "user",
        "uuid": uuid,
        "version": "2.0.0",
        "parentUuid": parent,
        "timestamp": f"2026-07-12T10:00:0{uuid[-1]}.000Z",
        "sessionId": "S1",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def _assistant_record(
    uuid: str,
    text: str,
    *,
    parent: str,
    message_id: str,
    stop_reason: str | None,
) -> dict:
    message: dict = {
        "id": message_id,
        "role": "assistant",
        "model": "claude-test",
        "content": [{"type": "text", "text": text}],
    }
    if stop_reason is not None:
        message["stop_reason"] = stop_reason
    return {
        "type": "assistant",
        "uuid": uuid,
        "version": "2.0.0",
        "parentUuid": parent,
        "timestamp": f"2026-07-12T10:00:0{uuid[-1]}.500Z",
        "sessionId": "S1",
        "requestId": f"req-{message_id}",
        "message": message,
    }


def _closed_turn_records() -> list[dict]:
    return [
        _user_record("u1", "first question"),
        _assistant_record(
            "a2", "first answer", parent="u1", message_id="msg1", stop_reason="end_turn"
        ),
    ]


def _second_closed_turn_records() -> list[dict]:
    return [
        _user_record("u5", "middle question", parent="a2"),
        _assistant_record(
            "a6", "middle answer", parent="u5", message_id="msg3", stop_reason="end_turn"
        ),
    ]


def _open_turn_records(parent: str = "a2") -> list[dict]:
    return [
        _user_record("u3", "second question", parent=parent),
        _assistant_record(
            "a4", "partial answer", parent="u3", message_id="msg2", stop_reason=None
        ),
    ]


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )


def _normalize(path: Path):
    result = _normalize_claude_session(_FakeClaudeSession(transcript_path=path))
    assert result is not None
    return result


def test_rederivation_is_hash_stable(tmp_path):
    path = tmp_path / "session.jsonl"
    _write_jsonl(path, _closed_turn_records() + _open_turn_records())

    first = _normalize(path).events
    second = _normalize(path).events
    assert first == second
    for event in first:
        assert event["extras"]["source_hash"]
        assert event["extras"]["chain_hash"]
        assert "final" not in event["extras"]
        assert isinstance(event["closed"]["estimate"], bool)


def test_provider_closure_estimate_is_explicitly_best_effort(tmp_path):
    path = tmp_path / "session.jsonl"
    _write_jsonl(path, _closed_turn_records() + _open_turn_records())
    events = _normalize(path).events

    estimate_by_text: dict[str, bool] = {}
    for event in events:
        text = json.dumps(event.get("payload", ""))
        for needle in ("first question", "first answer", "partial answer"):
            if needle in text:
                estimate_by_text[needle] = event["closed"]["estimate"]
    assert estimate_by_text["first question"] is True
    assert estimate_by_text["first answer"] is True
    assert estimate_by_text["partial answer"] is False


def test_append_preserves_the_existing_event_address_prefix(tmp_path):
    path = tmp_path / "session.jsonl"
    base = _closed_turn_records() + _second_closed_turn_records()
    _write_jsonl(path, base)
    before = _normalize(path).events
    addresses_before = [event["event_address"] for event in before]

    _write_jsonl(path, base + _open_turn_records(parent="a6"))
    after = _normalize(path).events

    assert [event["event_address"] for event in after[: len(before)]] == addresses_before


def test_mutated_frozen_record_diverges_source_hash(tmp_path):
    path = tmp_path / "session.jsonl"
    records = _closed_turn_records() + _open_turn_records()
    _write_jsonl(path, records)
    before = _normalize(path).events

    records[0]["message"]["content"][0]["text"] = "first question, edited"
    _write_jsonl(path, records)
    after = _normalize(path).events

    def hash_of(events, needle):
        for event in events:
            if needle in json.dumps(event.get("payload", "")):
                return event["extras"]["source_hash"]
        raise AssertionError(f"no event for {needle}")

    assert hash_of(before, "first question") != hash_of(after, "first question")
    assert hash_of(before, "first answer") == hash_of(after, "first answer")


def test_content_amendment_preserves_event_places_and_count(tmp_path):
    path = tmp_path / "session.jsonl"
    records = _closed_turn_records() + _second_closed_turn_records()
    _write_jsonl(path, records)
    before = _normalize(path).events

    records[0]["message"]["content"][0]["text"] = "first question, amended"
    _write_jsonl(path, records)
    after = _normalize(path).events

    assert [event["event_address"] for event in after] == [
        event["event_address"] for event in before
    ]
    assert len(after) == len(before)
    assert [event["event_hash"] for event in after] != [
        event["event_hash"] for event in before
    ]
