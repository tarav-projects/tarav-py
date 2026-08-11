# $kw: --from Normal.Turn
from __future__ import annotations

from typing import Any

from agentos._core.errors import CliError

from ._payload_helpers import dict_list, string_or_none
from .normalization.session_model.events import (
    compute_event_group_hash,
    events_for_normal_turn,
    normal_turn_id,
)


TURN_REF_FIELDS = frozenset({"session", "turn_id", "turn_hash", "at"})


def session_events(session_model: dict[str, Any]) -> list[dict[str, Any]]:
    chat = session_model.get("chat")
    return dict_list(chat.get("events")) if isinstance(chat, dict) else []


def normal_turn_events(
    session_model: dict[str, Any], turn_id: str
) -> list[dict[str, Any]]:
    return events_for_normal_turn(session_events(session_model), turn_id)


def normal_turn_ref(
    session: str,
    events: list[dict[str, Any]],
) -> dict[str, str]:
    if not events:
        raise CliError("cannot reference an empty Normal.Turn")
    turn_ids = {normal_turn_id(event) for event in events}
    if len(turn_ids) != 1 or None in turn_ids:
        raise CliError("Normal.Turn.Ref events do not share one turn identity")
    at = string_or_none(events[0].get("timestamp"))
    if at is None:
        raise CliError("Normal.Turn.Ref landing event has no timestamp")
    return {
        "session": session,
        "turn_id": next(iter(turn_ids)),
        "turn_hash": compute_event_group_hash(events),
        "at": at,
    }


def parse_normal_turn_ref(value: object, *, field: str = "turn ref") -> dict[str, str]:
    if not isinstance(value, dict):
        raise CliError(f"{field} must be an object")
    unknown = set(value) - TURN_REF_FIELDS
    if unknown:
        raise CliError(f"{field} has unknown fields: {', '.join(sorted(unknown))}")
    parsed: dict[str, str] = {}
    for key in ("session", "turn_id", "turn_hash", "at"):
        item = string_or_none(value.get(key))
        if item is None:
            raise CliError(f"{field} requires non-empty {key!r}")
        parsed[key] = item
    if len(parsed["turn_hash"]) != 64:
        raise CliError(f"{field} turn_hash must be a full SHA-256 digest")
    return parsed


def resolve_normal_turn_ref(
    value: object,
    session_model: dict[str, Any],
    *,
    field: str = "turn ref",
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    ref = parse_normal_turn_ref(value, field=field)
    events = normal_turn_events(session_model, ref["turn_id"])
    if not events:
        raise CliError(f"{field} turn is unavailable: {ref['session']}:{ref['turn_id']}")
    actual = normal_turn_ref(ref["session"], events)
    if actual["turn_hash"] != ref["turn_hash"]:
        raise CliError(
            f"{field} turn_hash mismatch for {ref['session']}:{ref['turn_id']}: "
            f"record={ref['turn_hash']!r}, actual={actual['turn_hash']!r}"
        )
    if actual["at"] != ref["at"]:
        raise CliError(
            f"{field} timestamp mismatch for {ref['session']}:{ref['turn_id']}: "
            f"record={ref['at']!r}, actual={actual['at']!r}"
        )
    return ref, events


__all__ = [
    "TURN_REF_FIELDS",
    "normal_turn_events",
    "normal_turn_ref",
    "parse_normal_turn_ref",
    "resolve_normal_turn_ref",
    "session_events",
]
