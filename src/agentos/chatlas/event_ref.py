# $kw: ^event-ref --from Chatlas.Session.Model --from Session.Event.Tape --note [DC] Event.Ref binds a stable event_address to an event_hash assertion; sequence is only presentation metadata ^c20260807-16u
"""`Event.Ref` — a self-verifying reference to one stable event place.

``event_address`` locates the place and ``event_hash`` asserts its current
content. A content amendment therefore preserves resolution while making the
assertion visibly stale. Tape sequence is positional metadata, never identity.

The reference is an **object**; the model never stores it packed into a string.
`format_event_ref` / `parse_event_ref` exist as sugar for CLI arguments, log
lines, and anything a human pastes — presentation over the model, never the
model itself.

`event_hash` is stored as a **prefix** of the event's digest, so verification
strength is the storer's choice: 8 bytes is the floor, the full digest the
maximum, and a resolver compares only as many characters as were stored. The
index does the addressing; the hash only decides how confidently a stale
reference announces itself.

A resolver reports the semantic established by those fields. Consumers decide
what policy to apply to matched, amended, or missing references.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from agentos.chatlas._payload_helpers import string_or_none
from agentos.chatlas.normalization.session_model.events import compute_event_hash

EVENT_REF_SCHEMA = "chatlas.event-ref.v2"

# Floor for the stored digest prefix. Below this the check still looks like
# verification while providing almost none, which is worse than no check.
EVENT_HASH_MIN_CHARS = 16  # 8 bytes


class EventRefOutcome(Enum):
    """What resolving a reference established about its assertion."""

    MATCHED = "matched"
    AMENDED = "amended"
    MISSING = "missing"


@dataclass(frozen=True)
class EventRefResolution:
    outcome: EventRefOutcome
    event: dict[str, Any] | None
    finding: str | None = None


def event_ref(
    event: dict[str, Any],
    *,
    hash_chars: int = EVENT_HASH_MIN_CHARS,
    session: str | None = None,
    with_timestamp: bool = False,
    with_schema: bool = False,
) -> dict[str, Any]:
    """Build a reference to `event`.

    `session`, the timestamp, and the schema marker are optional: include them
    when the reference escapes a context that already supplies them.
    """
    if hash_chars < EVENT_HASH_MIN_CHARS:
        raise ValueError(
            f"event_hash prefix must be at least {EVENT_HASH_MIN_CHARS} chars: {hash_chars}"
        )
    digest = event.get("event_hash") or compute_event_hash(event)
    address = event.get("event_address")
    if not isinstance(address, str) or not address:
        raise ValueError("event has no event_address; cannot build an Event.Ref")
    ref: dict[str, Any] = {}
    if with_schema:
        ref["schema"] = EVENT_REF_SCHEMA
    if session is not None:
        ref["session"] = session
    ref["event_address"] = address
    ref["event_hash"] = str(digest)[:hash_chars]
    if with_timestamp and event.get("timestamp") is not None:
        ref["at"] = event["timestamp"]
    return ref


def _ref_parts(ref: dict[str, Any]) -> tuple[str, str]:
    address = ref.get("event_address")
    digest = ref.get("event_hash")
    if not isinstance(address, str) or not address:
        raise ValueError("Event.Ref requires a non-empty event_address")
    if not isinstance(digest, str) or not digest:
        raise ValueError("Event.Ref requires a non-empty event_hash")
    if len(digest) < EVENT_HASH_MIN_CHARS:
        raise ValueError(
            f"Event.Ref event_hash is shorter than the {EVENT_HASH_MIN_CHARS}-char floor"
        )
    return address, digest


def format_event_ref(ref: dict[str, Any]) -> str:
    """CLI/display sugar — never the stored form."""
    address, digest = _ref_parts(ref)
    return f"{address}:{digest}"


def parse_event_ref(text: str) -> dict[str, Any]:
    """Read the sugar back into a reference object."""
    address, separator, digest = text.partition(":")
    if not separator or not address or not digest:
        raise ValueError(
            f"Event.Ref text must have the form <event-address>:<event-hash>: {text!r}"
        )
    ref = {"event_address": address, "event_hash": digest}
    _ref_parts(ref)
    return ref


def _matches(event: dict[str, Any], digest: str) -> bool:
    stored = event.get("event_hash")
    if not isinstance(stored, str):
        stored = compute_event_hash(event)
    return stored[: len(digest)] == digest


def resolve_event_ref(
    events: list[dict[str, Any]],
    ref: dict[str, Any],
) -> EventRefResolution:
    """Check a reference's assertion against a tape and report what holds."""
    address, digest = _ref_parts(ref)
    addressed = next(
        (event for event in events if event.get("event_address") == address), None
    )
    if addressed is None:
        return EventRefResolution(
            EventRefOutcome.MISSING,
            None,
            finding=f"event place {address} is not present in this tape scope",
        )
    if _matches(addressed, digest):
        return EventRefResolution(EventRefOutcome.MATCHED, addressed)
    return EventRefResolution(
        EventRefOutcome.AMENDED,
        addressed,
        finding=f"event place {address} exists but its current event_hash differs",
    )


def event_ref_list(value: object) -> list[dict[str, Any]]:
    """The `Event.Ref` objects in a stored `event_refs` field, ignoring junk."""
    if not isinstance(value, list):
        return []
    return [
        ref
        for ref in value
        if isinstance(ref, dict)
        and "event_address" in ref
        and "event_hash" in ref
    ]


def event_ref_addresses(value: object) -> list[str]:
    """The stable places a stored ``event_refs`` field addresses."""
    return [
        address
        for ref in event_ref_list(value)
        if (address := string_or_none(ref.get("event_address"))) is not None
    ]


def attach_event_refs_to_tool_invocations(
    tool_invocations: list[dict[str, Any]],
    *,
    events: list[dict[str, Any]],
) -> None:
    refs_by_tool_invocation: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        tool_invocation_ref = string_or_none(event.get("tool_invocation_ref"))
        if tool_invocation_ref is None or string_or_none(event.get("event_address")) is None:
            continue
        refs_by_tool_invocation.setdefault(tool_invocation_ref, []).append(
            event_ref(event),
        )

    for invocation in tool_invocations:
        invocation_id = string_or_none(invocation.get("tool_invocation_id"))
        if invocation_id is None:
            continue
        refs = refs_by_tool_invocation.get(invocation_id)
        if refs:
            invocation["event_refs"] = refs


def attach_model_run_refs_to_events(
    model_runs: list[dict[str, Any]],
    *,
    events: list[dict[str, Any]],
) -> None:
    """Back-fill the neutral run correlation: every event a model run's
    `event_refs` address carries that run's id as `model_run_ref`.

    The join is intra-document, so it reads the reference address directly.
    """
    model_run_ref_by_address: dict[str, str] = {}
    for model_run in model_runs:
        model_run_id = string_or_none(model_run.get("model_run_id"))
        if model_run_id is None:
            continue
        for address in event_ref_addresses(model_run.get("event_refs")):
            model_run_ref_by_address[address] = model_run_id

    for event in events:
        address = string_or_none(event.get("event_address"))
        if address is None:
            continue
        model_run_ref = model_run_ref_by_address.get(address)
        if model_run_ref is not None:
            event["model_run_ref"] = model_run_ref


__all__ = [
    "EVENT_HASH_MIN_CHARS",
    "EVENT_REF_SCHEMA",
    "EventRefOutcome",
    "EventRefResolution",
    "attach_event_refs_to_tool_invocations",
    "attach_model_run_refs_to_events",
    "event_ref",
    "event_ref_list",
    "event_ref_addresses",
    "format_event_ref",
    "parse_event_ref",
    "resolve_event_ref",
]
