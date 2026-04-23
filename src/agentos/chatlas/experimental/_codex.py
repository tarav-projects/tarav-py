from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from agentos.chat.extractors.codex import is_codex_rollout_path

from ._shared import *
from ._transcript import _experimental_clean_transcript_result

_CODEX_CONTEXT_MESSAGE_PREFIXES = (
    "<INSTRUCTIONS>",
    "<environment_context>",
    "# AGENTS.md",
    "<skill>",
    "<turn_aborted>",
    "<collaboration_mode>",
    "<permissions",
    "<system-reminder>",
)

@dataclass(frozen=True)
class _CodexRawRecord:
    record_index: int
    line: int
    timestamp: str | None
    record_type: str | None
    payload: dict[str, Any]
    source_refs: list[dict[str, object]]

@dataclass(frozen=True)
class _CodexRawRollout:
    path: Path
    source_ref_id: str | None
    records: list[_CodexRawRecord]
    warnings: list[str]

def _experimental_normalize_codex_raw_rollout(
    session: dict[str, Any],
    *,
    sources: list[dict[str, object]],
) -> _ExperimentalNormalizationResult | None:
    primary_artifact = _primary_backing_artifact(session)
    if primary_artifact is None:
        return None

    primary_path_text = _string_or_none(primary_artifact.get("path"))
    if primary_path_text is None:
        return None

    primary_path = Path(primary_path_text)
    if not primary_path.is_file():
        return None

    try:
        if not is_codex_rollout_path(primary_path):
            return None
    except OSError:
        return None

    source_ref_id = _source_ref_id_for_artifact(primary_artifact, sources=sources)
    rollout = _load_codex_raw_rollout_records(
        primary_path,
        source_ref_id=source_ref_id,
    )
    message_result = _codex_messages_from_raw_rollout(rollout)
    tool_result = _codex_tool_invocations_from_raw_rollout(rollout)
    messages = _dict_list(message_result["messages"])
    tool_invocations = _dict_list(tool_result["tool_invocations"])
    tool_invocation_refs_by_call_id = _tool_invocation_refs_by_call_id(
        tool_invocations,
    )
    event_result = _codex_events_from_raw_rollout(
        rollout,
        tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
    )
    events = _dict_list(event_result["events"])
    _attach_event_refs_to_tool_invocations(
        tool_invocations,
        events=events,
    )
    model_run_result = _codex_model_runs_from_raw_rollout(
        rollout,
        messages=messages,
        tool_invocations=tool_invocations,
        events=events,
    )
    model_runs = _dict_list(model_run_result["model_runs"])
    usage: list[dict[str, object]] = []
    raw_counts = _codex_raw_rollout_counts(rollout)
    residual_unsupported_concepts = _codex_residual_unsupported_concepts(
        raw_counts=raw_counts,
        events=events,
    )
    if messages or tool_invocations or events or model_runs:
        warnings = [
            *rollout.warnings,
            (
                f"codex raw rollout parsed for future normalization: "
                f"{len(rollout.records)} records"
            ),
        ]
        if messages:
            warnings.append(
                "codex raw rollout messages normalized from "
                f"response_item.message: {len(messages)} messages"
            )
        if tool_invocations:
            warnings.append(
                "codex raw rollout tool invocations normalized by call_id: "
                f"{len(tool_invocations)} invocations"
            )
        if events:
            warnings.append(
                "codex raw rollout events normalized from event_msg: "
                f"{len(events)} events"
            )
        if model_runs:
            warnings.append(
                "codex raw rollout model runs normalized: "
                f"{len(model_runs)} runs"
            )
        warnings.extend(_string_list(message_result["warnings"]))
        warnings.extend(_string_list(tool_result["warnings"]))
        warnings.extend(_string_list(event_result["warnings"]))
        warnings.extend(_string_list(model_run_result["warnings"]))
        warnings.extend(
            _codex_count_oriented_warnings(
                raw_counts=raw_counts,
                messages=messages,
                model_runs=model_runs,
                tool_invocations=tool_invocations,
                events=events,
                usage=usage,
                residual_unsupported_concepts=residual_unsupported_concepts,
            )
        )
        return _ExperimentalNormalizationResult(
            messages=messages,
            model_runs=model_runs,
            tool_invocations=tool_invocations,
            events=events,
            usage=usage,
            normalizer="codex.raw_rollout.experimental.v1",
            source_mode="codex_raw_rollout",
            warnings=warnings,
            unsupported_concepts=[
                *_experimental_unsupported_concepts(
                    messages=messages,
                    model_runs=model_runs,
                    tool_invocations=tool_invocations,
                    events=events,
                ),
                *residual_unsupported_concepts,
            ],
            metadata=_codex_normalization_metadata(
                raw_counts=raw_counts,
                messages=messages,
                model_runs=model_runs,
                tool_invocations=tool_invocations,
                events=events,
                usage=usage,
                deferred_concepts=residual_unsupported_concepts,
            ),
        )

    fallback = _experimental_clean_transcript_result(
        session,
        sources=sources,
        normalizer="codex.raw_rollout.experimental.v1",
    )
    warnings = [
        *rollout.warnings,
        (
            f"codex raw rollout parsed for future normalization: "
            f"{len(rollout.records)} records"
        ),
        "codex raw rollout contained no response_item.message records; using clean transcript fallback",
        *_string_list(message_result["warnings"]),
        *_string_list(tool_result["warnings"]),
        *_string_list(event_result["warnings"]),
        *_string_list(model_run_result["warnings"]),
        *fallback.warnings,
    ]
    return _ExperimentalNormalizationResult(
        messages=fallback.messages,
        model_runs=fallback.model_runs,
        tool_invocations=fallback.tool_invocations,
        events=fallback.events,
        usage=fallback.usage,
        normalizer=fallback.normalizer,
        source_mode=fallback.source_mode,
        warnings=warnings,
        unsupported_concepts=fallback.unsupported_concepts,
        metadata=fallback.metadata,
    )

def _codex_messages_from_raw_rollout(
    rollout: _CodexRawRollout,
) -> dict[str, object]:
    messages: list[dict[str, object]] = []
    warnings: list[str] = []
    for record in rollout.records:
        if record.record_type != "response_item":
            continue

        payload_type = _string_or_none(record.payload.get("type"))
        if payload_type != "message":
            continue

        role = _string_or_none(record.payload.get("role"))
        if role is None:
            role = "unknown"
            warnings.append(
                f"codex message record {record.record_index} has no role"
            )

        content, content_types, content_warnings = _codex_message_content_blocks(
            record,
        )
        warnings.extend(content_warnings)

        message: dict[str, object] = {
            "message_id": f"message-{len(messages) + 1}",
            "role": role,
            "visibility": _codex_message_visibility(role, content),
            "content": content,
            "native": {
                "record_type": record.record_type,
                "payload_type": payload_type,
                "role": role,
            },
        }
        if record.timestamp is not None:
            message["timestamp"] = record.timestamp
        if record.source_refs:
            message["source_refs"] = record.source_refs
        if content_types:
            native = message["native"]
            if isinstance(native, dict):
                native["content_types"] = content_types
        messages.append(message)

    return {
        "messages": messages,
        "warnings": warnings,
    }

def _codex_raw_rollout_counts(rollout: _CodexRawRollout) -> dict[str, object]:
    record_types: dict[str, int] = {}
    response_item_types: dict[str, int] = {}
    event_msg_types: dict[str, int] = {}
    for record in rollout.records:
        record_type = record.record_type or "unknown"
        record_types[record_type] = record_types.get(record_type, 0) + 1
        payload_type = _string_or_none(record.payload.get("type")) or "unknown"
        if record_type == "response_item":
            response_item_types[payload_type] = response_item_types.get(payload_type, 0) + 1
        elif record_type == "event_msg":
            event_msg_types[payload_type] = event_msg_types.get(payload_type, 0) + 1
    return {
        "records": len(rollout.records),
        "record_types": _sorted_count_dict(record_types),
        "response_item_types": _sorted_count_dict(response_item_types),
        "event_msg_types": _sorted_count_dict(event_msg_types),
        "parse_warning_count": len(rollout.warnings),
    }

def _codex_normalization_metadata(
    *,
    raw_counts: dict[str, object],
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
        "raw_counts": raw_counts,
        "coverage": _codex_normalization_coverage(
            raw_counts=raw_counts,
            messages=messages,
            model_runs=model_runs,
            tool_invocations=tool_invocations,
            events=events,
            usage=usage,
        ),
        "deferred_concepts": deferred_concepts,
    }

def _codex_normalization_coverage(
    *,
    raw_counts: dict[str, object],
    messages: list[dict[str, object]],
    model_runs: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
    usage: list[dict[str, object]],
) -> dict[str, object]:
    response_item_types = _count_payload(raw_counts.get("response_item_types"))
    event_msg_types = _count_payload(raw_counts.get("event_msg_types"))
    reasoning_count = _model_run_reasoning_count(model_runs)
    token_count_events = event_msg_types.get("token_count", 0)
    return {
        "messages": {
            "status": _coverage_status(len(messages)),
            "raw_count": response_item_types.get("message", 0),
            "normalized_count": len(messages),
        },
        "model_runs": {
            "status": _coverage_status(len(model_runs)),
            "raw_turn_context_count": _count_payload(raw_counts.get("record_types")).get("turn_context", 0),
            "normalized_count": len(model_runs),
        },
        "tool_invocations": {
            "status": _coverage_status(len(tool_invocations)),
            "raw_function_call_count": response_item_types.get("function_call", 0),
            "raw_function_call_output_count": response_item_types.get("function_call_output", 0),
            "raw_exec_command_end_count": event_msg_types.get("exec_command_end", 0),
            "normalized_count": len(tool_invocations),
        },
        "events": {
            "status": _coverage_status(len(events)),
            "raw_count": _count_payload(raw_counts.get("record_types")).get("event_msg", 0),
            "normalized_count": len(events),
        },
        "reasoning": {
            "status": _coverage_status(reasoning_count),
            "raw_count": response_item_types.get("reasoning", 0),
            "normalized_count": reasoning_count,
        },
        "usage": {
            "status": "event_only" if token_count_events else "no_raw_evidence",
            "raw_token_count_event_count": token_count_events,
            "normalized_count": len(usage),
        },
        "cost": {
            "status": "event_only" if _codex_has_cost_like_events(events) else "no_raw_evidence",
            "normalized_count": 0,
        },
    }

def _codex_residual_unsupported_concepts(
    *,
    raw_counts: dict[str, object],
    events: list[dict[str, object]],
) -> list[str]:
    unsupported: list[str] = []
    event_msg_types = _count_payload(raw_counts.get("event_msg_types"))
    if event_msg_types.get("token_count", 0):
        unsupported.append("usage")
    if _codex_has_cost_like_events(events):
        unsupported.append("cost")
    return unsupported

def _codex_count_oriented_warnings(
    *,
    raw_counts: dict[str, object],
    messages: list[dict[str, object]],
    model_runs: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
    usage: list[dict[str, object]],
    residual_unsupported_concepts: list[str],
) -> list[str]:
    warnings: list[str] = []
    coverage = _codex_normalization_coverage(
        raw_counts=raw_counts,
        messages=messages,
        model_runs=model_runs,
        tool_invocations=tool_invocations,
        events=events,
        usage=usage,
    )
    for concept in ("messages", "events", "reasoning"):
        detail = coverage.get(concept)
        if not isinstance(detail, dict):
            continue
        raw_count = _int_or_zero(detail.get("raw_count"))
        normalized_count = _int_or_zero(detail.get("normalized_count"))
        if raw_count and raw_count != normalized_count:
            warnings.append(
                f"codex {concept} partial normalization: raw={raw_count} normalized={normalized_count}"
            )

    tool_detail = coverage.get("tool_invocations")
    if isinstance(tool_detail, dict):
        raw_function_call_count = _int_or_zero(tool_detail.get("raw_function_call_count"))
        normalized_count = _int_or_zero(tool_detail.get("normalized_count"))
        if raw_function_call_count and raw_function_call_count != normalized_count:
            warnings.append(
                "codex tool_invocations partial normalization: "
                f"raw_function_call={raw_function_call_count} normalized={normalized_count}"
            )

    if "usage" in residual_unsupported_concepts:
        token_count_events = _int_or_zero(
            _count_payload(raw_counts.get("event_msg_types")).get("token_count")
        )
        warnings.append(
            "codex token_count events preserved as events only; "
            f"stable usage projection is deferred: {token_count_events} events"
        )
    if "cost" in residual_unsupported_concepts:
        warnings.append(
            "codex cost-like evidence is preserved as events only; stable cost projection is deferred"
        )
    return warnings

def _codex_has_cost_like_events(events: list[dict[str, object]]) -> bool:
    for event in events:
        if event.get("type") != "codex.token_count":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        rate_limits = data.get("rate_limits")
        if not isinstance(rate_limits, dict):
            continue
        credits = rate_limits.get("credits")
        if credits is not None:
            return True
    return False

def _codex_events_from_raw_rollout(
    rollout: _CodexRawRollout,
    *,
    tool_invocation_refs_by_call_id: dict[str, str],
) -> dict[str, object]:
    events: list[dict[str, object]] = []
    warnings: list[str] = []
    for record in rollout.records:
        if record.record_type != "event_msg":
            continue
        payload_type = _string_or_none(record.payload.get("type"))
        if payload_type is None:
            payload_type = "unknown"
            warnings.append(
                f"codex event record {record.record_index} has no payload type"
            )

        event: dict[str, object] = {
            "event_id": f"event-{len(events) + 1}",
            "type": f"codex.{payload_type}",
            "data": _codex_event_data(record.payload),
            "native": {
                "record_type": record.record_type,
                "payload_type": payload_type,
                "record_index": record.record_index,
            },
        }
        if record.timestamp is not None:
            event["timestamp"] = record.timestamp
        if record.source_refs:
            event["source_refs"] = record.source_refs

        call_id = _string_or_none(record.payload.get("call_id"))
        if call_id is not None:
            event["call_id"] = call_id
            tool_invocation_ref = tool_invocation_refs_by_call_id.get(call_id)
            if tool_invocation_ref is not None:
                event["tool_invocation_ref"] = tool_invocation_ref
            elif payload_type == "exec_command_end":
                warnings.append(
                    f"codex exec_command_end event record {record.record_index} has no matching tool invocation for call_id {call_id}"
                )

        turn_id = _string_or_none(record.payload.get("turn_id"))
        if turn_id is not None:
            event["turn_id"] = turn_id
        events.append(event)

    return {
        "events": events,
        "warnings": warnings,
    }

def _codex_model_runs_from_raw_rollout(
    rollout: _CodexRawRollout,
    *,
    messages: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
) -> dict[str, object]:
    warnings: list[str] = []
    turn_context_records = [
        record for record in rollout.records if record.record_type == "turn_context"
    ]
    reasoning_trace = _codex_reasoning_trace_from_raw_rollout(rollout)
    session_meta = _codex_session_meta_payload(rollout)

    model_runs: list[dict[str, object]] = []
    if turn_context_records:
        for record in turn_context_records:
            model_runs.append(
                _codex_model_run_from_turn_context(
                    record=record,
                    index=len(model_runs) + 1,
                    session_meta=session_meta,
                    messages=messages,
                    tool_invocations=tool_invocations,
                    events=events,
                    reasoning_trace=reasoning_trace,
                    single_model_run=len(turn_context_records) == 1,
                )
            )
    else:
        inferred_turn_ids = _codex_inferred_model_run_turn_ids(
            events=events,
            tool_invocations=tool_invocations,
        )
        if reasoning_trace or inferred_turn_ids:
            if not inferred_turn_ids:
                inferred_turn_ids = [None]
            for turn_id in inferred_turn_ids:
                model_runs.append(
                    _codex_inferred_model_run(
                        turn_id=turn_id,
                        index=len(model_runs) + 1,
                        session_meta=session_meta,
                        messages=messages,
                        tool_invocations=tool_invocations,
                        events=events,
                        reasoning_trace=reasoning_trace,
                        single_model_run=len(inferred_turn_ids) == 1,
                    )
                )
            warnings.append(
                "codex model run inferred without turn_context record"
            )

    if len(model_runs) != 1 and reasoning_trace:
        warnings.append(
            "codex reasoning records do not expose turn_id; reasoning_trace was not attached to multiple model runs"
        )

    return {
        "model_runs": model_runs,
        "warnings": warnings,
    }

def _codex_model_run_from_turn_context(
    *,
    record: _CodexRawRecord,
    index: int,
    session_meta: dict[str, Any] | None,
    messages: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
    reasoning_trace: list[dict[str, object]],
    single_model_run: bool,
) -> dict[str, object]:
    turn_id = _string_or_none(record.payload.get("turn_id"))
    model_run = _codex_base_model_run(
        index=index,
        turn_id=turn_id,
        session_meta=session_meta,
        events=events,
        turn_context=record.payload,
    )
    model_run["native"] = {
        "turn_context_present": True,
        "turn_context_record_index": record.record_index,
    }
    if record.source_refs:
        model_run["source_refs"] = record.source_refs
    _codex_attach_model_run_refs(
        model_run,
        turn_id=turn_id,
        messages=messages,
        tool_invocations=tool_invocations,
        events=events,
        reasoning_trace=reasoning_trace,
        single_model_run=single_model_run,
    )
    return model_run

def _codex_inferred_model_run(
    *,
    turn_id: str | None,
    index: int,
    session_meta: dict[str, Any] | None,
    messages: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
    reasoning_trace: list[dict[str, object]],
    single_model_run: bool,
) -> dict[str, object]:
    model_run = _codex_base_model_run(
        index=index,
        turn_id=turn_id,
        session_meta=session_meta,
        events=events,
        turn_context=None,
    )
    model_run["native"] = {
        "turn_context_present": False,
    }
    _codex_attach_model_run_refs(
        model_run,
        turn_id=turn_id,
        messages=messages,
        tool_invocations=tool_invocations,
        events=events,
        reasoning_trace=reasoning_trace,
        single_model_run=single_model_run,
    )
    return model_run

def _codex_base_model_run(
    *,
    index: int,
    turn_id: str | None,
    session_meta: dict[str, Any] | None,
    events: list[dict[str, object]],
    turn_context: dict[str, Any] | None,
) -> dict[str, object]:
    task_started = _first_event_for_turn(
        events,
        turn_id=turn_id,
        event_type="codex.task_started",
    )
    task_complete = _first_event_for_turn(
        events,
        turn_id=turn_id,
        event_type="codex.task_complete",
    )
    model_run: dict[str, object] = {
        "model_run_id": f"model-run-{index}",
        "provider": "codex",
        "status": _codex_model_run_status(task_started, task_complete),
    }
    if turn_id is not None:
        model_run["turn_id"] = turn_id

    model_provider = _string_or_none(
        session_meta.get("model_provider") if session_meta is not None else None
    )
    if model_provider is not None:
        model_run["model_provider"] = model_provider

    if turn_context is not None:
        _codex_apply_turn_context_fields(model_run, turn_context)

    started_at = _event_timestamp(task_started) or _string_or_none(
        turn_context.get("timestamp") if turn_context is not None else None
    )
    if started_at is not None:
        model_run["started_at"] = started_at
    ended_at = _event_timestamp(task_complete)
    if ended_at is not None:
        model_run["ended_at"] = ended_at

    task_started_data = _event_data(task_started)
    model_context_window = task_started_data.get("model_context_window")
    if model_context_window is not None:
        model_run["model_context_window"] = model_context_window

    task_complete_data = _event_data(task_complete)
    duration_ms = task_complete_data.get("duration_ms")
    if duration_ms is not None:
        model_run["duration_ms"] = duration_ms

    return model_run

def _codex_apply_turn_context_fields(
    model_run: dict[str, object],
    turn_context: dict[str, Any],
) -> None:
    model = _string_or_none(turn_context.get("model"))
    if model is not None:
        model_run["model"] = model
    effort = _string_or_none(turn_context.get("effort"))
    if effort is not None:
        model_run["reasoning_effort"] = effort
    for key in (
        "cwd",
        "approval_policy",
        "sandbox_policy",
        "current_date",
        "timezone",
        "truncation_policy",
        "realtime_active",
    ):
        value = turn_context.get(key)
        if value is not None:
            model_run[key] = value
    collaboration_mode = _codex_collaboration_mode(turn_context.get("collaboration_mode"))
    if collaboration_mode is not None:
        model_run["collaboration_mode"] = collaboration_mode

def _codex_collaboration_mode(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    mode = _string_or_none(value.get("mode"))
    payload: dict[str, object] = {}
    if mode is not None:
        payload["mode"] = mode
    settings = value.get("settings")
    if isinstance(settings, dict):
        safe_settings: dict[str, object] = {}
        for key in ("model", "reasoning_effort"):
            setting_value = settings.get(key)
            if setting_value is not None:
                safe_settings[key] = setting_value
        if safe_settings:
            payload["settings"] = safe_settings
    return payload or None

def _codex_attach_model_run_refs(
    model_run: dict[str, object],
    *,
    turn_id: str | None,
    messages: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
    reasoning_trace: list[dict[str, object]],
    single_model_run: bool,
) -> None:
    message_refs = _codex_model_run_message_refs(messages, single_model_run)
    if message_refs:
        model_run["message_refs"] = message_refs
    tool_refs = _codex_model_run_tool_refs(tool_invocations, turn_id, single_model_run)
    if tool_refs:
        model_run["tool_invocation_refs"] = tool_refs
    event_refs = _codex_model_run_event_refs(events, turn_id, single_model_run)
    if event_refs:
        model_run["event_refs"] = event_refs
    if reasoning_trace and single_model_run:
        model_run["reasoning_trace"] = reasoning_trace

def _codex_model_run_message_refs(
    messages: list[dict[str, object]],
    single_model_run: bool,
) -> list[str]:
    if not single_model_run:
        return []
    return [
        message_id
        for message in messages
        if (message_id := _string_or_none(message.get("message_id"))) is not None
    ]

def _codex_model_run_tool_refs(
    tool_invocations: list[dict[str, object]],
    turn_id: str | None,
    single_model_run: bool,
) -> list[str]:
    refs: list[str] = []
    for invocation in tool_invocations:
        invocation_id = _string_or_none(invocation.get("tool_invocation_id"))
        if invocation_id is None:
            continue
        if single_model_run:
            refs.append(invocation_id)
            continue
        invocation_turn_id = _string_or_none(invocation.get("turn_id"))
        if turn_id is not None and invocation_turn_id == turn_id:
            refs.append(invocation_id)
    return refs

def _codex_model_run_event_refs(
    events: list[dict[str, object]],
    turn_id: str | None,
    single_model_run: bool,
) -> list[str]:
    refs: list[str] = []
    for event in events:
        event_id = _string_or_none(event.get("event_id"))
        if event_id is None:
            continue
        if single_model_run:
            refs.append(event_id)
            continue
        event_turn_id = _event_turn_id(event)
        if turn_id is not None and event_turn_id == turn_id:
            refs.append(event_id)
    return refs

def _codex_reasoning_trace_from_raw_rollout(
    rollout: _CodexRawRollout,
) -> list[dict[str, object]]:
    reasoning_trace: list[dict[str, object]] = []
    for record in rollout.records:
        if record.record_type != "response_item":
            continue
        if _string_or_none(record.payload.get("type")) != "reasoning":
            continue
        reasoning: dict[str, object] = {
            "reasoning_id": f"reasoning-{len(reasoning_trace) + 1}",
            "visibility": _codex_reasoning_visibility(record.payload),
            "native": {
                "record_type": record.record_type,
                "payload_type": "reasoning",
                "record_index": record.record_index,
            },
        }
        if record.timestamp is not None:
            reasoning["timestamp"] = record.timestamp
        encrypted_content = _string_or_none(record.payload.get("encrypted_content"))
        if encrypted_content is not None:
            reasoning["encrypted_content"] = encrypted_content
        summary = record.payload.get("summary")
        if summary is not None:
            reasoning["summary"] = summary
        content = record.payload.get("content")
        if content is not None:
            reasoning["content"] = content
        if record.source_refs:
            reasoning["source_refs"] = record.source_refs
        reasoning_trace.append(reasoning)
    return reasoning_trace

def _codex_reasoning_visibility(payload: dict[str, Any]) -> str:
    if _string_or_none(payload.get("encrypted_content")) is not None:
        return "encrypted"
    if payload.get("content") is not None or payload.get("summary") is not None:
        return "visible"
    return "unknown"

def _codex_session_meta_payload(rollout: _CodexRawRollout) -> dict[str, Any] | None:
    for record in rollout.records:
        if record.record_type == "session_meta":
            return record.payload
    return None

def _codex_inferred_model_run_turn_ids(
    *,
    events: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
) -> list[str | None]:
    seen: set[str] = set()
    turn_ids: list[str] = []
    for event in events:
        turn_id = _event_turn_id(event)
        if turn_id is not None and turn_id not in seen:
            seen.add(turn_id)
            turn_ids.append(turn_id)
    for invocation in tool_invocations:
        turn_id = _string_or_none(invocation.get("turn_id"))
        if turn_id is not None and turn_id not in seen:
            seen.add(turn_id)
            turn_ids.append(turn_id)
    return turn_ids

def _codex_model_run_status(
    task_started: dict[str, object] | None,
    task_complete: dict[str, object] | None,
) -> str:
    if task_complete is not None:
        return "completed"
    if task_started is not None:
        return "started"
    return "unknown"

def _codex_event_data(payload: dict[str, Any]) -> dict[str, object]:
    data: dict[str, object] = {}
    for key, value in payload.items():
        if key == "type":
            continue
        if key == "duration":
            duration = _codex_duration_seconds(value)
            if duration is not None:
                data["duration"] = duration
            else:
                data[key] = value
            continue
        data[key] = value
    return data

def _codex_tool_invocations_from_raw_rollout(
    rollout: _CodexRawRollout,
) -> dict[str, object]:
    warnings: list[str] = []
    groups: dict[str, dict[str, list[_CodexRawRecord]]] = {}
    for record in rollout.records:
        group_kind = _codex_tool_group_kind(record)
        if group_kind is None:
            continue
        call_id = _string_or_none(record.payload.get("call_id"))
        if call_id is None:
            warnings.append(
                f"codex tool record {record.record_index} has no call_id"
            )
            continue
        group = groups.setdefault(
            call_id,
            {
                "function_call": [],
                "function_call_output": [],
                "exec_command_end": [],
            },
        )
        group[group_kind].append(record)

    tool_invocations: list[dict[str, object]] = []
    for call_id, group in sorted(groups.items(), key=_codex_tool_group_order):
        tool_invocation, group_warnings = _codex_tool_invocation_from_group(
            call_id=call_id,
            group=group,
            index=len(tool_invocations) + 1,
        )
        tool_invocations.append(tool_invocation)
        warnings.extend(group_warnings)

    return {
        "tool_invocations": tool_invocations,
        "warnings": warnings,
    }

def _codex_tool_group_kind(record: _CodexRawRecord) -> str | None:
    payload_type = _string_or_none(record.payload.get("type"))
    if record.record_type == "response_item":
        if payload_type == "function_call":
            return "function_call"
        if payload_type == "function_call_output":
            return "function_call_output"
    if record.record_type == "event_msg" and payload_type == "exec_command_end":
        return "exec_command_end"
    return None

def _codex_tool_group_order(
    item: tuple[str, dict[str, list[_CodexRawRecord]]],
) -> int:
    _call_id, group = item
    record_indices = [
        record.record_index
        for records in group.values()
        for record in records
    ]
    return min(record_indices) if record_indices else 0

def _codex_tool_invocation_from_group(
    *,
    call_id: str,
    group: dict[str, list[_CodexRawRecord]],
    index: int,
) -> tuple[dict[str, object], list[str]]:
    warnings: list[str] = []
    calls = group["function_call"]
    outputs = group["function_call_output"]
    exec_ends = group["exec_command_end"]
    first_call = calls[0] if calls else None
    first_output = outputs[0] if outputs else None
    first_exec_end = exec_ends[0] if exec_ends else None

    _codex_warn_about_tool_group_records(
        warnings=warnings,
        call_id=call_id,
        kind="function_call",
        records=calls,
    )
    _codex_warn_about_tool_group_records(
        warnings=warnings,
        call_id=call_id,
        kind="function_call_output",
        records=outputs,
    )
    _codex_warn_about_tool_group_records(
        warnings=warnings,
        call_id=call_id,
        kind="exec_command_end",
        records=exec_ends,
    )

    invocation: dict[str, object] = {
        "tool_invocation_id": f"tool-invocation-{index}",
        "call_id": call_id,
        "tool_name": _codex_tool_name(first_call),
        "status": _codex_tool_status(first_output, first_exec_end),
        "native": {
            "response_call_present": first_call is not None,
            "response_output_present": first_output is not None,
            "exec_end_present": first_exec_end is not None,
            "record_indices": {
                "function_call": [record.record_index for record in calls],
                "function_call_output": [
                    record.record_index for record in outputs
                ],
                "exec_command_end": [
                    record.record_index for record in exec_ends
                ],
            },
        },
    }

    started_at = _codex_tool_started_at(first_call, first_output, first_exec_end)
    if started_at is not None:
        invocation["started_at"] = started_at
    ended_at = _codex_tool_ended_at(first_output, first_exec_end)
    if ended_at is not None:
        invocation["ended_at"] = ended_at

    if first_call is not None:
        invocation["input"], input_warnings = _codex_tool_input(first_call)
        warnings.extend(input_warnings)
    if first_output is not None:
        invocation["output"] = _codex_tool_output(first_output)
    if first_exec_end is not None:
        execution = _codex_tool_execution(first_exec_end)
        if execution:
            invocation["execution"] = execution
        turn_id = _string_or_none(first_exec_end.payload.get("turn_id"))
        if turn_id is not None:
            invocation["turn_id"] = turn_id

    source_refs = _codex_tool_source_refs(calls, outputs, exec_ends)
    if source_refs:
        invocation["source_refs"] = source_refs

    return invocation, warnings

def _codex_warn_about_tool_group_records(
    *,
    warnings: list[str],
    call_id: str,
    kind: str,
    records: list[_CodexRawRecord],
) -> None:
    if not records:
        warnings.append(f"codex tool call_id {call_id} missing {kind} record")
    elif len(records) > 1:
        warnings.append(
            f"codex tool call_id {call_id} has {len(records)} {kind} records; using first"
        )

def _codex_tool_name(record: _CodexRawRecord | None) -> str:
    if record is None:
        return "unknown"
    return _string_or_none(record.payload.get("name")) or "unknown"

def _codex_tool_status(
    output_record: _CodexRawRecord | None,
    exec_end_record: _CodexRawRecord | None,
) -> str:
    if exec_end_record is not None:
        status = _string_or_none(exec_end_record.payload.get("status"))
        if status is not None:
            return status
    if output_record is not None:
        return "completed"
    return "requested"

def _codex_tool_started_at(
    call_record: _CodexRawRecord | None,
    output_record: _CodexRawRecord | None,
    exec_end_record: _CodexRawRecord | None,
) -> str | None:
    for record in (call_record, exec_end_record, output_record):
        if record is not None and record.timestamp is not None:
            return record.timestamp
    return None

def _codex_tool_ended_at(
    output_record: _CodexRawRecord | None,
    exec_end_record: _CodexRawRecord | None,
) -> str | None:
    for record in (exec_end_record, output_record):
        if record is not None and record.timestamp is not None:
            return record.timestamp
    return None

def _codex_tool_input(
    record: _CodexRawRecord,
) -> tuple[dict[str, object], list[str]]:
    warnings: list[str] = []
    payload: dict[str, object] = {}
    raw_arguments = record.payload.get("arguments")
    if isinstance(raw_arguments, str):
        try:
            payload["arguments"] = json.loads(raw_arguments)
        except json.JSONDecodeError:
            payload["arguments"] = raw_arguments
            payload["arguments_format"] = "raw_string"
            warnings.append(
                f"codex tool call_id {record.payload.get('call_id')} has invalid json arguments"
            )
    elif raw_arguments is not None:
        payload["arguments"] = raw_arguments
    return payload, warnings

def _codex_tool_output(record: _CodexRawRecord) -> dict[str, object]:
    payload: dict[str, object] = {}
    output = record.payload.get("output")
    if output is not None:
        payload["content"] = output
    return payload

def _codex_tool_execution(record: _CodexRawRecord) -> dict[str, object]:
    execution: dict[str, object] = {}
    for key in (
        "command",
        "cwd",
        "exit_code",
        "stdout",
        "stderr",
        "aggregated_output",
        "formatted_output",
        "parsed_cmd",
        "process_id",
        "source",
    ):
        value = record.payload.get(key)
        if value is not None:
            execution[key] = value
    duration = _codex_duration_seconds(record.payload.get("duration"))
    if duration is not None:
        execution["duration"] = duration
    return execution

def _codex_duration_seconds(value: object) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    if not isinstance(value, dict):
        return None
    secs = value.get("secs")
    nanos = value.get("nanos")
    if not isinstance(secs, int | float) or isinstance(secs, bool):
        secs = 0
    if not isinstance(nanos, int | float) or isinstance(nanos, bool):
        nanos = 0
    return secs + (nanos / 1_000_000_000)

def _codex_tool_source_refs(
    calls: list[_CodexRawRecord],
    outputs: list[_CodexRawRecord],
    exec_ends: list[_CodexRawRecord],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for record in [*calls, *outputs, *exec_ends]:
        refs.extend(record.source_refs)
    return _dedupe_dicts(refs)

def _codex_message_content_blocks(
    record: _CodexRawRecord,
) -> tuple[list[dict[str, object]], list[str], list[str]]:
    content_value = record.payload.get("content")
    if not isinstance(content_value, list):
        return (
            [],
            [],
            [
                f"codex message record {record.record_index} has no content array",
            ],
        )

    blocks: list[dict[str, object]] = []
    content_types: list[str] = []
    warnings: list[str] = []
    for item_index, item in enumerate(content_value, start=1):
        if not isinstance(item, dict):
            blocks.append(
                {
                    "type": "unknown",
                    "native": {
                        "value": item,
                    },
                }
            )
            warnings.append(
                f"codex message record {record.record_index} content item {item_index} is not an object"
            )
            continue

        item_type = _string_or_none(item.get("type"))
        if item_type is not None:
            content_types.append(item_type)

        if item_type in {"input_text", "output_text", "text"}:
            text = _string_or_none(item.get("text"))
            if text is None:
                warnings.append(
                    f"codex message record {record.record_index} content item {item_index} has no text"
                )
                continue
            blocks.append(
                {
                    "type": "text",
                    "text": text,
                }
            )
            continue

        blocks.append(
            {
                "type": "unknown",
                "native": item,
            }
        )
        warnings.append(
            f"codex message record {record.record_index} content item {item_index} has unsupported type {item_type or 'unknown'}"
        )

    return blocks, content_types, warnings

def _codex_message_visibility(
    role: str,
    content: list[dict[str, object]],
) -> str:
    if role in {"developer", "system"}:
        return "context"
    if role not in {"user", "assistant"}:
        return "unknown"
    if role == "assistant":
        return "conversation"

    for block in content:
        text = _string_or_none(block.get("text"))
        if text is None:
            continue
        if _codex_text_starts_with_context_prefix(text):
            return "context"
        return "conversation"
    return "unknown"

def _codex_text_starts_with_context_prefix(text: str) -> bool:
    return any(text.startswith(prefix) for prefix in _CODEX_CONTEXT_MESSAGE_PREFIXES)

def _load_codex_raw_rollout_records(
    path: Path,
    *,
    source_ref_id: str | None,
) -> _CodexRawRollout:
    records: list[_CodexRawRecord] = []
    warnings: list[str] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record_index = len(records) + 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                warnings.append(
                    f"codex raw rollout line {line_number} is invalid json: {exc.msg}"
                )
                continue
            if not isinstance(obj, dict):
                warnings.append(
                    f"codex raw rollout line {line_number} is not a json object"
                )
                continue

            payload = obj.get("payload")
            if not isinstance(payload, dict):
                payload = {}

            source_refs: list[dict[str, object]] = []
            if source_ref_id is not None:
                source_refs.append(
                    {
                        "source_ref_id": source_ref_id,
                        "record_index": record_index,
                        "line": line_number,
                    }
                )
            records.append(
                _CodexRawRecord(
                    record_index=record_index,
                    line=line_number,
                    timestamp=_string_or_none(obj.get("timestamp")),
                    record_type=_string_or_none(obj.get("type")),
                    payload=payload,
                    source_refs=source_refs,
                )
            )
    return _CodexRawRollout(
        path=path,
        source_ref_id=source_ref_id,
        records=records,
        warnings=warnings,
    )
