from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Iterable

from .model import JsonObject
from .records import event_record


_FULL_SHA256 = re.compile(r"[0-9a-f]{64}")
_LEGACY_EVENT_HASH_KEY = "class"


def compute_event_address(
    *,
    provider: str,
    scope: str,
    place: object,
) -> str:
    body = {
        "schema": "tarav.chatlas.event-address.v1",
        "provider": provider,
        "scope": scope,
        "place": place,
    }
    return _digest(body)


def compute_event_hash(event: JsonObject) -> str:
    event_type = event.get("type")
    body = {
        # Event identity predates registered Record Types. Keep its original
        # hash preimage while the retained representation moves to ``type``.
        _LEGACY_EVENT_HASH_KEY: event_type,
        "origin": event.get("origin"),
        "started_at": event.get("started_at"),
        "content": event.get("content"),
    }
    return _digest(body)


def event_ref(event: JsonObject) -> JsonObject:
    event = event_record(event).to_record()
    address = _full_digest(event.get("event_address"), field="event_address")
    digest = _full_digest(event.get("event_hash"), field="event_hash")
    return {"event_address": address, "event_hash": digest}


def resolve_event_ref(
    events: Iterable[JsonObject],
    ref: JsonObject,
) -> JsonObject:
    address = _full_digest(ref.get("event_address"), field="event_address")
    expected_hash = _full_digest(ref.get("event_hash"), field="event_hash")
    addressed = [event for event in events if event.get("event_address") == address]
    if len(addressed) > 1:
        raise ValueError(f"current event tape contains duplicate address {address}")
    if not addressed:
        return {
            "standing": "MISSING",
            "event": None,
        }
    current = event_record(addressed[0]).to_record()
    current_hash = _full_digest(current.get("event_hash"), field="event_hash")
    return {
        "standing": "MATCHED" if current_hash == expected_hash else "AMENDED",
        "event": current,
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
        raise ValueError(f"Event.Ref {field} must be a full lowercase SHA-256 digest")
    return value


__all__ = [
    "compute_event_address",
    "compute_event_hash",
    "event_ref",
    "resolve_event_ref",
]
