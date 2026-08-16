# $kw: ^chatlas2-event-ref --from Event.Ref --note [DC] Chatlas2 separates provider-derived event place from current normalized state and resolves stored assertions only against the supplied current tape --supp ^c20260815-37u ^c20260815-38u ^c20260815-39u ^c20260815-40u ^c20260815-41u ^c20260815-42u ^c20260815-43u ^c20260815-44u ^c20260815-64u
from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Iterable

from .model import JsonObject


_FULL_SHA256 = re.compile(r"[0-9a-f]{64}")


def compute_event_address(
    *,
    provider: str,
    scope: str,
    place: object,
) -> str:
    body = {
        "schema": "tarav.chatlas2.event-address.v1",
        "provider": provider,
        "scope": scope,
        "place": place,
    }
    return _digest(body)


def compute_event_hash(event: JsonObject) -> str:
    body = {
        "class": event.get("class"),
        "origin": event.get("origin"),
        "started_at": event.get("started_at"),
        "record": _without_native_identifiers(event.get("record")),
    }
    return _digest(body)


def event_ref(event: JsonObject) -> JsonObject:
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
            "class": "Event.Ref.Resolution",
            "standing": "MISSING",
            "event": None,
        }
    current = addressed[0]
    current_hash = _full_digest(current.get("event_hash"), field="event_hash")
    return {
        "class": "Event.Ref.Resolution",
        "standing": "MATCHED" if current_hash == expected_hash else "AMENDED",
        "event": current,
    }


def _without_native_identifiers(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_native_identifiers(item)
            for key, item in value.items()
            if not _native_identifier_key(key)
        }
    if isinstance(value, list):
        return [_without_native_identifiers(item) for item in value]
    return value


def _native_identifier_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    return (
        key == "id"
        or key.endswith("_id")
        or key.endswith("_ids")
        or key == "uuid"
        or key.endswith(("Uuid", "Uuids", "UUID", "UUIDs"))
        or key.endswith(("Id", "Ids", "ID", "IDs"))
    )


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
