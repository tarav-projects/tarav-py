from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.chatlas.normal_turn import normal_turn_ref, resolve_normal_turn_ref
from agentos.chatlas.normalization.session_model._copilot import (
    _CopilotRawEvent,
    _CopilotRawEvents,
    _copilot_append_run_event,
    _copilot_events_from_raw_events,
)
from agentos.chatlas.normalization.session_model.events import (
    SemanticEventBuilder,
    compute_event_group_hash,
    compute_event_hash,
    finalize_normal_turn_annotations,
    normal_turn_id,
    semantic_event_producer,
    semantic_event_surfaces,
    set_normal_turn_id,
)


def _event(text: str, *, turn_id: str = "turn-1") -> dict[str, object]:
    builder = SemanticEventBuilder()
    return builder.append(
        kind="message",
        producer=semantic_event_producer("human"),
        surfaces=semantic_event_surfaces(transcript="visible"),
        turn_id=turn_id,
        payload={
            "role": "user",
            "visibility": "conversation",
            "content": [{"type": "text", "text": text}],
        },
        timestamp="2026-07-31T10:00:00Z",
    )


def test_event_hash_excludes_annotations() -> None:
    event = _event("hello")
    digest = compute_event_hash(event)
    set_normal_turn_id(event, "renamed")
    event["annotations"]["another_group"] = {"id": "anything"}
    assert compute_event_hash(event) == digest


def test_event_group_hash_uses_ordered_full_event_hashes() -> None:
    first = _event("first")
    second = _event("second")
    digest = compute_event_group_hash([first, second])
    set_normal_turn_id(first, "renamed")
    set_normal_turn_id(second, "renamed")
    assert compute_event_group_hash([first, second]) == digest
    assert compute_event_group_hash([second, first]) != digest


def test_normal_turn_ref_locates_and_verifies_group() -> None:
    event = _event("hello")
    ref = normal_turn_ref("session-a", [event])
    model = {"chat": {"events": [event]}}

    parsed, events = resolve_normal_turn_ref(ref, model)

    assert parsed == ref
    assert events == [event]
    assert parsed == {
        "session": "session-a",
        "turn_id": normal_turn_id(event),
        "turn_hash": compute_event_group_hash([event]),
        "at": "2026-07-31T10:00:00Z",
    }

    drifted = deepcopy(ref)
    drifted["turn_hash"] = "0" * 64
    with pytest.raises(CliError, match="turn_hash mismatch"):
        resolve_normal_turn_ref(drifted, model)


def test_copilot_run_native_id_does_not_replace_semantic_group() -> None:
    builder = SemanticEventBuilder()
    raw_event = _CopilotRawEvent(
        event_index=1,
        line=1,
        event_id="event-1",
        parent_id=None,
        timestamp="2026-07-31T10:00:00Z",
        event_type="runStart",
        data={"turnId": "provider-turn", "interactionId": "interaction-1"},
        source_refs=[],
    )

    _copilot_append_run_event(
        event_builder=builder,
        raw_event=raw_event,
        turn_id="semantic-turn",
        kind="run.start",
    )
    events = builder.events
    finalize_normal_turn_annotations(events)

    assert normal_turn_id(events[0]) == "semantic-turn:assistant"
    assert events[0]["native"]["turn_id"] == "provider-turn"


def _copilot_user_raw_event(
    event_index: int, text: str, *, event_id: str
) -> _CopilotRawEvent:
    return _CopilotRawEvent(
        event_index=event_index,
        line=event_index,
        event_id=event_id,
        parent_id=None,
        timestamp=f"2026-07-31T10:00:0{event_index}Z",
        event_type="user.message",
        data={"content": text, "interactionId": f"interaction-{event_index}"},
        source_refs=[
            {
                "source_ref_id": "source-1",
                "event_index": event_index,
                "line": event_index,
            }
        ],
    )


def _copilot_events(raw_events: list[_CopilotRawEvent]) -> list[dict[str, object]]:
    result = _copilot_events_from_raw_events(
        _CopilotRawEvents(
            path=Path("events.jsonl"),
            source_ref_id="source-1",
            events=raw_events,
            warnings=[],
        )
    )
    return result["events"]


def test_copilot_content_amendment_preserves_event_places_and_count() -> None:
    before = _copilot_events([_copilot_user_raw_event(1, "hello", event_id="e1")])
    after = _copilot_events(
        [_copilot_user_raw_event(1, "hello, amended", event_id="e1")]
    )

    assert [event["event_address"] for event in after] == [
        event["event_address"] for event in before
    ]
    assert len(after) == len(before)
    assert [event["event_hash"] for event in after] != [
        event["event_hash"] for event in before
    ]


def test_copilot_append_preserves_existing_event_address_prefix() -> None:
    first = _copilot_user_raw_event(1, "hello", event_id="e1")
    before = _copilot_events([first])
    after = _copilot_events(
        [first, _copilot_user_raw_event(2, "again", event_id="e2")]
    )

    assert [event["event_address"] for event in after[: len(before)]] == [
        event["event_address"] for event in before
    ]
