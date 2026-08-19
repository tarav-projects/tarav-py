# $kw: ^chatlas2-message-operations --from Event.Annotation --from Event.Ref --note [IMPL] provider-neutral pure operations expose the primary transcript projection, derived time, support identity, and bounded context without decoding native records --supp ^c20260815-7u ^c20260815-40u ^c20260815-42u ^c20260815-46u
from __future__ import annotations

from copy import deepcopy
from typing import Literal

from .message_ref import chat_message_ref, resolve_chat_message_ref
from .model import JsonObject


MessageSide = Literal["user", "agent"]


def list_chat_messages(
    model: JsonObject,
    *,
    side: MessageSide | None = None,
) -> list[JsonObject]:
    if side not in {None, "user", "agent"}:
        raise ValueError("Chat.Message side must be 'user' or 'agent'")
    annotations = model.get("annotations")
    raw = annotations.get("chat_messages") if isinstance(annotations, dict) else None
    if not isinstance(raw, list):
        return []
    messages = [message for message in raw if isinstance(message, dict)]
    if side is not None:
        messages = [message for message in messages if message.get("side") == side]
    return deepcopy(messages)


def find_chat_messages(
    model: JsonObject,
    *,
    text: str,
    side: MessageSide | None = None,
    exact: bool = False,
) -> list[JsonObject]:
    if not isinstance(text, str):
        raise ValueError("Chat.Message text query must be a string")
    matches: list[JsonObject] = []
    for message in list_chat_messages(model, side=side):
        candidate = message.get("text")
        if not isinstance(candidate, str):
            continue
        if candidate == text if exact else text in candidate:
            matches.append(message)
    return matches


def chat_message_at(model: JsonObject, message: JsonObject) -> str | None:
    refs = message.get("event_refs")
    if not isinstance(refs, list) or not refs or not isinstance(refs[0], dict):
        return None
    first_address = refs[0].get("event_address")
    events = model.get("events")
    if not isinstance(first_address, str) or not isinstance(events, list):
        return None
    for event in events:
        if not isinstance(event, dict) or event.get("event_address") != first_address:
            continue
        started_at = event.get("started_at")
        return started_at if isinstance(started_at, str) and started_at else None
    return None


def chat_message_support_member(model: JsonObject, message: JsonObject) -> JsonObject:
    session = model.get("session")
    identity = session.get("identity_hash") if isinstance(session, dict) else None
    at = chat_message_at(model, message)
    if not isinstance(identity, str) or not identity:
        raise ValueError("lossless Normal Model has no session identity_hash")
    if at is None:
        raise ValueError("Chat.Message has no resolvable started_at")
    ref = chat_message_ref(message)
    return {
        "session": identity,
        "message_address": ref["message_address"],
        "message_hash": ref["message_hash"],
        "at": at,
    }


def chat_message_neighborhood(
    model: JsonObject,
    ref: JsonObject,
    *,
    radius: int = 4,
) -> JsonObject:
    if radius < 0:
        raise ValueError("Chat.Message neighborhood radius must be non-negative")
    messages = list_chat_messages(model)
    resolution = resolve_chat_message_ref(messages, ref)
    standing = resolution["standing"]
    current = resolution["message"]
    if current is None:
        return {"standing": standing, "target_index": None, "messages": []}
    target_address = current["message_address"]
    target_index = next(
        index
        for index, message in enumerate(messages)
        if message.get("message_address") == target_address
    )
    start = max(0, target_index - radius)
    end = min(len(messages), target_index + radius + 1)
    return {
        "standing": standing,
        "target_index": target_index,
        "messages": messages[start:end],
    }


__all__ = [
    "MessageSide",
    "chat_message_at",
    "chat_message_neighborhood",
    "chat_message_support_member",
    "find_chat_messages",
    "list_chat_messages",
]
