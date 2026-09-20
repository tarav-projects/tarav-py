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
EVENT_ONE_ADDRESS = "1" * 64
EVENT_TWO_ADDRESS = "2" * 64
EVENT_ONE_HASH = "3" * 64
EVENT_TWO_HASH = "4" * 64


def _turn(
    turn_hash: str,
    *,
    address: str,
    side: str = "user",
    event_refs: list[dict[str, str]] | None = None,
    message_refs: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "type": "Chat.Turn",
        "turn_address": address,
        "turn_hash": turn_hash,
        "side": side,
        "event_refs": event_refs
        or [{"event_address": EVENT_ONE_ADDRESS, "event_hash": EVENT_ONE_HASH}],
        "message_refs": message_refs or [],
    }


def _message(
    address: str, digest: str, text: str, *, side: str = "user"
) -> dict[str, object]:
    return {
        "type": "Chat.Message",
        "message_address": address,
        "message_hash": digest,
        "side": side,
        "event_refs": [
            {"event_address": EVENT_ONE_ADDRESS, "event_hash": EVENT_ONE_HASH}
        ],
        "text": text,
    }


def _event(address: str, digest: str, *, started_at: str) -> dict[str, object]:
    return {
        "type": "User.Event",
        "event_address": address,
        "event_hash": digest,
        "started_at": started_at,
        "origin": "user",
        "observations": [
            {
                "observed_at": started_at,
                "source_ref": {
                    "source_id": "source-one",
                    "record_index": 1,
                    "line": 1,
                },
            }
        ],
        "opaque_payload_hash": "5" * 64,
    }


class Reader:
    def __init__(
        self,
        *,
        turns: list[dict[str, object]],
        messages: list[dict[str, object]],
        events: list[dict[str, object]] | None = None,
    ) -> None:
        self._turns = turns
        self._messages = messages
        self._events = (
            events
            if events is not None
            else [
                _event(
                    EVENT_ONE_ADDRESS,
                    EVENT_ONE_HASH,
                    started_at="2026-09-05T13:00:00Z",
                )
            ]
        )

    def model_header(self) -> dict[str, object]:
        return {
            "schema": "tarav.chatlas.normal-model",
            "schema_version": 2,
            "session": {
                "provider": "codex",
                "session_id": "session-one",
                "identity_hash": "0" * 64,
            },
        }

    def iter_turns(self):
        yield from deepcopy(self._turns)

    def iter_events(self):
        yield from deepcopy(self._events)

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


def test_query_resolves_the_earliest_valid_event_started_at() -> None:
    event_refs = [
        {"event_address": EVENT_ONE_ADDRESS, "event_hash": EVENT_ONE_HASH},
        {"event_address": EVENT_TWO_ADDRESS, "event_hash": EVENT_TWO_HASH},
    ]
    reader = Reader(
        turns=[
            _turn(
                TURN_ONE_HASH,
                address="5" * 64,
                event_refs=event_refs,
            )
        ],
        messages=[],
        events=[
            _event(
                EVENT_ONE_ADDRESS,
                EVENT_ONE_HASH,
                started_at="2026-09-05T10:00:00-04:00",
            ),
            _event(
                EVENT_TWO_ADDRESS,
                EVENT_TWO_HASH,
                started_at="2026-09-05T13:00:00Z",
            ),
        ],
    )

    result = ChatlasQueryEngine(reader).run(
        ChatlasQuery(turn_hash_prefixes=(TURN_ONE_HASH[:8],))
    )

    assert result.findings[0].started_at == "2026-09-05T13:00:00Z"
    assert result.findings[0].to_dict()["started_at"] == "2026-09-05T13:00:00Z"


def test_query_leaves_started_at_absent_when_events_have_no_valid_time() -> None:
    reader = Reader(
        turns=[
            _turn(
                TURN_ONE_HASH,
                address="5" * 64,
                event_refs=[
                    {"event_address": EVENT_ONE_ADDRESS, "event_hash": EVENT_ONE_HASH}
                ],
            )
        ],
        messages=[],
        events=[_event(EVENT_ONE_ADDRESS, EVENT_ONE_HASH, started_at="not-a-time")],
    )

    result = ChatlasQueryEngine(reader).run(
        ChatlasQuery(turn_hash_prefixes=(TURN_ONE_HASH[:8],))
    )

    assert result.findings[0].started_at is None


def test_query_rejects_an_amended_turn_event() -> None:
    reader = Reader(
        turns=[
            _turn(
                TURN_ONE_HASH,
                address="5" * 64,
                event_refs=[
                    {"event_address": EVENT_ONE_ADDRESS, "event_hash": EVENT_ONE_HASH}
                ],
            )
        ],
        messages=[],
        events=[
            _event(
                EVENT_ONE_ADDRESS,
                EVENT_TWO_HASH,
                started_at="2026-09-05T13:00:00Z",
            )
        ],
    )

    with pytest.raises(ChatlasQueryError, match="Chat.Event was amended"):
        ChatlasQueryEngine(reader).run(
            ChatlasQuery(turn_hash_prefixes=(TURN_ONE_HASH[:8],))
        )


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
