# $kw: ^stable-event-address --from Chatlas.Session.Model.Contract --from Session.Event.Tape --note [DC] event_address names a provider-derived event place while event_hash asserts its current content ^c20260807-9u
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Callable, Hashable

from tarav.chatlas._payload_helpers import (
    dict_list,
    string_or_none,
)


def first_event_for_turn(
    events: list[dict[str, object]],
    *,
    native_turn_id: str | None,
    event_type: str,
) -> dict[str, object] | None:
    expected_kind = event_type_kind(event_type)
    for event in events:
        if event.get("type") != event_type and event.get("kind") != expected_kind:
            continue
        if native_turn_id is not None and event_native_turn_id(event) != native_turn_id:
            continue
        if native_turn_id is None and event_native_turn_id(event) is not None:
            continue
        return event
    return None


def event_type_kind(event_type: str) -> str:
    if event_type.endswith(".task_started"):
        return "run.start"
    if event_type.endswith(".task_complete"):
        return "run.end"
    return event_type


def event_native(event: dict[str, object]) -> dict[str, object]:
    """The event's provider-anchor area — native identifiers live here, not on the
    neutral envelope."""
    native = event.get("native")
    if isinstance(native, dict):
        return native
    return {}


def set_event_native(event: dict[str, object], key: str, value: object) -> None:
    if value is None:
        return
    native = event.get("native")
    if not isinstance(native, dict):
        native = {}
        event["native"] = native
    native[key] = value







EVENT_HASH_FIELDS = ("kind", "producer", "payload", "timestamp")


def compute_event_hash(event: dict[str, object]) -> str:
    """The event's content digest — reproducible from the event alone.

    An `Event.Ref` asserts this value at a stable event address, so a
    consumer never recomputes semantics: chatlas owns the derivation and the
    covered field set is contract, not convention.
    """
    body = json.dumps(
        {field: event.get(field) for field in EVENT_HASH_FIELDS},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def compute_event_address(
    *,
    provider: str,
    scope: str,
    place: object,
    occurrence: int = 1,
) -> str:
    """Hash one provider-owned raw place into the normal model's opaque address.

    The normal model deliberately does not prescribe a universal raw coordinate.
    Each normalizer chooses ``place``; this function only supplies the common opaque
    representation and domain separation. Normalized content and tape sequence must
    never be included in ``place``.
    """
    body = json.dumps(
        {
            "schema": "chatlas.event-address.v1",
            "provider": provider,
            "scope": scope,
            "place": place,
            "occurrence": occurrence,
        },
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def assign_event_addresses(
    events: list[dict[str, object]],
    *,
    provider: str,
    scope: str,
    place_key: Callable[[dict[str, object]], Hashable],
) -> None:
    """Assign stable addresses from a provider normalizer's raw-place recipe.

    ``occurrence`` only disambiguates multiple normal events intentionally emitted
    at the same provider place. It is local to an identical place key, never a tape
    ordinal, so unrelated insertion or amendment cannot move other addresses.
    """
    occurrences: dict[Hashable, int] = {}
    addresses: set[str] = set()
    for event in events:
        key = place_key(event)
        occurrence = occurrences.get(key, 0) + 1
        occurrences[key] = occurrence
        address = compute_event_address(
            provider=provider,
            scope=scope,
            place=key,
            occurrence=occurrence,
        )
        if address in addresses:
            raise ValueError(f"{provider} derived duplicate event_address {address}")
        addresses.add(address)
        event["event_address"] = address


def event_annotations(event: dict[str, object]) -> dict[str, object]:
    annotations = event.get("annotations")
    return annotations if isinstance(annotations, dict) else {}


def normal_turn_id(event: dict[str, object]) -> str | None:
    annotation = event_annotations(event).get("normal_turn")
    if not isinstance(annotation, dict):
        return None
    return string_or_none(annotation.get("id"))


def normal_turn_kind(event: dict[str, object]) -> str | None:
    annotation = event_annotations(event).get("normal_turn")
    if not isinstance(annotation, dict):
        return None
    kind = string_or_none(annotation.get("kind"))
    return kind if kind in {"user", "assistant"} else None


def set_normal_turn_id(event: dict[str, object], turn_id: str | None) -> None:
    annotations = event.get("annotations")
    if not isinstance(annotations, dict):
        annotations = {}
    else:
        annotations = dict(annotations)
    if turn_id is None:
        annotations.pop("normal_turn", None)
    else:
        current = annotations.get("normal_turn")
        normal_turn = dict(current) if isinstance(current, dict) else {}
        normal_turn["id"] = turn_id
        annotations["normal_turn"] = normal_turn
    if annotations:
        event["annotations"] = annotations
    else:
        event.pop("annotations", None)


def set_normal_turn(
    event: dict[str, object],
    *,
    turn_id: str | None,
    kind: str | None,
) -> None:
    if kind not in {None, "user", "assistant"}:
        raise ValueError(f"unsupported Normal.Turn kind: {kind!r}")
    set_normal_turn_id(event, turn_id)
    if turn_id is None:
        return
    annotations = event["annotations"]
    assert isinstance(annotations, dict)
    normal_turn = annotations["normal_turn"]
    assert isinstance(normal_turn, dict)
    if kind is None:
        normal_turn.pop("kind", None)
    else:
        normal_turn["kind"] = kind


def events_for_normal_turn(
    events: list[dict[str, object]], turn_id: str
) -> list[dict[str, object]]:
    return [event for event in events if normal_turn_id(event) == turn_id]


def compute_event_group_hash(events: list[dict[str, object]]) -> str:
    """Hash one ordered grouping by the full Event.Hash of each member."""
    hashes: list[str] = []
    for event in events:
        digest = string_or_none(event.get("event_hash"))
        if digest is None:
            raise ValueError("event group member has no event_hash")
        hashes.append(digest)
    if not hashes:
        raise ValueError("event group must contain at least one event")
    body = json.dumps(hashes, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _is_user_input_event(event: dict[str, object]) -> bool:
    """Provider-normalized input admitted to the semantic User.Turn boundary."""
    payload = event.get("payload")
    producer = event.get("producer")
    return (
        event.get("kind") == "message"
        and isinstance(payload, dict)
        and payload.get("role") == "user"
        and isinstance(producer, dict)
        and producer.get("type") == "human"
    )


def _is_assistant_turn_event(event: dict[str, object]) -> bool:
    producer = event.get("producer")
    producer_type = producer.get("type") if isinstance(producer, dict) else None
    kind = string_or_none(event.get("kind")) or ""
    payload = event.get("payload")
    role = payload.get("role") if isinstance(payload, dict) else None
    return (
        producer_type in {"assistant", "tool"}
        or role == "assistant"
        or kind == "reasoning"
        or kind.startswith("tool.")
        or kind in {"run.start", "run.end", "usage", "metric"}
    )


def finalize_normal_turn_annotations(events: list[dict[str, object]]) -> None:
    """Split provider interaction hints into independent semantic turns.

    Emitters initially use their provider-stable interaction identity as a
    grouping hint. This final pass is the purity boundary: only normalized user input
    joins a user turn; assistant response activity receives a distinct id; all
    other events remain outside Normal.Turn.
    """
    orphan_assistant_id: str | None = None
    for event in events:
        interaction_id = normal_turn_id(event)
        if _is_user_input_event(event):
            if interaction_id is None:
                digest = string_or_none(event.get("event_hash")) or compute_event_hash(event)
                interaction_id = f"user-{digest[:16]}"
            set_normal_turn(event, turn_id=interaction_id, kind="user")
            orphan_assistant_id = None
            continue
        if _is_assistant_turn_event(event):
            if interaction_id is not None:
                assistant_id = f"{interaction_id}:assistant"
            else:
                if orphan_assistant_id is None:
                    digest = string_or_none(event.get("event_hash")) or compute_event_hash(event)
                    orphan_assistant_id = f"assistant-{digest[:16]}"
                assistant_id = orphan_assistant_id
            set_normal_turn(event, turn_id=assistant_id, kind="assistant")
            continue
        set_normal_turn_id(event, None)


def event_extras(event: dict[str, object]) -> dict[str, object]:
    """The event's non-chat area — content about how the model was computed
    rather than about the conversation; absent when the event carries none."""
    extras = event.get("extras")
    if isinstance(extras, dict):
        return extras
    return {}


def set_event_extra(event: dict[str, object], key: str, value: object) -> None:
    extras = event.get("extras")
    if not isinstance(extras, dict):
        extras = {}
        event["extras"] = extras
    extras[key] = value


def event_native_turn_id(event: dict[str, object]) -> str | None:
    """The provider's own turn handle, never the model's Normal.Turn annotation.

    This accessor deliberately ignores `annotations.normal_turn`, so provider
    identity and semantic grouping stay distinct even where their values match.
    """
    turn_id = string_or_none(event_native(event).get("turn_id"))
    if turn_id is not None:
        return turn_id
    if "kind" not in event and "sequence" not in event:
        turn_id = string_or_none(event.get("turn_id"))
        if turn_id is not None:
            return turn_id
    data = event.get("data")
    if isinstance(data, dict):
        turn_id = string_or_none(data.get("turn_id"))
        if turn_id is not None:
            return turn_id
    payload = event.get("payload")
    if isinstance(payload, dict):
        return string_or_none(payload.get("turn_id"))
    return None


def event_timestamp(event: dict[str, object] | None) -> str | None:
    if event is None:
        return None
    return string_or_none(event.get("timestamp"))


def timestamp_min(*values: object) -> str | None:
    timestamps = [
        timestamp
        for timestamp in (string_or_none(value) for value in values)
        if timestamp is not None
    ]
    return min(timestamps) if timestamps else None


def timestamp_max(*values: object) -> str | None:
    timestamps = [
        timestamp
        for timestamp in (string_or_none(value) for value in values)
        if timestamp is not None
    ]
    return max(timestamps) if timestamps else None


def event_data(event: dict[str, object] | None) -> dict[str, object]:
    if event is None:
        return {}
    data = event.get("data")
    if isinstance(data, dict):
        return data
    return {}


def semantic_event_producer(
    producer_type: str,
    *,
    name: str | None = None,
) -> dict[str, object]:
    producer: dict[str, object] = {
        "type": producer_type,
    }
    if name is not None:
        producer["name"] = name
    return producer


def semantic_event_surfaces(
    *,
    transcript: str,
    replay: str = "visible",
    debug: str = "visible",
    model_input: str = "hidden",
) -> dict[str, object]:
    return {
        "transcript": transcript,
        "replay": replay,
        "debug": debug,
        "model_input": model_input,
    }


def semantic_event_outcome_from_status(status: str | None) -> str | None:
    normalized = string_or_none(status)
    if normalized is None:
        return None
    normalized = normalized.lower()
    if normalized in {"completed", "complete", "ok", "success", "succeeded"}:
        return "ok"
    if normalized in {"interrupted", "timeout", "timed_out"}:
        return "interrupted"
    if normalized in {"cancelled", "canceled"}:
        return "cancelled"
    if normalized in {"failed", "failure", "error", "errored"}:
        return "error"
    return None




SEMANTIC_EVENT_ENVELOPE_KEYS = frozenset(
    {
        "sequence",
        "kind",
        "producer",
        "surfaces",
        "annotations",
        "payload",
        "source_refs",
        "timestamp",
        "outcome",
        "model_run_ref",
        "tool_invocation_ref",
        "lineage",
        "native",
        "extras",
        "event_hash",
        "event_address",
        "closed",
    }
)


def enforce_event_envelope(
    events: list[dict[str, object]],
    *,
    provider_label: str,
) -> None:
    """Fail fast on envelope leakage — only emitter code can put keys on an event, so a
    violation is a normalizer bug, never a data condition."""
    for event in events:
        unknown = set(event) - SEMANTIC_EVENT_ENVELOPE_KEYS
        if unknown:
            raise ValueError(
                f"{provider_label} event at sequence {event.get('sequence')} leaks envelope keys: "
                f"{sorted(unknown)}"
            )


@dataclass
class SemanticEventBuilder:
    events: list[dict[str, object]] = field(default_factory=list)

    sequence_base: int = 0

    def append(
        self,
        *,
        kind: str,
        producer: dict[str, object],
        surfaces: dict[str, object],
        turn_id: str | None = None,
        payload: dict[str, object] | None = None,
        timestamp: str | None = None,
        source_refs: list[dict[str, object]] | None = None,
        outcome: str | None = None,
        model_run_ref: str | None = None,
        tool_invocation_ref: str | None = None,
        native: dict[str, object | None] | None = None,
    ) -> dict[str, object]:
        sequence = self.sequence_base + len(self.events) + 1
        event: dict[str, object] = {
            "sequence": sequence,
            "kind": kind,
            "producer": dict(producer),
            "surfaces": dict(surfaces),
            "payload": dict(payload or {}),
            "source_refs": [dict(source_ref) for source_ref in source_refs or []],
        }
        if turn_id is not None and turn_id != "session":
            set_normal_turn_id(event, turn_id)
        if timestamp is not None:
            event["timestamp"] = timestamp
        if outcome is not None:
            event["outcome"] = outcome
        if model_run_ref is not None:
            event["model_run_ref"] = model_run_ref
        if tool_invocation_ref is not None:
            event["tool_invocation_ref"] = tool_invocation_ref

        if native:
            anchors = {key: value for key, value in native.items() if value is not None}
            if anchors:
                event["native"] = anchors

        event["event_hash"] = compute_event_hash(event)
        self.events.append(event)
        return event


def warn_about_tool_group_records(
    *,
    warnings: list[str],
    provider_label: str,
    call_id: str,
    kind: str,
    records: list[object],
    required: bool = True,
) -> None:
    """Absence of a required record kind is an anomaly; absence of a supplementary
    kind (required=False) is a normal state — only multiples warn there."""
    if not records:
        if required:
            warnings.append(f"{provider_label} {call_id} missing {kind} record")
    elif len(records) > 1:
        warnings.append(
            f"{provider_label} {call_id} has {len(records)} {kind} records; using first"
        )


def warn_about_tool_group_kinds(
    *,
    warnings: list[str],
    provider_label: str,
    call_id: str,
    kinds: list[tuple[str, list[object]]],
    supplementary: frozenset[str] = frozenset(),
) -> None:
    for kind, records in kinds:
        warn_about_tool_group_records(
            warnings=warnings,
            provider_label=provider_label,
            call_id=call_id,
            kind=kind,
            records=records,
            required=kind not in supplementary,
        )


def tool_invocation_refs_by_call_id(
    tool_invocations: list[dict[str, object]],
) -> dict[str, str]:
    refs: dict[str, str] = {}
    for invocation in tool_invocations:
        call_id = string_or_none(invocation.get("call_id"))
        invocation_id = string_or_none(invocation.get("tool_invocation_id"))
        if call_id is not None and invocation_id is not None:
            refs[call_id] = invocation_id
    return refs


def attach_tool_invocation_refs_to_events(
    events: list[dict[str, object]],
    *,
    tool_invocations: list[dict[str, object]],
) -> None:
    refs_by_call_id = tool_invocation_refs_by_call_id(tool_invocations)
    for event in events:
        call_id = string_or_none(event_native(event).get("call_id"))
        if call_id is None:
            continue
        tool_invocation_ref = refs_by_call_id.get(call_id)
        if tool_invocation_ref is not None:
            event["tool_invocation_ref"] = tool_invocation_ref


def project_messages_from_events(
    events: list[dict[str, object]],
    *,
    project_event: Callable[
        [dict[str, object], int],
        tuple[dict[str, object] | list[dict[str, object]] | None, list[str]],
    ],
    index_base: int = 0,
) -> dict[str, object]:
    return project_records_from_events(
        events,
        record_key="messages",
        project_event=project_event,
        index_base=index_base,
    )


def project_usage_from_events(
    events: list[dict[str, object]],
    *,
    project_event: Callable[
        [dict[str, object], int],
        tuple[dict[str, object] | list[dict[str, object]] | None, list[str]],
    ],
    index_base: int = 0,
) -> dict[str, object]:
    return project_records_from_events(
        events,
        record_key="usage",
        project_event=project_event,
        index_base=index_base,
    )


def project_reasoning_trace_from_events(
    events: list[dict[str, object]],
    *,
    id_prefix: str,
    include_event: Callable[[dict[str, object]], bool] | None = None,
    require_content: bool = False,
) -> list[dict[str, object]]:
    reasoning_trace: list[dict[str, object]] = []
    for event in events:
        if event.get("kind") != "reasoning":
            continue
        if include_event is not None and not include_event(event):
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        content = string_or_none(payload.get("content"))
        if require_content and content is None:
            continue
        reasoning: dict[str, object] = {
            "reasoning_id": f"{id_prefix}-{len(reasoning_trace) + 1}",
            "visibility": string_or_none(payload.get("visibility")) or "visible",
        }
        if content is not None:
            reasoning["content"] = content
        timestamp = string_or_none(event.get("timestamp"))
        if timestamp is not None:
            reasoning["timestamp"] = timestamp
        source_refs = dict_list(event.get("source_refs"))
        if source_refs:
            reasoning["source_refs"] = source_refs
        reasoning_trace.append(reasoning)
    return reasoning_trace


def project_records_from_events(
    events: list[dict[str, object]],
    *,
    record_key: str,
    project_event: Callable[
        [dict[str, object], int],
        tuple[dict[str, object] | list[dict[str, object]] | None, list[str]],
    ],
    index_base: int = 0,
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    warnings: list[str] = []
    for event in events:
        record, event_warnings = project_event(event, index_base + len(records) + 1)
        warnings.extend(event_warnings)
        if isinstance(record, list):
            records.extend(record)
        elif record is not None:
            records.append(record)
    return {
        record_key: records,
        "warnings": warnings,
    }
