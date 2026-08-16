from __future__ import annotations

from copy import deepcopy
from inspect import signature

from tarav.chatlas2.event_ref import (
    compute_event_address,
    compute_event_hash,
    event_ref,
    resolve_event_ref,
)


def _event(*, text: str = "hello", native_id: str = "message-1") -> dict[str, object]:
    event: dict[str, object] = {
        "class": "User.Event",
        "event_address": compute_event_address(
            provider="codex",
            scope="session-1",
            place={"record_index": 3},
        ),
        "started_at": "2026-08-15T00:00:03Z",
        "origin": "user",
        "record": {
            "timestamp": "2026-08-15T00:00:03Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "id": native_id,
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        },
        "observations": [],
    }
    event["event_hash"] = compute_event_hash(event)
    return event


def test_event_address_is_place_only_and_event_hash_is_current_content() -> None:
    original = _event()
    amended = _event(text="amended")
    native_id_drift = _event(native_id="message-2")

    assert original["event_address"] == amended["event_address"]
    assert original["event_hash"] != amended["event_hash"]
    assert original["event_hash"] == native_id_drift["event_hash"]

    moved = deepcopy(original)
    moved["event_address"] = compute_event_address(
        provider="codex",
        scope="session-1",
        place={"record_index": 4},
    )
    assert moved["event_address"] != original["event_address"]


def test_event_address_has_no_raw_model_version_axis() -> None:
    assert "raw_model_version" not in signature(compute_event_address).parameters


def test_event_ref_resolution_is_stateless_and_consumer_neutral() -> None:
    original = _event()
    current = _event(text="amended")
    stored_ref = event_ref(original)

    matched = resolve_event_ref([original], stored_ref)
    amended = resolve_event_ref([current], stored_ref)
    missing = resolve_event_ref([], stored_ref)

    assert matched == {
        "class": "Event.Ref.Resolution",
        "standing": "MATCHED",
        "event": original,
    }
    assert amended == {
        "class": "Event.Ref.Resolution",
        "standing": "AMENDED",
        "event": current,
    }
    assert missing == {
        "class": "Event.Ref.Resolution",
        "standing": "MISSING",
        "event": None,
    }
