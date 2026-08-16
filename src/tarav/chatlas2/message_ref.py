# $kw: ^chatlas2-message-ref --from Event.Ref --note [DC] Chatlas2 separates provider-derived message place from the current ordered Event.Hash assertion and resolves stored message refs only against the supplied current model --supp ^c20260815-4u ^c20260815-5u ^c20260815-6u ^c20260815-7u ^c20260815-8u ^c20260815-37u ^c20260815-38u ^c20260815-39u ^c20260815-46u ^c20260815-64u
from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Iterable

from .model import JsonObject


_FULL_SHA256 = re.compile(r"[0-9a-f]{64}")


def compute_chat_message_address(
    *,
    provider: str,
    scope: str,
    place: object,
) -> str:
    body = {
        "schema": "tarav.chatlas2.chat-message-address.v1",
        "provider": provider,
        "scope": scope,
        "place": place,
    }
    return _digest(body)


def compute_chat_message_hash(message: JsonObject) -> str:
    side = message.get("side")
    if side not in {"user", "agent"}:
        raise ValueError("Chat.Message side must be 'user' or 'agent'")
    refs = message.get("event_refs")
    if not isinstance(refs, list) or not refs:
        raise ValueError("Chat.Message must contain Event.Ref members")
    event_hashes: list[str] = []
    for ref in refs:
        if not isinstance(ref, dict):
            raise ValueError("Chat.Message Event.Ref member must be an object")
        event_hashes.append(_full_digest(ref.get("event_hash"), field="event_hash"))
    return _digest({"side": side, "event_hashes": event_hashes})


def chat_message_ref(message: JsonObject) -> JsonObject:
    address = _full_digest(
        message.get("message_address"), field="message_address"
    )
    digest = _full_digest(message.get("message_hash"), field="message_hash")
    return {"message_address": address, "message_hash": digest}


def resolve_chat_message_ref(
    messages: Iterable[JsonObject],
    ref: JsonObject,
) -> JsonObject:
    address = _full_digest(ref.get("message_address"), field="message_address")
    expected_hash = _full_digest(ref.get("message_hash"), field="message_hash")
    addressed = [
        message for message in messages if message.get("message_address") == address
    ]
    if len(addressed) > 1:
        raise ValueError(f"current Chat.Message projection contains duplicate address {address}")
    if not addressed:
        return {
            "class": "Chat.Message.Ref.Resolution",
            "standing": "MISSING",
            "message": None,
        }
    current = addressed[0]
    current_hash = _full_digest(current.get("message_hash"), field="message_hash")
    return {
        "class": "Chat.Message.Ref.Resolution",
        "standing": "MATCHED" if current_hash == expected_hash else "AMENDED",
        "message": current,
    }


def _digest(value: object) -> str:
    body = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(body.encode("utf-8")).hexdigest()


def _full_digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _FULL_SHA256.fullmatch(value) is None:
        raise ValueError(
            f"Chat.Message.Ref {field} must be a full lowercase SHA-256 digest"
        )
    return value


__all__ = [
    "chat_message_ref",
    "compute_chat_message_address",
    "compute_chat_message_hash",
    "resolve_chat_message_ref",
]
