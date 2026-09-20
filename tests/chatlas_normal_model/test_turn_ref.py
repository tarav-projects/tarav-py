from __future__ import annotations

from copy import deepcopy

from tarav.chatlas.normal_model.turn_ref import (
    chat_turn_ref,
    compute_chat_turn_address,
    compute_chat_turn_hash,
    resolve_chat_turn_ref,
)


def _turn() -> dict[str, object]:
    turn = {
        "type": "Chat.Turn",
        "turn_address": compute_chat_turn_address(
            provider="codex",
            scope="session-one",
            place={"first_event_address": "a" * 64},
        ),
        "side": "user",
        "event_refs": [
            {"event_address": "a" * 64, "event_hash": "b" * 64},
        ],
        "message_refs": [
            {"message_address": "c" * 64, "message_hash": "d" * 64},
        ],
    }
    turn["turn_hash"] = compute_chat_turn_hash(
        turn,
        opaque_payload_hashes=["e" * 64],
    )
    return turn


def test_turn_ref_resolves_place_separately_from_current_state() -> None:
    turn = _turn()
    ref = chat_turn_ref(turn)

    assert resolve_chat_turn_ref([turn], ref)["standing"] == "MATCHED"

    amended = deepcopy(turn)
    amended["turn_hash"] = compute_chat_turn_hash(
        amended,
        opaque_payload_hashes=["f" * 64],
    )
    assert resolve_chat_turn_ref([amended], ref)["standing"] == "AMENDED"
    assert resolve_chat_turn_ref([], ref)["standing"] == "MISSING"
