from __future__ import annotations

from copy import deepcopy
from inspect import signature

from tarav.chatlas.normal_model.message_ref import (
    chat_message_ref,
    compute_chat_message_address,
    compute_chat_message_hash,
    resolve_chat_message_ref,
)


def _message(
    *,
    side: str = "user",
    first_hash: str = "1" * 64,
    second_hash: str = "2" * 64,
) -> dict[str, object]:
    message: dict[str, object] = {
        "type": "Chat.Message",
        "message_address": compute_chat_message_address(
            provider="codex",
            scope="session-1",
            place={"record_index": 3},
        ),
        "side": side,
        "text": "hello",
        "event_refs": [
            {"event_address": "a" * 64, "event_hash": first_hash},
            {"event_address": "b" * 64, "event_hash": second_hash},
        ],
    }
    message["message_hash"] = compute_chat_message_hash(message)
    return message


def test_message_address_is_place_only_and_hash_covers_side_and_ordered_event_hashes() -> None:
    original = _message()
    amended = _message(first_hash="3" * 64)
    reclassified = _message(side="agent")
    reordered = _message(first_hash="2" * 64, second_hash="1" * 64)

    assert original["message_address"] == amended["message_address"]
    assert original["message_hash"] != amended["message_hash"]
    assert original["message_hash"] != reclassified["message_hash"]
    assert original["message_hash"] != reordered["message_hash"]

    provenance_drift = deepcopy(original)
    provenance_drift["diagnostic"] = "ignored"
    assert compute_chat_message_hash(provenance_drift) == original["message_hash"]


def test_message_address_has_no_raw_model_version_axis() -> None:
    assert "raw_model_version" not in signature(
        compute_chat_message_address
    ).parameters


def test_chat_message_ref_resolution_is_stateless_and_consumer_neutral() -> None:
    original = _message()
    current = _message(first_hash="3" * 64)
    stored_ref = chat_message_ref(original)

    assert resolve_chat_message_ref([original], stored_ref) == {
        "standing": "MATCHED",
        "message": original,
    }
    assert resolve_chat_message_ref([current], stored_ref) == {
        "standing": "AMENDED",
        "message": current,
    }
    assert resolve_chat_message_ref([], stored_ref) == {
        "standing": "MISSING",
        "message": None,
    }
