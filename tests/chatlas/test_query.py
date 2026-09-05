from __future__ import annotations

from copy import deepcopy

import pytest

from tarav.chatlas.query import (
    ChatlasQuery,
    ChatlasQueryEngine,
    ChatlasQueryError,
)


TURN_ONE_HASH = "a" * 63 + "1"
TURN_TWO_HASH = "b" * 63 + "2"
MESSAGE_ONE_ADDRESS = "c" * 64
MESSAGE_TWO_ADDRESS = "d" * 64
MESSAGE_ONE_HASH = "e" * 64
MESSAGE_TWO_HASH = "f" * 64


def _turn(
    turn_hash: str,
    *,
    address: str,
    side: str = "user",
    message_refs: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "class": "Chat.Turn",
        "turn_address": address,
        "turn_hash": turn_hash,
        "side": side,
        "event_refs": [],
        "message_refs": message_refs or [],
    }


def _message(
    address: str, digest: str, text: str, *, side: str = "user"
) -> dict[str, object]:
    return {
        "class": "Chat.Message",
        "message_address": address,
        "message_hash": digest,
        "side": side,
        "event_refs": [],
        "text": text,
    }


class Reader:
    def __init__(
        self,
        *,
        turns: list[dict[str, object]],
        messages: list[dict[str, object]],
    ) -> None:
        self._turns = turns
        self._messages = messages

    def model_header(self) -> dict[str, object]:
        return {
            "class": "tarav.chatlas.normal_model",
            "schema_version": 1,
            "session": {
                "provider": "codex",
                "session_id": "session-one",
                "identity_hash": "0" * 64,
            },
        }

    def iter_turns(self):
        yield from deepcopy(self._turns)

    def iter_messages(self):
        yield from deepcopy(self._messages)


def test_query_resolves_a_turn_prefix_and_assembles_messages_in_reference_order() -> (
    None
):
    first_ref = {
        "message_address": MESSAGE_ONE_ADDRESS,
        "message_hash": MESSAGE_ONE_HASH,
    }
    second_ref = {
        "message_address": MESSAGE_TWO_ADDRESS,
        "message_hash": MESSAGE_TWO_HASH,
    }
    reader = Reader(
        turns=[
            _turn(
                TURN_ONE_HASH,
                address="1" * 64,
                message_refs=[second_ref, first_ref],
            )
        ],
        messages=[
            _message(MESSAGE_ONE_ADDRESS, MESSAGE_ONE_HASH, "first stored"),
            _message(MESSAGE_TWO_ADDRESS, MESSAGE_TWO_HASH, "second stored"),
        ],
    )

    result = ChatlasQueryEngine(reader).run(
        ChatlasQuery(turn_hash_prefixes=(TURN_ONE_HASH[:8],))
    )

    assert result.session["session_id"] == "session-one"
    assert len(result.findings) == 1
    assert result.findings[0].turn["turn_hash"] == TURN_ONE_HASH
    assert [item["text"] for item in result.findings[0].messages] == [
        "second stored",
        "first stored",
    ]


def test_query_preserves_requested_prefix_order() -> None:
    reader = Reader(
        turns=[
            _turn(TURN_ONE_HASH, address="1" * 64),
            _turn(TURN_TWO_HASH, address="2" * 64),
        ],
        messages=[],
    )

    result = ChatlasQueryEngine(reader).run(
        ChatlasQuery(turn_hash_prefixes=(TURN_TWO_HASH[:8], TURN_ONE_HASH[:8]))
    )

    assert [item.prefix for item in result.findings] == [
        TURN_TWO_HASH[:8],
        TURN_ONE_HASH[:8],
    ]


@pytest.mark.parametrize("prefix", ["", "xyz", "A" * 8, "a" * 65])
def test_query_rejects_malformed_turn_hash_prefixes(prefix: str) -> None:
    reader = Reader(turns=[], messages=[])

    with pytest.raises(ChatlasQueryError, match="lowercase hexadecimal"):
        ChatlasQueryEngine(reader).run(ChatlasQuery(turn_hash_prefixes=(prefix,)))


def test_query_rejects_a_missing_turn_prefix() -> None:
    reader = Reader(turns=[_turn(TURN_ONE_HASH, address="1" * 64)], messages=[])

    with pytest.raises(ChatlasQueryError, match="does not match a Turn"):
        ChatlasQueryEngine(reader).run(
            ChatlasQuery(turn_hash_prefixes=(TURN_TWO_HASH[:8],))
        )


def test_query_rejects_an_ambiguous_turn_prefix() -> None:
    reader = Reader(
        turns=[
            _turn("a1" + "0" * 62, address="1" * 64),
            _turn("a2" + "0" * 62, address="2" * 64),
        ],
        messages=[],
    )

    with pytest.raises(ChatlasQueryError, match="matches 2 Turns"):
        ChatlasQueryEngine(reader).run(ChatlasQuery(turn_hash_prefixes=("a",)))


def test_query_discovers_turns_by_side_and_literal_message_text() -> None:
    user_ref = {
        "message_address": MESSAGE_ONE_ADDRESS,
        "message_hash": MESSAGE_ONE_HASH,
    }
    agent_ref = {
        "message_address": MESSAGE_TWO_ADDRESS,
        "message_hash": MESSAGE_TWO_HASH,
    }
    reader = Reader(
        turns=[
            _turn(TURN_ONE_HASH, address="1" * 64, message_refs=[user_ref]),
            _turn(
                TURN_TWO_HASH,
                address="2" * 64,
                side="agent",
                message_refs=[agent_ref],
            ),
        ],
        messages=[
            _message(MESSAGE_ONE_ADDRESS, MESSAGE_ONE_HASH, "Need General discovery"),
            _message(
                MESSAGE_TWO_ADDRESS,
                MESSAGE_TWO_HASH,
                "general response",
                side="agent",
            ),
        ],
    )

    result = ChatlasQueryEngine(reader).run(
        ChatlasQuery(side="user", text_contains="GENERAL")
    )

    assert [item.turn["turn_hash"] for item in result.findings] == [TURN_ONE_HASH]
    assert result.findings[0].prefix == TURN_ONE_HASH[:16]


def test_query_discovery_orders_then_limits_results() -> None:
    reader = Reader(
        turns=[
            _turn(TURN_ONE_HASH, address="1" * 64),
            _turn(TURN_TWO_HASH, address="2" * 64),
        ],
        messages=[],
    )

    result = ChatlasQueryEngine(reader).run(ChatlasQuery(order="newest", limit=1))

    assert [item.turn["turn_hash"] for item in result.findings] == [TURN_TWO_HASH]


def test_query_discovery_returns_an_empty_result_for_no_text_match() -> None:
    reader = Reader(
        turns=[_turn(TURN_ONE_HASH, address="1" * 64)],
        messages=[],
    )

    result = ChatlasQueryEngine(reader).run(ChatlasQuery(text_contains="missing"))

    assert result.findings == ()


def test_query_rejects_mixing_exact_prefixes_and_discovery_options() -> None:
    with pytest.raises(ChatlasQueryError, match="cannot be combined"):
        ChatlasQuery(turn_hash_prefixes=(TURN_ONE_HASH[:8],), side="user")
