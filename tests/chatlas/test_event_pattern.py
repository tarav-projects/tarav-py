# $kw: ^test-event-pattern-refs --from Chatlas.Session.Model.Tests --from Session.Event.Tape --note [CT] Event.Pattern accepts and projects Event.Ref objects and rejects event_id predicates ^c20260728-16u
from __future__ import annotations

import pytest

from tarav.chatlas.event_pattern import (
    EventPattern,
    EventPatternError,
    alphanumeric_material,
    evaluate_event_pattern,
)
from tarav.chatlas.event_ref import event_ref
from tarav.chatlas.normalization.session_model.events import compute_event_hash


def _event(
    sequence: int,
    role: str,
    text: str,
) -> dict[str, object]:
    event: dict[str, object] = {
        "event_address": f"{sequence:064x}",
        "sequence": sequence,
        "kind": "message",
        "producer": {"type": role},
        "payload": {"role": role, "content": [{"type": "text", "text": text}]},
        "timestamp": f"2026-07-28T10:00:{sequence:02d}.000Z",
        "annotations": {"normal_turn": {"id": f"turn-{sequence}", "kind": role}},
    }
    event["event_hash"] = compute_event_hash(event)
    return event


def _model() -> dict[str, object]:
    return {
        "schema_version": 5,
        "session": {"identity_hash": "session-a"},
        "chat": {
            "events": [
                _event(1, "assistant", "candidate: POI.Class"),
                {
                    "sequence": 2,
                    "kind": "tool",
                    "payload": {"name": "rg"},
                },
                _event(3, "user", "::approve POI.Class"),
                _event(4, "assistant", "candidate: POI.Instance"),
                _event(5, "user", "::approve POI.Instance"),
            ]
        },
    }


def _pattern(**overrides: object) -> EventPattern:
    payload: dict[str, object] = {
        "steps": [
            {"role": "assistant", "text_contains": "candidate:"},
            {"role": "user", "text_exact": "::approve POI.Class"},
        ],
        "relation": "next_turn",
        "select": "all",
        "project": "match",
        "cardinality": "many",
    }
    payload.update(overrides)
    return EventPattern.from_dict(payload)


def test_adjacent_visible_turn_pattern_ignores_non_message_events() -> None:
    matches = evaluate_event_pattern(_model(), _pattern())
    events = _model()["chat"]["events"]

    assert matches == ((event_ref(events[0]), event_ref(events[2])),)


def test_latest_and_last_projection_select_authoritative_event_refs() -> None:
    pattern = _pattern(
        steps=[
            {"role": "assistant", "text_contains": "candidate:"},
            {"role": "user", "text_contains": "::approve"},
        ],
        select="latest",
        project="last",
        cardinality="one",
    )

    event = _model()["chat"]["events"][4]
    assert evaluate_event_pattern(_model(), pattern) == ((event_ref(event),),)


def test_event_ref_predicate_matches_one_exact_event() -> None:
    model = _model()
    event = model["chat"]["events"][2]
    pattern = EventPattern.from_dict({"steps": [{"event_ref": event_ref(event)}]})

    assert evaluate_event_pattern(model, pattern) == ((event_ref(event),),)


def test_turn_kind_predicate_selects_normalized_user_input_semantics() -> None:
    model = _model()
    user_events = [model["chat"]["events"][2], model["chat"]["events"][4]]
    pattern = EventPattern.from_dict({"steps": [{"turn_kind": "user"}]})

    assert evaluate_event_pattern(model, pattern) == tuple(
        (event_ref(event),) for event in user_events
    )


def test_alphanumeric_material_ignores_case_punctuation_and_whitespace() -> None:
    assert alphanumeric_material("  Natural.Placement: one\nclaim! ") == (
        "naturalplacementoneclaim"
    )

    pattern = EventPattern.from_dict(
        {
            "steps": [
                {
                    "producer_type": "user",
                    "role": "user",
                    "text_alphanumeric_contains": "APPROVE, poi class!",
                    "text_regex": r"approve\s+POI\.Class",
                    "timestamp_after": "2026-07-28T10:00:02Z",
                    "timestamp_before": "2026-07-28T10:00:04Z",
                }
            ]
        }
    )

    assert evaluate_event_pattern(_model(), pattern) == (
        (event_ref(_model()["chat"]["events"][2]),),
    )


def test_cardinality_one_rejects_multiple_matches() -> None:
    pattern = _pattern(
        steps=[
            {"role": "assistant", "text_contains": "candidate:"},
            {"role": "user", "text_contains": "::approve"},
        ],
        cardinality="one",
    )

    with pytest.raises(EventPatternError, match="expected exactly one"):
        evaluate_event_pattern(_model(), pattern)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"steps": []},
        {"steps": [{"unknown": "value"}]},
        {"steps": [{"event_id": "event-1"}]},
        {"steps": [{"event_ref": {"event_address": "place", "event_hash": "short"}}]},
        {"steps": [{"role": "user"}], "relation": "eventually"},
        {"steps": [{"role": "user"}], "select": "middle"},
        {"steps": [{"text_regex": "["}]},
        {"steps": [{"timestamp_after": "not-a-timestamp"}]},
    ],
)
def test_invalid_pattern_is_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(EventPatternError):
        EventPattern.from_dict(payload)
