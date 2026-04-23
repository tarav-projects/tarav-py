from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

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
        return _string_or_none(data.get("turn_id"))
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

def _copilot_usage_billing_count(usage: list[dict[str, object]]) -> int:
    count = 0
    for item in usage:
        provider_billing_units = item.get("provider_billing_units")
        if isinstance(provider_billing_units, dict):
            count += 1
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
    "_tool_invocation_refs_by_call_id",
    "_attach_event_refs_to_tool_invocations",
    "_primary_backing_artifact",
    "_source_ref_id_for_artifact",
    "_experimental_unsupported_concepts",
    "_experimental_normalization_metadata",
    "_experimental_normalized_counts",
    "_experimental_normalization_coverage",
    "_model_run_reasoning_count",
    "_copilot_usage_billing_count",
    "_coverage_status",
    "_count_payload",
    "_sorted_count_dict",
    "_copy_present_fields",
    "_int_or_none",
    "_int_or_zero",
    "_source_ref_first_event_index",
    "_source_ref_event_indices",
    "_record_native_dict",
    "_record_native_int_field",
    "_record_native_string_field",
    "_dict_list",
    "_string_list",
    "_dedupe_dicts",
    "_jsonable_identity",
    "_string_or_none",
]
