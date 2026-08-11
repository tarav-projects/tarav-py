"""Normal.Turn identity (Impl.Req 513, Slice 2).

A turn's identity must not be positional: adding an earlier turn, or otherwise
re-segmenting the tape ahead of it, must leave a later turn's identity
unchanged. This is the direct regression test for the defect that motivated the
work — anchors keyed on a positional value came to point at other turns.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from agentos.chatlas.normalization.session_model._claude import (
    _normalize_claude_session,
)
from agentos.chatlas.normalization.session_model.events import normal_turn_id


@dataclass(frozen=True)
class _FakeClaudeSession:
    transcript_path: Path
    source_ref_id: str | None = "src-1"


def _user_record(uuid: str, text: str, parent: str | None) -> dict:
    return {
        "type": "user",
        "uuid": uuid,
        "version": "2.0.0",
        "parentUuid": parent,
        "timestamp": "2026-07-26T10:00:00.000Z",
        "sessionId": "S1",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def _assistant_record(uuid: str, text: str, parent: str) -> dict:
    return {
        "type": "assistant",
        "uuid": uuid,
        "version": "2.0.0",
        "parentUuid": parent,
        "timestamp": "2026-07-26T10:00:01.000Z",
        "sessionId": "S1",
        "requestId": "req-1",
        "message": {
            "id": "msg-1",
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        },
    }


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )


def _events(tmp_path: Path, name: str, records: list[dict]) -> list[dict]:
    path = tmp_path / f"{name}.jsonl"
    _write_jsonl(path, records)
    result = _normalize_claude_session(_FakeClaudeSession(transcript_path=path))
    assert result is not None
    return result.events


def _turn_of(events: list[dict], needle: str) -> str | None:
    for event in events:
        payload = event.get("payload") or {}
        if payload.get("role") != "user":
            continue
        text = "".join(
            block.get("text", "") for block in (payload.get("content") or [])
        )
        if needle in text:
            return normal_turn_id(event)
    raise AssertionError(f"no user event carrying {needle!r}")


LATER = "the later question"


def test_earlier_turn_does_not_shift_a_later_turn_identity(tmp_path):
    """The regression: an extra turn ahead of the target must not renumber it."""
    without = [
        _user_record("u1", "the first question", None),
        _assistant_record("a1", "first answer", "u1"),
        _user_record("u2", LATER, "a1"),
    ]
    with_extra = [
        _user_record("u0", "an even earlier question", None),
        _assistant_record("a0", "earlier answer", "u0"),
        *[dict(record) for record in without],
    ]
    with_extra[2]["parentUuid"] = "a0"

    identity_without = _turn_of(_events(tmp_path, "without", without), LATER)
    identity_with = _turn_of(_events(tmp_path, "with", with_extra), LATER)

    assert identity_without is not None
    assert identity_without == identity_with


def test_turn_identity_is_stable_across_rederivation(tmp_path):
    records = [
        _user_record("u1", "the first question", None),
        _assistant_record("a1", "first answer", "u1"),
        _user_record("u2", LATER, "a1"),
    ]
    first = _events(tmp_path, "one", records)
    second = _events(tmp_path, "two", records)
    assert _turn_of(first, LATER) == _turn_of(second, LATER)


def test_turn_identity_is_not_a_tape_ordinal(tmp_path):
    records = [
        _user_record("u1", "the first question", None),
        _assistant_record("a1", "first answer", "u1"),
        _user_record("u2", LATER, "a1"),
    ]
    identity = _turn_of(_events(tmp_path, "ordinal", records), LATER)
    assert identity is not None
    assert not identity.startswith("interaction-")


def test_user_and_assistant_are_independent_turns(tmp_path):
    records = [
        _user_record("u1", "the first question", None),
        _assistant_record("a1", "first answer", "u1"),
    ]
    events = _events(tmp_path, "shared", records)
    turns = {
        normal_turn_id(event)
        for event in events
        if event.get("kind") == "message"
    }
    assert None not in turns
    assert len(turns) == 2

    user = next(
        event for event in events if (event.get("payload") or {}).get("role") == "user"
    )
    assistant = next(
        event
        for event in events
        if (event.get("payload") or {}).get("role") == "assistant"
    )
    assert normal_turn_id(assistant) == f"{normal_turn_id(user)}:assistant"
    assert "turn_id" not in user
    assert "turn_id" not in assistant
