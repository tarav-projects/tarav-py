# $kw: ^test-event-envelope-addressing --from Chatlas.Session.Model.Contract --from Chatlas.Session.Model.Tests --note [CT] assembled tapes reject retired event_id while preserving sequence and event_hash ^c20260728-16u
"""Envelope closure over a fully assembled tape (Impl.Req 514, Slice 1).

`enforce_event_envelope` runs inside each provider assembler, before
`attach_tape_provenance` adds its keys — so provenance leakage is invisible to
it. This asserts closure on the finished model instead: every top-level key on
every event is declared.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tarav.chatlas.normalization.session_model._claude import (
    _normalize_claude_session,
)
from tarav.chatlas.normalization.session_model.events import (
    SEMANTIC_EVENT_ENVELOPE_KEYS,
)


@dataclass(frozen=True)
class _FakeClaudeSession:
    transcript_path: Path
    source_ref_id: str | None = "src-1"


def _records() -> list[dict]:
    return [
        {
            "type": "user",
            "uuid": "u1",
            "version": "2.0.0",
            "parentUuid": None,
            "timestamp": "2026-07-28T10:00:00.000Z",
            "sessionId": "S1",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "a question"}],
            },
        },
        {
            "type": "assistant",
            "uuid": "a1",
            "version": "2.0.0",
            "parentUuid": "u1",
            "timestamp": "2026-07-28T10:00:01.000Z",
            "sessionId": "S1",
            "requestId": "req-1",
            "message": {
                "id": "msg-1",
                "role": "assistant",
                "content": [{"type": "text", "text": "an answer"}],
            },
        },
    ]


def _events(tmp_path: Path) -> list[dict]:
    path = tmp_path / "session.jsonl"
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in _records()), encoding="utf-8"
    )
    result = _normalize_claude_session(_FakeClaudeSession(transcript_path=path))
    assert result is not None
    return result.events


def test_assembled_tape_carries_only_declared_envelope_keys(tmp_path):
    events = _events(tmp_path)
    assert events
    undeclared: dict[str, int] = {}
    for event in events:
        for key in set(event) - SEMANTIC_EVENT_ENVELOPE_KEYS:
            undeclared[key] = undeclared.get(key, 0) + 1
    assert not undeclared, f"undeclared top-level event keys: {sorted(undeclared)}"


def test_assembled_tape_has_sequence_but_no_retired_event_id(tmp_path):
    events = _events(tmp_path)

    assert all(isinstance(event.get("sequence"), int) for event in events)
    assert all(isinstance(event.get("event_address"), str) for event in events)
    assert len({event["event_address"] for event in events}) == len(events)
    assert all("event_id" not in event for event in events)


def test_delta_provenance_rides_under_extras(tmp_path):
    """Provenance is derivation bookkeeping, not chat semantics — it lives in
    the `extras` namespace, never on the envelope top level."""
    events = _events(tmp_path)
    for event in events:
        for key in ("source_hash", "chain_hash", "final"):
            assert key not in event
        extras = event.get("extras")
        assert isinstance(extras, dict)
        assert set(extras) >= {"source_hash", "chain_hash"}
        assert "final" not in extras
        assert isinstance(event.get("closed"), dict)
