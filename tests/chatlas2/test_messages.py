from __future__ import annotations

from copy import deepcopy

import pytest

from tarav.chatlas2.message_ref import compute_chat_message_hash
from tarav.chatlas2.messages import (
    chat_message_at,
    chat_message_neighborhood,
    chat_message_support_member,
    find_chat_messages,
    list_chat_messages,
)


def _model() -> dict[str, object]:
    events = []
    messages = []
    for index, (side, text) in enumerate(
        (("user", "first question"), ("agent", "first answer"), ("user", "second question")),
        start=1,
    ):
        address = str(index) * 64
        event_hash = chr(96 + index) * 64
        events.append(
            {
                "class": "User.Event" if side == "user" else "Agent.Event",
                "event_address": address,
                "event_hash": event_hash,
                "started_at": f"2026-08-16T00:00:0{index}Z",
            }
        )
        message = {
            "class": "Chat.Message",
            "message_address": chr(100 + index) * 64,
            "side": side,
            "text": text,
            "event_refs": [{"event_address": address, "event_hash": event_hash}],
        }
        message["message_hash"] = compute_chat_message_hash(message)
        messages.append(message)
    return {
        "session": {"identity_hash": "f" * 64},
        "events": events,
        "annotations": {"chat_messages": messages},
    }


def test_message_operations_are_provider_neutral_and_pure() -> None:
    model = _model()
    original = deepcopy(model)

    assert [message["text"] for message in list_chat_messages(model)] == [
        "first question",
        "first answer",
        "second question",
    ]
    assert [message["text"] for message in list_chat_messages(model, side="user")] == [
        "first question",
        "second question",
    ]
    assert [message["text"] for message in find_chat_messages(model, text="question")] == [
        "first question",
        "second question",
    ]
    assert [
        message["text"]
        for message in find_chat_messages(
            model, side="agent", text="first answer", exact=True
        )
    ] == ["first answer"]
    assert model == original


def test_message_time_support_member_and_bounded_neighborhood() -> None:
    model = _model()
    target = list_chat_messages(model)[1]
    ref = {
        "message_address": target["message_address"],
        "message_hash": target["message_hash"],
    }

    assert chat_message_at(model, target) == "2026-08-16T00:00:02Z"
    assert chat_message_support_member(model, target) == {
        "session": "f" * 64,
        "message_address": target["message_address"],
        "message_hash": target["message_hash"],
        "at": "2026-08-16T00:00:02Z",
    }
    neighborhood = chat_message_neighborhood(model, ref, radius=1)
    assert neighborhood["standing"] == "MATCHED"
    assert neighborhood["target_index"] == 1
    assert [message["text"] for message in neighborhood["messages"]] == [
        "first question",
        "first answer",
        "second question",
    ]


def test_message_neighborhood_preserves_amended_and_missing_standing() -> None:
    model = _model()
    target = list_chat_messages(model)[1]
    amended_ref = {
        "message_address": target["message_address"],
        "message_hash": "0" * 64,
    }
    missing_ref = {
        "message_address": "9" * 64,
        "message_hash": "0" * 64,
    }

    assert chat_message_neighborhood(model, amended_ref, radius=0)["standing"] == "AMENDED"
    assert chat_message_neighborhood(model, missing_ref, radius=0) == {
        "standing": "MISSING",
        "target_index": None,
        "messages": [],
    }
    with pytest.raises(ValueError, match="non-negative"):
        chat_message_neighborhood(model, amended_ref, radius=-1)
