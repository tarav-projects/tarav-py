from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Iterable

from .model import JsonObject


_FULL_SHA256 = re.compile(r"[0-9a-f]{64}")


def compute_chat_turn_address(
    *,
    provider: str,
    scope: str,
    place: object,
) -> str:
    return _digest(
        {
            "schema": "tarav.chatlas.chat-turn-address.v1",
            "provider": provider,
            "scope": scope,
            "place": place,
        }
    )


def compute_opaque_payload_hash(value: object) -> str:
    return _digest(
        {
            "schema": "tarav.chatlas.opaque-payload.v1",
            "value": value,
        }
    )


def compute_chat_turn_hash(
    turn: JsonObject,
    *,
    opaque_payload_hashes: Iterable[str],
) -> str:
    side = turn.get("side")
    if side not in {"user", "agent"}:
        raise ValueError("Chat.Turn side must be 'user' or 'agent'")
    event_hashes = _member_hashes(
        turn.get("event_refs"),
        field="event_hash",
        allow_empty=False,
    )
    message_hashes = _member_hashes(
        turn.get("message_refs"),
        field="message_hash",
        allow_empty=True,
    )
    payload_hashes = [
        _full_digest(value, field="opaque_payload_hash")
        for value in opaque_payload_hashes
    ]
    if len(payload_hashes) != len(event_hashes):
        raise ValueError("Chat.Turn requires one opaque payload hash per event")
    return _digest(
        {
            "side": side,
            "event_hashes": event_hashes,
            "message_hashes": message_hashes,
            "opaque_payload_hashes": payload_hashes,
        }
    )


def chat_turn_ref(turn: JsonObject) -> JsonObject:
    return {
        "turn_address": _full_digest(turn.get("turn_address"), field="turn_address"),
        "turn_hash": _full_digest(turn.get("turn_hash"), field="turn_hash"),
    }


def resolve_chat_turn_ref(
    turns: Iterable[JsonObject],
    ref: JsonObject,
) -> JsonObject:
    address = _full_digest(ref.get("turn_address"), field="turn_address")
    expected_hash = _full_digest(ref.get("turn_hash"), field="turn_hash")
    addressed = [turn for turn in turns if turn.get("turn_address") == address]
    if len(addressed) > 1:
        raise ValueError(
            f"current Chat.Turn projection contains duplicate address {address}"
        )
    if not addressed:
        return {
            "class": "Chat.Turn.Ref.Resolution",
            "standing": "MISSING",
            "turn": None,
        }
    current = addressed[0]
    current_hash = _full_digest(current.get("turn_hash"), field="turn_hash")
    return {
        "class": "Chat.Turn.Ref.Resolution",
        "standing": "MATCHED" if current_hash == expected_hash else "AMENDED",
        "turn": current,
    }


def _member_hashes(value: object, *, field: str, allow_empty: bool) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValueError(f"Chat.Turn must contain {field} members")
    hashes: list[str] = []
    for ref in value:
        if not isinstance(ref, dict):
            raise ValueError("Chat.Turn ref member must be an object")
        hashes.append(_full_digest(ref.get(field), field=field))
    return hashes


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
            f"Chat.Turn.Ref {field} must be a full lowercase SHA-256 digest"
        )
    return value


__all__ = [
    "chat_turn_ref",
    "compute_chat_turn_address",
    "compute_chat_turn_hash",
    "compute_opaque_payload_hash",
    "resolve_chat_turn_ref",
]
