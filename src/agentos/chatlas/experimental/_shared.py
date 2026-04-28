from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Callable

@dataclass(frozen=True)
class _ExperimentalNormalizationResult:
    messages: list[dict[str, object]]
    model_runs: list[dict[str, object]]
    tool_invocations: list[dict[str, object]]
    events: list[dict[str, object]]
    usage: list[dict[str, object]]
    normalizer: str
    source_mode: str
    warnings: list[str]
    unsupported_concepts: list[str]
    metadata: dict[str, object]

def _first_event_for_turn(
    events: list[dict[str, object]],
    *,
    turn_id: str | None,
    event_type: str,
) -> dict[str, object] | None:
    for event in events:
        if event.get("type") != event_type:
            continue
        if turn_id is not None and _event_turn_id(event) != turn_id:
            continue
        if turn_id is None and _event_turn_id(event) is not None:
            continue
        return event
    return None

def _event_turn_id(event: dict[str, object]) -> str | None:
    turn_id = _string_or_none(event.get("turn_id"))
    if turn_id is not None:
        return turn_id
    data = event.get("data")
    if isinstance(data, dict):
        turn_id = _string_or_none(data.get("turn_id"))
        if turn_id is not None:
            return turn_id
    payload = event.get("payload")
    if isinstance(payload, dict):
        return _string_or_none(payload.get("turn_id"))
    return None

def _event_timestamp(event: dict[str, object] | None) -> str | None:
    if event is None:
        return None
    return _string_or_none(event.get("timestamp"))

def _event_data(event: dict[str, object] | None) -> dict[str, object]:
    if event is None:
        return {}
    data = event.get("data")
    if isinstance(data, dict):
        return data
    return {}

def _semantic_event_producer(
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

def _semantic_event_surfaces(
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

def _semantic_event_outcome_from_status(status: str | None) -> str | None:
    normalized = _string_or_none(status)
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

@dataclass
class _SemanticEventBuilder:
    events: list[dict[str, object]] = field(default_factory=list)

    def append(
        self,
        *,
        kind: str,
        producer: dict[str, object],
        surfaces: dict[str, object],
        interaction_ref: str,
        payload: dict[str, object] | None = None,
        timestamp: str | None = None,
        source_refs: list[dict[str, object]] | None = None,
        outcome: str | None = None,
        model_run_ref: str | None = None,
        tool_invocation_ref: str | None = None,
        legacy_type: str | None = None,
        legacy_data: dict[str, object] | None = None,
        legacy_native: dict[str, object] | None = None,
        extra: dict[str, object | None] | None = None,
    ) -> dict[str, object]:
        sequence = len(self.events) + 1
        event: dict[str, object] = {
            "event_id": f"event-{sequence}",
            "sequence": sequence,
            "kind": kind,
            "producer": dict(producer),
            "surfaces": dict(surfaces),
            "interaction_ref": interaction_ref,
            "payload": dict(payload or {}),
            "source_refs": [dict(source_ref) for source_ref in source_refs or []],
        }
        if timestamp is not None:
            event["timestamp"] = timestamp
        if outcome is not None:
            event["outcome"] = outcome
        if model_run_ref is not None:
            event["model_run_ref"] = model_run_ref
        if tool_invocation_ref is not None:
            event["tool_invocation_ref"] = tool_invocation_ref

        # Transitional fields stay until semantic events fully replace provider-shaped rows.
        if legacy_type is not None:
            event["type"] = legacy_type
        if legacy_data is not None:
            event["data"] = dict(legacy_data)
        if legacy_native is not None:
            event["native"] = dict(legacy_native)
        if extra:
            for key, value in extra.items():
                if value is not None:
                    event[key] = value

        self.events.append(event)
        return event

def _warn_about_tool_group_records(
    *,
    warnings: list[str],
    provider_label: str,
    call_id: str,
    kind: str,
    records: list[object],
) -> None:
    if not records:
        warnings.append(f"{provider_label} {call_id} missing {kind} record")
    elif len(records) > 1:
        warnings.append(
            f"{provider_label} {call_id} has {len(records)} {kind} records; using first"
        )

def _tool_invocation_refs_by_call_id(
    tool_invocations: list[dict[str, object]],
) -> dict[str, str]:
    refs: dict[str, str] = {}
    for invocation in tool_invocations:
        call_id = _string_or_none(invocation.get("call_id"))
        invocation_id = _string_or_none(invocation.get("tool_invocation_id"))
        if call_id is not None and invocation_id is not None:
            refs[call_id] = invocation_id
    return refs

def _attach_event_refs_to_tool_invocations(
    tool_invocations: list[dict[str, object]],
    *,
    events: list[dict[str, object]],
) -> None:
    event_refs_by_tool_invocation: dict[str, list[str]] = {}
    for event in events:
        tool_invocation_ref = _string_or_none(event.get("tool_invocation_ref"))
        event_id = _string_or_none(event.get("event_id"))
        if tool_invocation_ref is None or event_id is None:
            continue
        event_refs_by_tool_invocation.setdefault(tool_invocation_ref, []).append(
            event_id,
        )

    for invocation in tool_invocations:
        invocation_id = _string_or_none(invocation.get("tool_invocation_id"))
        if invocation_id is None:
            continue
        event_refs = event_refs_by_tool_invocation.get(invocation_id)
        if event_refs:
            invocation["event_refs"] = event_refs

def _attach_tool_invocation_refs_to_events(
    events: list[dict[str, object]],
    *,
    tool_invocations: list[dict[str, object]],
) -> None:
    refs_by_call_id = _tool_invocation_refs_by_call_id(tool_invocations)
    for event in events:
        call_id = _string_or_none(event.get("call_id"))
        if call_id is None:
            continue
        tool_invocation_ref = refs_by_call_id.get(call_id)
        if tool_invocation_ref is not None:
            event["tool_invocation_ref"] = tool_invocation_ref

def _project_messages_from_events(
    events: list[dict[str, object]],
    *,
    project_event: Callable[
        [dict[str, object], int],
        tuple[dict[str, object] | list[dict[str, object]] | None, list[str]],
    ],
) -> dict[str, object]:
    return _project_records_from_events(
        events,
        record_key="messages",
        project_event=project_event,
    )

def _project_usage_from_events(
    events: list[dict[str, object]],
    *,
    project_event: Callable[
        [dict[str, object], int],
        tuple[dict[str, object] | list[dict[str, object]] | None, list[str]],
    ],
) -> dict[str, object]:
    return _project_records_from_events(
        events,
        record_key="usage",
        project_event=project_event,
    )

def _project_records_from_events(
    events: list[dict[str, object]],
    *,
    record_key: str,
    project_event: Callable[
        [dict[str, object], int],
        tuple[dict[str, object] | list[dict[str, object]] | None, list[str]],
    ],
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    warnings: list[str] = []
    for event in events:
        record, event_warnings = project_event(event, len(records) + 1)
        warnings.extend(event_warnings)
        if isinstance(record, list):
            records.extend(record)
        elif record is not None:
            records.append(record)
    return {
        record_key: records,
        "warnings": warnings,
    }

def _event_refs_for_sequence_span(
    events: list[dict[str, object]],
    *,
    start_sequence: int,
    end_sequence: int,
) -> list[str]:
    refs: list[str] = []
    for event in events:
        sequence = _int_or_none(event.get("sequence"))
        event_id = _string_or_none(event.get("event_id"))
        if sequence is None or event_id is None:
            continue
        if start_sequence <= sequence <= end_sequence:
            refs.append(event_id)
    return refs

def _primary_backing_artifact(session: dict[str, Any]) -> dict[str, Any] | None:
    primary = session.get("primary_backing_artifact")
    if isinstance(primary, dict):
        return primary
    artifacts = session.get("backing_artifacts")
    if not isinstance(artifacts, list):
        return None
    for artifact in artifacts:
        if isinstance(artifact, dict) and artifact.get("role") == "transcript":
            return artifact
    return None

def _source_ref_id_for_artifact(
    artifact: dict[str, Any],
    *,
    sources: list[dict[str, object]],
) -> str | None:
    role = artifact.get("role")
    storage_kind = artifact.get("storage_kind")
    path = artifact.get("path")
    for source in sources:
        if (
            source.get("role") == role
            and source.get("storage_kind") == storage_kind
            and source.get("path") == path
        ):
            return _string_or_none(source.get("source_ref_id"))
    return None

def _experimental_unsupported_concepts(
    *,
    messages: list[dict[str, object]],
    model_runs: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
) -> list[str]:
    unsupported: list[str] = []
    if not messages:
        unsupported.append("messages")
    if not model_runs:
        unsupported.append("model_runs")
    if not tool_invocations:
        unsupported.append("tool_invocations")
    if not events:
        unsupported.append("events")
    return unsupported

def _experimental_normalization_metadata(
    *,
    messages: list[dict[str, object]],
    model_runs: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
    usage: list[dict[str, object]],
    deferred_concepts: list[str],
) -> dict[str, object]:
    return {
        "counts": _experimental_normalized_counts(
            messages=messages,
            model_runs=model_runs,
            tool_invocations=tool_invocations,
            events=events,
            usage=usage,
        ),
        "raw_counts": {},
        "coverage": _experimental_normalization_coverage(
            messages=messages,
            model_runs=model_runs,
            tool_invocations=tool_invocations,
            events=events,
            usage=usage,
        ),
        "deferred_concepts": deferred_concepts,
    }

def _experimental_normalized_counts(
    *,
    messages: list[dict[str, object]],
    model_runs: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
    usage: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "messages": len(messages),
        "model_runs": len(model_runs),
        "tool_invocations": len(tool_invocations),
        "events": len(events),
        "usage": len(usage),
        "reasoning_traces": _model_run_reasoning_count(model_runs),
    }

def _experimental_normalization_coverage(
    *,
    messages: list[dict[str, object]],
    model_runs: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
    usage: list[dict[str, object]],
) -> dict[str, object]:
    reasoning_count = _model_run_reasoning_count(model_runs)
    return {
        "messages": {
            "status": _coverage_status(len(messages)),
            "normalized_count": len(messages),
        },
        "model_runs": {
            "status": _coverage_status(len(model_runs)),
            "normalized_count": len(model_runs),
        },
        "tool_invocations": {
            "status": _coverage_status(len(tool_invocations)),
            "normalized_count": len(tool_invocations),
        },
        "events": {
            "status": _coverage_status(len(events)),
            "normalized_count": len(events),
        },
        "reasoning": {
            "status": _coverage_status(reasoning_count),
            "normalized_count": reasoning_count,
        },
        "usage": {
            "status": _coverage_status(len(usage)),
            "normalized_count": len(usage),
        },
    }

def _model_run_reasoning_count(model_runs: list[dict[str, object]]) -> int:
    count = 0
    for model_run in model_runs:
        reasoning_trace = model_run.get("reasoning_trace")
        if isinstance(reasoning_trace, list):
            count += len(reasoning_trace)
    return count

def _coverage_status(count: int) -> str:
    return "normalized" if count else "missing"

def _count_payload(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        key: count
        for key, count in value.items()
        if isinstance(key, str) and isinstance(count, int) and not isinstance(count, bool)
    }

def _sorted_count_dict(counts: dict[str, int]) -> dict[str, int]:
    return {key: counts[key] for key in sorted(counts)}

def _copy_present_fields(
    target: dict[str, object],
    source: dict[str, Any],
    field_map: tuple[tuple[str, str], ...],
) -> None:
    for source_key, target_key in field_map:
        value = source.get(source_key)
        if value is not None:
            target[target_key] = value

def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None

def _int_or_zero(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0

def _source_ref_first_event_index(source_refs: object) -> int | None:
    for event_index in _source_ref_event_indices(source_refs):
        return event_index
    return None

def _source_ref_first_record_index(source_refs: object) -> int | None:
    for record_index in _source_ref_record_indices(source_refs):
        return record_index
    return None

def _source_ref_event_indices(source_refs: object) -> list[int]:
    if not isinstance(source_refs, list):
        return []
    event_indices: list[int] = []
    for source_ref in source_refs:
        if not isinstance(source_ref, dict):
            continue
        event_index = _int_or_none(source_ref.get("event_index"))
        if event_index is not None:
            event_indices.append(event_index)
    return event_indices

def _source_ref_record_indices(source_refs: object) -> list[int]:
    if not isinstance(source_refs, list):
        return []
    record_indices: list[int] = []
    for source_ref in source_refs:
        if not isinstance(source_ref, dict):
            continue
        record_index = _int_or_none(source_ref.get("record_index"))
        if record_index is not None:
            record_indices.append(record_index)
    return record_indices

def _record_native_dict(record: dict[str, object]) -> dict[str, object]:
    native = record.get("native")
    if isinstance(native, dict):
        return native
    return {}

def _record_native_int_field(
    record: dict[str, object],
    key: str,
) -> int | None:
    return _int_or_none(_record_native_dict(record).get(key))

def _record_native_string_field(
    record: dict[str, object],
    key: str,
) -> str | None:
    return _string_or_none(_record_native_dict(record).get(key))

def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]

def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]

def _dedupe_dicts(values: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen: set[str] = set()
    for value in values:
        identity = json.dumps(value, sort_keys=True, default=str)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(value)
    return deduped

def _jsonable_identity(value: object) -> str:
    return repr(value)

def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped

__all__ = [
    "_ExperimentalNormalizationResult",
    "_first_event_for_turn",
    "_event_turn_id",
    "_event_timestamp",
    "_event_data",
    "_semantic_event_producer",
    "_semantic_event_surfaces",
    "_semantic_event_outcome_from_status",
    "_SemanticEventBuilder",
    "_warn_about_tool_group_records",
    "_tool_invocation_refs_by_call_id",
    "_attach_event_refs_to_tool_invocations",
    "_attach_tool_invocation_refs_to_events",
    "_project_messages_from_events",
    "_project_usage_from_events",
    "_project_records_from_events",
    "_event_refs_for_sequence_span",
    "_primary_backing_artifact",
    "_source_ref_id_for_artifact",
    "_experimental_unsupported_concepts",
    "_experimental_normalization_metadata",
    "_experimental_normalized_counts",
    "_experimental_normalization_coverage",
    "_model_run_reasoning_count",
    "_coverage_status",
    "_count_payload",
    "_sorted_count_dict",
    "_copy_present_fields",
    "_int_or_none",
    "_int_or_zero",
    "_source_ref_first_event_index",
    "_source_ref_first_record_index",
    "_source_ref_event_indices",
    "_source_ref_record_indices",
    "_record_native_dict",
    "_record_native_int_field",
    "_record_native_string_field",
    "_dict_list",
    "_string_list",
    "_dedupe_dicts",
    "_jsonable_identity",
    "_string_or_none",
]
