# $kw: ^test-event-ref-traceability --from Chatlas.Session.Model.Contract --from Chatlas.Session.Model.Tests --note [CT] traceability reports matched, amended, missing, and malformed stored Event.Ref assertions ^c20260807-16u
"""Stored `event_refs` are `Event.Ref` objects, and the checksum earns its place
here (Impl.Req 514, Slice 5).

Intra-document joins use stable places. Reordering cannot change their target;
content amendment keeps the address resolvable while making the stored hash
assertion disagree, which the validator surfaces.
"""

from __future__ import annotations

from agentos.chatlas.event_ref import event_ref
from agentos.chatlas.normalization.session_model.events import compute_event_hash
from agentos.chatlas.normalization.session_model.traceability import (
    standard_model_traceability_errors,
)


def _event(sequence: int, text: str) -> dict[str, object]:
    event: dict[str, object] = {
        "event_address": f"{sequence:064x}",
        "sequence": sequence,
        "kind": "message",
        "producer": {"type": "assistant"},
        "payload": {"role": "assistant", "content": [{"type": "text", "text": text}]},
        "timestamp": f"2026-07-28T10:00:{sequence:02d}.000Z",
        "source_refs": [{"source_ref_id": "src-1", "record_index": sequence}],
    }
    event["event_hash"] = compute_event_hash(event)
    return event


def _payload(events: list[dict[str, object]], refs: list[dict[str, object]]) -> dict:
    return {
        "sources": [{"source_ref_id": "src-1"}],
        "chat": {
            "events": events,
            "messages": [],
            "model_runs": [
                {
                    "model_run_id": "run-1",
                    "event_refs": refs,
                }
            ],
            "tool_invocations": [],
            "usage": [],
        },
    }


def test_matching_refs_produce_no_errors():
    events = [_event(1, "alpha"), _event(2, "beta"), _event(3, "gamma")]
    refs = [event_ref(events[1])]
    assert standard_model_traceability_errors(_payload(events, refs)) == []


def test_a_ref_survives_positional_reordering():
    events = [_event(1, "alpha"), _event(2, "beta"), _event(3, "gamma")]
    refs = [event_ref(events[2])]
    events[1], events[2] = events[2], events[1]
    events[1]["sequence"], events[2]["sequence"] = 2, 3

    assert standard_model_traceability_errors(_payload(events, refs)) == []


def test_a_ref_to_amended_content_is_reported_as_amended():
    events = [_event(1, "alpha")]
    refs = [event_ref(events[0])]
    events[0]["payload"] = {
        "role": "assistant",
        "content": [{"type": "text", "text": "amended"}],
    }
    events[0]["event_hash"] = compute_event_hash(events[0])

    errors = standard_model_traceability_errors(_payload(events, refs))

    assert len(errors) == 1
    assert "chat.model_runs[0].event_refs[0]" in errors[0]
    assert "amended" in errors[0]


def test_a_ref_whose_event_is_gone_is_reported_as_missing():
    events = [_event(1, "alpha"), _event(2, "beta")]
    refs = [event_ref(_event(3, "gamma"))]

    errors = standard_model_traceability_errors(_payload(events, refs))

    assert len(errors) == 1
    assert "missing" in errors[0]


def test_a_ref_must_be_an_object_not_a_bare_id():
    events = [_event(1, "alpha")]

    errors = standard_model_traceability_errors(_payload(events, ["event-1"]))

    assert len(errors) == 1
    assert "must be an Event.Ref object" in errors[0]


def test_a_referenced_event_still_needs_source_refs():
    events = [_event(1, "alpha")]
    refs = [event_ref(events[0])]
    events[0].pop("source_refs")

    errors = standard_model_traceability_errors(_payload(events, refs))

    assert any("without source_refs" in error for error in errors)
