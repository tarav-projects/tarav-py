"""Canonical `event_hash` (Impl.Req 514, Slice 2).

The digest covers the event's chat content — `kind`, `producer`, `payload`,
`timestamp` — and nothing derived or positional. It is what a stored
`<hash>:<idx>` reference asserts against, so its reproducibility is the whole
property: recomputing it over a materialized tape must reproduce every stored
value.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from agentos.chatlas.normalization.session_model._claude import (
    _normalize_claude_session,
)
from agentos.chatlas.normalization.session_model.events import compute_event_hash


@dataclass(frozen=True)
class _FakeClaudeSession:
    transcript_path: Path
    source_ref_id: str | None = "src-1"


def _user(uuid: str, text: str, parent: str | None, *, ts: str) -> dict:
    return {
        "type": "user",
        "uuid": uuid,
        "version": "2.0.0",
        "parentUuid": parent,
        "timestamp": ts,
        "sessionId": "S1",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def _assistant(uuid: str, text: str, parent: str, *, ts: str) -> dict:
    return {
        "type": "assistant",
        "uuid": uuid,
        "version": "2.0.0",
        "parentUuid": parent,
        "timestamp": ts,
        "sessionId": "S1",
        "requestId": "req-1",
        "message": {
            "id": "msg-1",
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        },
    }


def _base() -> list[dict]:
    return [
        _user("u1", "the first question", None, ts="2026-07-28T10:00:00.000Z"),
        _assistant("a1", "the first answer", "u1", ts="2026-07-28T10:00:01.000Z"),
        _user("u2", "the second question", "a1", ts="2026-07-28T10:00:02.000Z"),
    ]


def _events(tmp_path: Path, name: str, records: list[dict]) -> list[dict]:
    path = tmp_path / f"{name}.jsonl"
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    result = _normalize_claude_session(_FakeClaudeSession(transcript_path=path))
    assert result is not None
    return result.events


def _by_text(events: list[dict], needle: str) -> dict:
    for event in events:
        payload = event.get("payload") or {}
        text = "".join(
            block.get("text", "") for block in (payload.get("content") or [])
        )
        if needle in text:
            return event
    raise AssertionError(f"no event carrying {needle!r}")


def test_every_event_carries_a_hash(tmp_path):
    events = _events(tmp_path, "all", _base())
    assert events
    assert all(isinstance(event.get("event_hash"), str) for event in events)


def test_recomputing_reproduces_every_stored_hash(tmp_path):
    """The standing invariant: if a hashed field ever becomes mutable after the
    hash is written, this is what catches it."""
    for event in _events(tmp_path, "recompute", _base()):
        assert compute_event_hash(event) == event["event_hash"]


def test_hash_is_stable_across_rederivation(tmp_path):
    first = _events(tmp_path, "one", _base())
    second = _events(tmp_path, "two", _base())
    assert [e["event_hash"] for e in first] == [e["event_hash"] for e in second]


def test_appending_does_not_change_earlier_hashes(tmp_path):
    before = _events(tmp_path, "before", _base())
    grown = _events(
        tmp_path,
        "after",
        _base() + [_assistant("a2", "a later answer", "u2", ts="2026-07-28T10:00:03.000Z")],
    )
    target = "the first question"
    assert _by_text(before, target)["event_hash"] == _by_text(grown, target)["event_hash"]


def test_hash_ignores_position_and_derived_fields(tmp_path):
    """An earlier turn shifts every later ordinal; content hashes must not move."""
    shifted = [
        _user("u0", "an even earlier question", None, ts="2026-07-28T09:59:00.000Z"),
        _assistant("a0", "an earlier answer", "u0", ts="2026-07-28T09:59:01.000Z"),
    ] + _base()
    shifted[2]["parentUuid"] = "a0"

    plain = _by_text(_events(tmp_path, "plain", _base()), "the second question")
    moved = _by_text(_events(tmp_path, "moved", shifted), "the second question")
    assert plain["sequence"] != moved["sequence"]
    assert plain["event_hash"] == moved["event_hash"]


def test_differing_content_differs(tmp_path):
    a = _by_text(_events(tmp_path, "a", _base()), "the first question")
    changed = _base()
    changed[0]["message"]["content"][0]["text"] = "a different question"
    b = _by_text(_events(tmp_path, "b", changed), "a different question")
    assert a["event_hash"] != b["event_hash"]
