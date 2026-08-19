from __future__ import annotations

from copy import deepcopy
from inspect import signature

from tarav.chatlas.lossless.event_ref import (
    compute_event_address,
    compute_event_hash,
    event_ref,
    resolve_event_ref,
)


def _event(*, text: str = "hello", raw_marker: str = "first") -> dict[str, object]:
    event: dict[str, object] = {
        "class": "User.Event",
        "event_address": compute_event_address(
            provider="codex",
            scope="session-1",
            place={"record_index": 3},
        ),
        "started_at": "2026-08-15T00:00:03Z",
        "origin": "user",
        "content": {"text": text},
        "raw": {"provider_marker": raw_marker},
        "observations": [],
    }
    event["event_hash"] = compute_event_hash(event)
    return event


def test_event_address_is_place_only_and_event_hash_is_current_content() -> None:
    original = _event()
    amended = _event(text="amended")
    raw_drift = _event(raw_marker="second")

    assert original["event_address"] == amended["event_address"]
    assert original["event_hash"] != amended["event_hash"]
    assert original["event_hash"] == raw_drift["event_hash"]

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


def test_a_stored_ref_survives_reordering_of_the_event_list() -> None:
    """Carried from the retired Chatlas1 traceability suite (Impl.Req 514, Slice 5).

    `Event.Address` is a place, not a position, so resolution must scan by address.
    A positional lookup would pass every other test in this file and fail only here.
    """
    first = _event(text="alpha")
    second = deepcopy(first)
    second["event_address"] = compute_event_address(
        provider="codex", scope="session-1", place={"record_index": 4}
    )
    second["content"] = {"text": "beta"}
    second["event_hash"] = compute_event_hash(second)

    stored_ref = event_ref(second)

    assert resolve_event_ref([first, second], stored_ref)["standing"] == "MATCHED"
    assert resolve_event_ref([second, first], stored_ref)["standing"] == "MATCHED"
    assert resolve_event_ref([second, first], stored_ref)["event"] == second
