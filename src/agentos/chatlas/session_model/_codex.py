from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from agentos.codex.session import CodexSession
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

def _experimental_normalize_codex_session(
    session: CodexSession,
) -> _ExperimentalNormalizationResult | None:
    primary_path = session.rollout_path
    if primary_path is None:
        return None
    if not primary_path.is_file():
        return None

    try:
        if not is_codex_rollout_path(primary_path):
            return None
    except OSError:
        return None

    rollout = _load_codex_raw_rollout_records(
        primary_path,
        source_ref_id=session.source_ref_id,
    )
    tool_result = _codex_tool_invocations_from_raw_rollout(rollout)
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
    message_result = _codex_messages_from_events(events)
    messages = _dict_list(message_result["messages"])
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
                "codex raw rollout messages projected from semantic events: "
                f"{len(messages)} messages"
            )
        if tool_invocations:
            warnings.append(
                "codex raw rollout tool invocations normalized by call_id: "
                f"{len(tool_invocations)} invocations"
            )
        if events:
            warnings.append(
                "codex raw rollout semantic events normalized: "
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
        *_string_list(tool_result["warnings"]),
        *_string_list(event_result["warnings"]),
        *_string_list(message_result["warnings"]),
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

def _codex_messages_from_events(
    events: list[dict[str, object]],
) -> dict[str, object]:
    return _project_messages_from_events(
        events,
        project_event=_codex_message_from_event,
    )

def _codex_message_from_event(
    event: dict[str, object],
    index: int,
) -> tuple[dict[str, object] | None, list[str]]:
    if event.get("kind") not in {"message", "context"}:
        return None, []

    payload = _codex_event_payload(event)
    role = _string_or_none(payload.get("role"))
    if role is None:
        return None, []
    content = _dict_list(payload.get("content"))
    if not content:
        return None, []
    visibility = _string_or_none(payload.get("visibility"))
    if visibility is None:
        visibility = "context" if event.get("kind") == "context" else "conversation"

    message: dict[str, object] = {
        "message_id": f"message-{index}",
        "role": role,
        "visibility": visibility,
        "content": content,
        "native": dict(_record_native_dict(event)),
    }
    timestamp = _string_or_none(event.get("timestamp"))
    if timestamp is not None:
        message["timestamp"] = timestamp
    source_refs = _dict_list(event.get("source_refs"))
    if source_refs:
        message["source_refs"] = source_refs
    return message, []

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
        "raw_semantic_candidate_count": _codex_raw_semantic_candidate_count(rollout),
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
            "raw_count": _int_or_zero(raw_counts.get("raw_semantic_candidate_count")),
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
        if event.get("kind") != "metric":
            continue
        payload = _codex_event_payload(event)
        if not payload:
            continue
        rate_limits = payload.get("rate_limits")
        if not isinstance(rate_limits, dict):
            continue
        credits = rate_limits.get("credits")
        if credits is not None:
            return True
    return False

def _codex_event_payload(event: dict[str, object] | None) -> dict[str, object]:
    if event is None:
        return {}
    payload = event.get("payload")
    if isinstance(payload, dict):
        return payload
    data = event.get("data")
    if isinstance(data, dict):
        return data
    return {}

def _codex_raw_semantic_candidate_count(rollout: _CodexRawRollout) -> int:
    response_message_keys = _codex_response_message_keys(rollout)
    count = 0
    for record in rollout.records:
        if record.record_type in {"session_meta", "turn_context"}:
            count += 1
            continue
        payload_type = _string_or_none(record.payload.get("type"))
        if record.record_type == "response_item" and payload_type in {
            "message",
            "reasoning",
            "function_call",
            "function_call_output",
        }:
            count += 1
            continue
        if record.record_type != "event_msg":
            continue
        if payload_type in {
            "task_started",
            "task_complete",
            "token_count",
            "exec_command_end",
        }:
            count += 1
            continue
        if payload_type in {"user_message", "agent_message"}:
            if _codex_event_msg_message_key(record) not in response_message_keys:
                count += 1
    return count

def _codex_response_message_keys(
    rollout: _CodexRawRollout,
) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for record in rollout.records:
        if record.record_type != "response_item":
            continue
        if _string_or_none(record.payload.get("type")) != "message":
            continue
        role = _string_or_none(record.payload.get("role")) or "unknown"
        text = _codex_message_text(record)
        if text is not None:
            keys.add((role, text))
    return keys

def _codex_event_msg_message_key(record: _CodexRawRecord) -> tuple[str, str]:
    payload_type = _string_or_none(record.payload.get("type"))
    role = "user" if payload_type == "user_message" else "assistant"
    return role, _string_or_none(record.payload.get("message")) or ""

def _codex_message_text(record: _CodexRawRecord) -> str | None:
    content_value = record.payload.get("content")
    if not isinstance(content_value, list):
        return None
    texts: list[str] = []
    for item in content_value:
        if not isinstance(item, dict):
            continue
        text = _string_or_none(item.get("text"))
        if text is not None:
            texts.append(text)
    if not texts:
        return None
    return "".join(texts)

def _codex_call_ids_with_response_output(rollout: _CodexRawRollout) -> set[str]:
    call_ids: set[str] = set()
    for record in rollout.records:
        if record.record_type != "response_item":
            continue
        if _string_or_none(record.payload.get("type")) != "function_call_output":
            continue
        call_id = _string_or_none(record.payload.get("call_id"))
        if call_id is not None:
            call_ids.add(call_id)
    return call_ids

def _codex_events_from_raw_rollout(
    rollout: _CodexRawRollout,
    *,
    tool_invocation_refs_by_call_id: dict[str, str],
) -> dict[str, object]:
    event_builder = _SemanticEventBuilder()
    warnings: list[str] = []
    interaction_refs_by_turn_id: dict[str, str] = {}
    current_interaction_ref: str | None = None
    current_turn_id: str | None = None
    response_message_keys = _codex_response_message_keys(rollout)
    call_ids_with_response_output = _codex_call_ids_with_response_output(rollout)
    for record in rollout.records:
        semantic_type = _codex_record_semantic_type(record)
        explicit_turn_id = _codex_record_turn_id(record)
        interaction_ref = _codex_event_interaction_ref(
            payload_type=semantic_type,
            turn_id=explicit_turn_id,
            interaction_refs_by_turn_id=interaction_refs_by_turn_id,
            current_interaction_ref=current_interaction_ref,
        )
        if interaction_ref != "session":
            current_interaction_ref = interaction_ref
            if explicit_turn_id is not None:
                current_turn_id = explicit_turn_id
        event_turn_id = explicit_turn_id or (
            current_turn_id if interaction_ref != "session" else None
        )

        if record.record_type == "session_meta":
            _codex_append_session_meta_event(
                event_builder=event_builder,
                record=record,
                interaction_ref=interaction_ref,
            )
            continue

        if record.record_type == "turn_context":
            _codex_append_turn_context_event(
                event_builder=event_builder,
                record=record,
                interaction_ref=interaction_ref,
                turn_id=event_turn_id,
            )
            continue

        if record.record_type == "response_item":
            _codex_append_response_item_event(
                event_builder=event_builder,
                record=record,
                interaction_ref=interaction_ref,
                turn_id=event_turn_id,
                tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
                warnings=warnings,
            )
            continue

        if record.record_type == "event_msg":
            _codex_append_event_msg_event(
                event_builder=event_builder,
                record=record,
                interaction_ref=interaction_ref,
                turn_id=event_turn_id,
                response_message_keys=response_message_keys,
                call_ids_with_response_output=call_ids_with_response_output,
                tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
                warnings=warnings,
            )

    _codex_attach_tool_invocation_refs(
        event_builder.events,
        tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
        warnings=warnings,
    )

    return {
        "events": event_builder.events,
        "warnings": warnings,
    }

def _codex_record_semantic_type(record: _CodexRawRecord) -> str:
    if record.record_type in {"session_meta", "turn_context"}:
        return record.record_type
    payload_type = _string_or_none(record.payload.get("type"))
    if payload_type is not None:
        return payload_type
    return record.record_type or "unknown"

def _codex_record_turn_id(record: _CodexRawRecord) -> str | None:
    return _string_or_none(record.payload.get("turn_id"))

def _codex_append_session_meta_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _CodexRawRecord,
    interaction_ref: str,
) -> None:
    payload: dict[str, object] = {"update_type": "session.start"}
    _copy_present_fields(
        payload,
        record.payload,
        (
            ("id", "session_id"),
            ("originator", "originator"),
            ("source", "source"),
            ("cli_version", "cli_version"),
            ("cwd", "cwd"),
            ("model_provider", "model_provider"),
        ),
    )
    event_builder.append(
        kind="session.start",
        producer=_semantic_event_producer("provider"),
        surfaces=_semantic_event_surfaces(transcript="hidden"),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        legacy_type="codex.session_meta",
        legacy_native=_codex_record_native(record, payload_type="session_meta"),
    )

def _codex_append_turn_context_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _CodexRawRecord,
    interaction_ref: str,
    turn_id: str | None,
) -> None:
    payload = _codex_turn_context_payload(record.payload)
    event = event_builder.append(
        kind="context",
        producer=_semantic_event_producer("provider"),
        surfaces=_semantic_event_surfaces(
            transcript="hidden",
            model_input="visible",
        ),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        legacy_type="codex.turn_context",
        legacy_native=_codex_record_native(record, payload_type="turn_context"),
    )
    if turn_id is not None:
        event["turn_id"] = turn_id

def _codex_turn_context_payload(turn_context: dict[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {"context_type": "turn_context"}
    _copy_present_fields(
        payload,
        turn_context,
        (
            ("turn_id", "turn_id"),
            ("model", "model"),
            ("cwd", "cwd"),
            ("approval_policy", "approval_policy"),
            ("sandbox_policy", "sandbox_policy"),
            ("current_date", "current_date"),
            ("timezone", "timezone"),
            ("truncation_policy", "truncation_policy"),
            ("realtime_active", "realtime_active"),
        ),
    )
    effort = _string_or_none(turn_context.get("effort"))
    if effort is not None:
        payload["reasoning_effort"] = effort
    collaboration_mode = _codex_collaboration_mode(
        turn_context.get("collaboration_mode")
    )
    if collaboration_mode is not None:
        payload["collaboration_mode"] = collaboration_mode
    return payload

def _codex_append_response_item_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _CodexRawRecord,
    interaction_ref: str,
    turn_id: str | None,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> None:
    payload_type = _string_or_none(record.payload.get("type"))
    if payload_type is None:
        warnings.append(
            f"codex response_item record {record.record_index} has no payload type"
        )
        return
    if payload_type == "message":
        _codex_append_response_message_event(
            event_builder=event_builder,
            record=record,
            interaction_ref=interaction_ref,
            turn_id=turn_id,
            warnings=warnings,
        )
        return
    if payload_type == "reasoning":
        _codex_append_reasoning_event(
            event_builder=event_builder,
            record=record,
            interaction_ref=interaction_ref,
            turn_id=turn_id,
        )
        return
    if payload_type == "function_call":
        _codex_append_tool_call_event(
            event_builder=event_builder,
            record=record,
            interaction_ref=interaction_ref,
            turn_id=turn_id,
            tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
        )
        return
    if payload_type == "function_call_output":
        _codex_append_function_call_output_event(
            event_builder=event_builder,
            record=record,
            interaction_ref=interaction_ref,
            turn_id=turn_id,
            tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
        )

def _codex_append_response_message_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _CodexRawRecord,
    interaction_ref: str,
    turn_id: str | None,
    warnings: list[str],
) -> None:
    role = _string_or_none(record.payload.get("role")) or "unknown"
    if role == "unknown":
        warnings.append(f"codex message record {record.record_index} has no role")
    content, content_types, content_warnings = _codex_message_content_blocks(record)
    warnings.extend(content_warnings)
    visibility = _codex_message_visibility(role, content)
    kind = "context" if visibility == "context" else "message"
    payload: dict[str, object] = {
        "role": role,
        "visibility": visibility,
        "content": content,
    }
    phase = _string_or_none(record.payload.get("phase"))
    if phase is not None:
        payload["phase"] = phase
    event = event_builder.append(
        kind=kind,
        producer=_codex_message_event_producer(role, visibility),
        surfaces=_codex_message_event_surfaces(visibility),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        legacy_type="codex.response_item.message",
        legacy_native=_codex_message_native(
            record,
            payload_type="message",
            role=role,
            content_types=content_types,
        ),
    )
    if turn_id is not None:
        event["turn_id"] = turn_id

def _codex_append_reasoning_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _CodexRawRecord,
    interaction_ref: str,
    turn_id: str | None,
) -> None:
    payload: dict[str, object] = {
        "visibility": _codex_reasoning_visibility(record.payload),
    }
    content = _codex_reasoning_content(record.payload)
    if content is not None:
        payload["content"] = content
    summary = record.payload.get("summary")
    if summary is not None:
        payload["summary"] = summary
    event = event_builder.append(
        kind="reasoning",
        producer=_semantic_event_producer("assistant"),
        surfaces=_semantic_event_surfaces(transcript="hidden"),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        legacy_type="codex.response_item.reasoning",
        legacy_native=_codex_record_native(record, payload_type="reasoning"),
    )
    if turn_id is not None:
        event["turn_id"] = turn_id

def _codex_append_tool_call_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _CodexRawRecord,
    interaction_ref: str,
    turn_id: str | None,
    tool_invocation_refs_by_call_id: dict[str, str],
) -> None:
    call_id = _string_or_none(record.payload.get("call_id"))
    payload: dict[str, object] = {
        "tool_name": _codex_tool_name(record),
    }
    if call_id is not None:
        payload["call_id"] = call_id
    tool_input = _codex_tool_input_payload(record)
    if tool_input:
        payload["input"] = tool_input
    event = event_builder.append(
        kind="tool.call",
        producer=_semantic_event_producer("assistant"),
        surfaces=_semantic_event_surfaces(
            transcript="hidden",
            model_input="visible",
        ),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        legacy_type="codex.response_item.function_call",
        legacy_native=_codex_record_native(record, payload_type="function_call"),
        extra={
            "call_id": call_id,
            "tool_invocation_ref": (
                tool_invocation_refs_by_call_id.get(call_id)
                if call_id is not None
                else None
            ),
        },
    )
    if turn_id is not None:
        event["turn_id"] = turn_id

def _codex_append_function_call_output_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _CodexRawRecord,
    interaction_ref: str,
    turn_id: str | None,
    tool_invocation_refs_by_call_id: dict[str, str],
) -> None:
    call_id = _string_or_none(record.payload.get("call_id"))
    payload: dict[str, object] = {"result_source": "model_input"}
    if call_id is not None:
        payload["call_id"] = call_id
    output = record.payload.get("output")
    if output is not None:
        payload["content"] = output
    event = event_builder.append(
        kind="tool.result",
        producer=_semantic_event_producer("tool"),
        surfaces=_semantic_event_surfaces(
            transcript="hidden",
            model_input="visible",
        ),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        outcome="ok",
        legacy_type="codex.response_item.function_call_output",
        legacy_native=_codex_record_native(
            record,
            payload_type="function_call_output",
        ),
        extra={
            "call_id": call_id,
            "tool_invocation_ref": (
                tool_invocation_refs_by_call_id.get(call_id)
                if call_id is not None
                else None
            ),
        },
    )
    if turn_id is not None:
        event["turn_id"] = turn_id

def _codex_append_event_msg_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _CodexRawRecord,
    interaction_ref: str,
    turn_id: str | None,
    response_message_keys: set[tuple[str, str]],
    call_ids_with_response_output: set[str],
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> None:
    payload_type = _string_or_none(record.payload.get("type"))
    if payload_type is None:
        warnings.append(f"codex event record {record.record_index} has no payload type")
        return
    if payload_type in {"user_message", "agent_message"}:
        if _codex_event_msg_message_key(record) in response_message_keys:
            return
        _codex_append_event_msg_message_event(
            event_builder=event_builder,
            record=record,
            payload_type=payload_type,
            interaction_ref=interaction_ref,
            turn_id=turn_id,
        )
        return
    if payload_type == "task_started":
        _codex_append_task_event(
            event_builder=event_builder,
            record=record,
            kind="run.start",
            interaction_ref=interaction_ref,
            turn_id=turn_id,
        )
        return
    if payload_type == "task_complete":
        _codex_append_task_event(
            event_builder=event_builder,
            record=record,
            kind="run.end",
            interaction_ref=interaction_ref,
            turn_id=turn_id,
        )
        return
    if payload_type == "token_count":
        _codex_append_metric_event(
            event_builder=event_builder,
            record=record,
            interaction_ref=interaction_ref,
            turn_id=turn_id,
        )
        return
    if payload_type == "exec_command_end":
        _codex_append_exec_command_end_event(
            event_builder=event_builder,
            record=record,
            interaction_ref=interaction_ref,
            turn_id=turn_id,
            call_ids_with_response_output=call_ids_with_response_output,
            tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
        )

def _codex_append_event_msg_message_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _CodexRawRecord,
    payload_type: str,
    interaction_ref: str,
    turn_id: str | None,
) -> None:
    role = "user" if payload_type == "user_message" else "assistant"
    text = _string_or_none(record.payload.get("message"))
    content: list[dict[str, object]] = []
    if text is not None:
        content.append({"type": "text", "text": text})
    payload: dict[str, object] = {
        "role": role,
        "visibility": "conversation",
        "content": content,
    }
    phase = _string_or_none(record.payload.get("phase"))
    if phase is not None:
        payload["phase"] = phase
    event = event_builder.append(
        kind="message",
        producer=_semantic_event_producer(role),
        surfaces=_semantic_event_surfaces(
            transcript="visible",
            model_input="visible",
        ),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        legacy_type=f"codex.{payload_type}",
        legacy_native=_codex_record_native(record, payload_type=payload_type),
    )
    if turn_id is not None:
        event["turn_id"] = turn_id

def _codex_append_task_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _CodexRawRecord,
    kind: str,
    interaction_ref: str,
    turn_id: str | None,
) -> None:
    payload = _codex_event_data(record.payload)
    event = event_builder.append(
        kind=kind,
        producer=_semantic_event_producer("provider"),
        surfaces=_semantic_event_surfaces(transcript="hidden"),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        outcome="ok" if kind == "run.end" else None,
        legacy_type=f"codex.{_string_or_none(record.payload.get('type')) or 'unknown'}",
        legacy_native=_codex_record_native(
            record,
            payload_type=_string_or_none(record.payload.get("type")) or "unknown",
        ),
    )
    if turn_id is not None:
        event["turn_id"] = turn_id

def _codex_append_metric_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _CodexRawRecord,
    interaction_ref: str,
    turn_id: str | None,
) -> None:
    payload = _codex_event_data(record.payload)
    event = event_builder.append(
        kind="metric",
        producer=_semantic_event_producer("provider"),
        surfaces=_semantic_event_surfaces(transcript="hidden"),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        legacy_type="codex.token_count",
        legacy_native=_codex_record_native(record, payload_type="token_count"),
    )
    if turn_id is not None:
        event["turn_id"] = turn_id

def _codex_append_exec_command_end_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _CodexRawRecord,
    interaction_ref: str,
    turn_id: str | None,
    call_ids_with_response_output: set[str],
    tool_invocation_refs_by_call_id: dict[str, str],
) -> None:
    call_id = _string_or_none(record.payload.get("call_id"))
    payload = _codex_tool_execution(record)
    payload["result_source"] = "execution"
    if call_id is not None:
        payload["call_id"] = call_id
    has_model_output = call_id in call_ids_with_response_output if call_id else False
    event = event_builder.append(
        kind="tool.progress" if has_model_output else "tool.result",
        producer=_semantic_event_producer(
            "tool",
            name=_string_or_none(record.payload.get("source")),
        ),
        surfaces=_semantic_event_surfaces(
            transcript="hidden",
            model_input="hidden" if has_model_output else "visible",
        ),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        outcome=_codex_event_outcome(record),
        legacy_type="codex.exec_command_end",
        legacy_native=_codex_record_native(record, payload_type="exec_command_end"),
        extra={
            "call_id": call_id,
            "tool_invocation_ref": (
                tool_invocation_refs_by_call_id.get(call_id)
                if call_id is not None
                else None
            ),
        },
    )
    if turn_id is not None:
        event["turn_id"] = turn_id

def _codex_attach_tool_invocation_refs(
    events: list[dict[str, object]],
    *,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> None:
    for event in events:
        call_id = _string_or_none(event.get("call_id"))
        if call_id is None:
            continue
        tool_invocation_ref = tool_invocation_refs_by_call_id.get(call_id)
        if tool_invocation_ref is not None:
            event["tool_invocation_ref"] = tool_invocation_ref
            continue
        if event.get("kind") in {"tool.call", "tool.result", "tool.progress"}:
            warnings.append(
                f"codex tool event {event.get('event_id')} has no matching tool invocation for call_id {call_id}"
            )

def _codex_event_interaction_ref(
    *,
    payload_type: str,
    turn_id: str | None,
    interaction_refs_by_turn_id: dict[str, str],
    current_interaction_ref: str | None,
) -> str:
    if payload_type == "session_meta" or payload_type.startswith("session."):
        return "session"
    if turn_id is not None:
        interaction_ref = interaction_refs_by_turn_id.get(turn_id)
        if interaction_ref is None:
            interaction_ref = f"interaction-{len(interaction_refs_by_turn_id) + 1}"
            interaction_refs_by_turn_id[turn_id] = interaction_ref
        return interaction_ref
    if current_interaction_ref is not None:
        return current_interaction_ref
    return "interaction-1"

def _codex_event_outcome(record: _CodexRawRecord) -> str | None:
    payload_type = _string_or_none(record.payload.get("type"))
    if payload_type == "task_complete":
        return "ok"
    if payload_type != "exec_command_end":
        return None
    status_outcome = _semantic_event_outcome_from_status(
        _codex_canonical_tool_status(record)
    )
    if status_outcome is not None:
        return status_outcome
    exit_code = _int_or_none(record.payload.get("exit_code"))
    if exit_code is not None:
        return "ok" if exit_code == 0 else "error"
    return None

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
    reasoning_trace = _codex_reasoning_trace_from_events(events)
    session_meta = _codex_session_meta_payload(rollout)

    model_runs: list[dict[str, object]] = []
    if turn_context_records:
        last_record_index = rollout.records[-1].record_index if rollout.records else 0
        for index, record in enumerate(turn_context_records):
            next_record = (
                turn_context_records[index + 1]
                if index + 1 < len(turn_context_records)
                else None
            )
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
                    span_start_record_index=record.record_index,
                    span_end_record_index=(
                        next_record.record_index - 1
                        if next_record is not None
                        else last_record_index
                    ),
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

    attached_reasoning_count = sum(
        len(_dict_list(model_run.get("reasoning_trace")))
        for model_run in model_runs
    )
    if attached_reasoning_count < len(reasoning_trace):
        warnings.append(
            "codex reasoning records could not be attached to a model run: "
            f"{len(reasoning_trace) - attached_reasoning_count} records"
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
    span_start_record_index: int,
    span_end_record_index: int,
) -> dict[str, object]:
    turn_id = _string_or_none(record.payload.get("turn_id"))
    model_run = _codex_base_model_run(
        index=index,
        turn_id=turn_id,
        session_meta=session_meta,
        events=events,
        turn_context=record.payload,
    )
    native = _record_native_dict(model_run)
    native.update(
        {
            "turn_context_present": True,
            "turn_context_record_index": record.record_index,
            "span_start_record_index": span_start_record_index,
            "span_end_record_index": span_end_record_index,
        }
    )
    model_run["native"] = native
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
        span_start_record_index=span_start_record_index,
        span_end_record_index=span_end_record_index,
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
    native = _record_native_dict(model_run)
    native["turn_context_present"] = False
    model_run["native"] = native
    _codex_attach_model_run_refs(
        model_run,
        turn_id=turn_id,
        messages=messages,
        tool_invocations=tool_invocations,
        events=events,
        reasoning_trace=reasoning_trace,
        single_model_run=single_model_run,
        span_start_record_index=None,
        span_end_record_index=None,
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
        "native": {},
    }
    native = _record_native_dict(model_run)
    if turn_id is not None:
        model_run["turn_id"] = turn_id

    model_provider = _string_or_none(
        session_meta.get("model_provider") if session_meta is not None else None
    )
    if model_provider is not None:
        native["model_provider"] = model_provider

    if turn_context is not None:
        _codex_apply_turn_context_fields(model_run, native, turn_context)

    started_at = _event_timestamp(task_started) or _string_or_none(
        turn_context.get("timestamp") if turn_context is not None else None
    )
    if started_at is not None:
        model_run["started_at"] = started_at
    ended_at = _event_timestamp(task_complete)
    if ended_at is not None:
        model_run["ended_at"] = ended_at

    task_started_data = _codex_event_payload(task_started)
    model_context_window = task_started_data.get("model_context_window")
    if model_context_window is not None:
        native["model_context_window"] = model_context_window

    task_complete_data = _codex_event_payload(task_complete)
    duration_ms = task_complete_data.get("duration_ms")
    if duration_ms is not None:
        native["duration_ms"] = duration_ms

    return model_run

def _codex_apply_turn_context_fields(
    model_run: dict[str, object],
    native: dict[str, object],
    turn_context: dict[str, Any],
) -> None:
    model = _string_or_none(turn_context.get("model"))
    if model is not None:
        model_run["model"] = model
    effort = _string_or_none(turn_context.get("effort"))
    if effort is not None:
        native["reasoning_effort"] = effort
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
            native[key] = value
    collaboration_mode = _codex_collaboration_mode(turn_context.get("collaboration_mode"))
    if collaboration_mode is not None:
        native["collaboration_mode"] = collaboration_mode

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
    span_start_record_index: int | None,
    span_end_record_index: int | None,
) -> None:
    message_refs = _codex_model_run_message_refs(
        messages,
        single_model_run=single_model_run,
        span_start_record_index=span_start_record_index,
        span_end_record_index=span_end_record_index,
    )
    if message_refs:
        model_run["message_refs"] = message_refs
    tool_refs = _codex_model_run_tool_refs(
        tool_invocations,
        turn_id=turn_id,
        single_model_run=single_model_run,
        span_start_record_index=span_start_record_index,
        span_end_record_index=span_end_record_index,
    )
    if tool_refs:
        model_run["tool_invocation_refs"] = tool_refs
    event_refs = _codex_model_run_event_refs(
        events,
        turn_id=turn_id,
        single_model_run=single_model_run,
        span_start_record_index=span_start_record_index,
        span_end_record_index=span_end_record_index,
    )
    if event_refs:
        model_run["event_refs"] = event_refs
    attached_reasoning = _codex_model_run_reasoning_trace(
        reasoning_trace,
        single_model_run=single_model_run,
        span_start_record_index=span_start_record_index,
        span_end_record_index=span_end_record_index,
    )
    if attached_reasoning:
        model_run["reasoning_trace"] = attached_reasoning

def _codex_model_run_message_refs(
    messages: list[dict[str, object]],
    *,
    single_model_run: bool,
    span_start_record_index: int | None,
    span_end_record_index: int | None,
) -> list[str]:
    refs: list[str] = []
    has_span = (
        span_start_record_index is not None and span_end_record_index is not None
    )
    if not has_span and not single_model_run:
        return refs
    for message in messages:
        message_id = _string_or_none(message.get("message_id"))
        if message_id is None:
            continue
        record_index = _record_native_int_field(message, "record_index")
        if record_index is None:
            record_index = _source_ref_first_record_index(message.get("source_refs"))
        if has_span:
            if (
                record_index is not None
                and span_start_record_index <= record_index <= span_end_record_index
            ):
                refs.append(message_id)
            continue
        refs.append(message_id)
    return refs

def _codex_model_run_reasoning_trace(
    reasoning_trace: list[dict[str, object]],
    *,
    single_model_run: bool,
    span_start_record_index: int | None,
    span_end_record_index: int | None,
) -> list[dict[str, object]]:
    has_span = (
        span_start_record_index is not None and span_end_record_index is not None
    )
    if not has_span and not single_model_run:
        return []
    attached: list[dict[str, object]] = []
    for reasoning in reasoning_trace:
        record_index = _record_native_int_field(reasoning, "record_index")
        if has_span:
            if (
                record_index is not None
                and span_start_record_index <= record_index <= span_end_record_index
            ):
                attached.append(reasoning)
            continue
        attached.append(reasoning)
    return attached

def _codex_model_run_tool_refs(
    tool_invocations: list[dict[str, object]],
    *,
    turn_id: str | None,
    single_model_run: bool,
    span_start_record_index: int | None,
    span_end_record_index: int | None,
) -> list[str]:
    refs: list[str] = []
    has_span = (
        span_start_record_index is not None and span_end_record_index is not None
    )
    for invocation in tool_invocations:
        invocation_id = _string_or_none(invocation.get("tool_invocation_id"))
        if invocation_id is None:
            continue
        invocation_turn_id = _string_or_none(invocation.get("turn_id"))
        if turn_id is not None and invocation_turn_id == turn_id:
            refs.append(invocation_id)
            continue
        if has_span and any(
            span_start_record_index <= record_index <= span_end_record_index
            for record_index in _source_ref_record_indices(invocation.get("source_refs"))
        ):
            refs.append(invocation_id)
            continue
        if single_model_run and not has_span:
            refs.append(invocation_id)
    return refs

def _codex_model_run_event_refs(
    events: list[dict[str, object]],
    *,
    turn_id: str | None,
    single_model_run: bool,
    span_start_record_index: int | None,
    span_end_record_index: int | None,
) -> list[str]:
    refs: list[str] = []
    has_span = (
        span_start_record_index is not None and span_end_record_index is not None
    )
    for event in events:
        event_id = _string_or_none(event.get("event_id"))
        if event_id is None:
            continue
        event_turn_id = _event_turn_id(event)
        if turn_id is not None and event_turn_id == turn_id:
            refs.append(event_id)
            continue
        record_index = _record_native_int_field(event, "record_index")
        if has_span and record_index is not None:
            if span_start_record_index <= record_index <= span_end_record_index:
                refs.append(event_id)
            continue
        if single_model_run and not has_span:
            refs.append(event_id)
    return refs

def _codex_reasoning_trace_from_events(
    events: list[dict[str, object]],
) -> list[dict[str, object]]:
    return _project_reasoning_trace_from_events(
        events,
        id_prefix="reasoning",
    )

def _codex_reasoning_content(payload: dict[str, Any]) -> object | None:
    content = payload.get("content")
    if content is not None:
        return content
    encrypted_content = _string_or_none(payload.get("encrypted_content"))
    if encrypted_content is not None:
        return encrypted_content
    return payload.get("summary")

def _codex_reasoning_visibility(payload: dict[str, Any]) -> str:
    if payload.get("content") is not None:
        return "visible"
    if _string_or_none(payload.get("encrypted_content")) is not None:
        return "encrypted"
    if payload.get("summary") is not None:
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
        return "running"
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

    _warn_about_tool_group_records(
        warnings=warnings,
        provider_label=_CODEX_TOOL_GROUP_LABEL,
        call_id=call_id,
        kind="function_call",
        records=calls,
    )
    _warn_about_tool_group_records(
        warnings=warnings,
        provider_label=_CODEX_TOOL_GROUP_LABEL,
        call_id=call_id,
        kind="function_call_output",
        records=outputs,
    )
    _warn_about_tool_group_records(
        warnings=warnings,
        provider_label=_CODEX_TOOL_GROUP_LABEL,
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
    raw_status = _string_or_none(
        first_exec_end.payload.get("status") if first_exec_end is not None else None
    )
    if raw_status is not None:
        invocation["native"]["raw_status"] = raw_status

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

_CODEX_TOOL_GROUP_LABEL = "codex tool call_id"

def _codex_tool_name(record: _CodexRawRecord | None) -> str:
    if record is None:
        return "unknown"
    return _string_or_none(record.payload.get("name")) or "unknown"

def _codex_tool_status(
    output_record: _CodexRawRecord | None,
    exec_end_record: _CodexRawRecord | None,
) -> str:
    if exec_end_record is not None:
        status = _codex_canonical_tool_status(exec_end_record)
        if status is not None:
            return status
    if output_record is not None:
        return "completed"
    if exec_end_record is not None:
        return "unknown"
    return "requested"

def _codex_canonical_tool_status(record: _CodexRawRecord) -> str | None:
    raw_status = _string_or_none(record.payload.get("status"))
    if raw_status is not None:
        normalized_status = raw_status.strip().lower()
        if normalized_status in {"completed", "complete", "ok", "success", "succeeded"}:
            return "completed"
        if normalized_status in {
            "failed",
            "error",
            "errored",
            "cancelled",
            "canceled",
            "interrupted",
            "timeout",
            "timed_out",
        }:
            return "failed"
        if normalized_status == "requested":
            return "requested"
    exit_code = _int_or_none(record.payload.get("exit_code"))
    if exit_code is not None:
        return "completed" if exit_code == 0 else "failed"
    return None

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

def _codex_tool_input_payload(record: _CodexRawRecord) -> dict[str, object]:
    payload: dict[str, object] = {}
    raw_arguments = record.payload.get("arguments")
    if isinstance(raw_arguments, str):
        try:
            payload["arguments"] = json.loads(raw_arguments)
        except json.JSONDecodeError:
            payload["arguments"] = raw_arguments
            payload["arguments_format"] = "raw_string"
    elif raw_arguments is not None:
        payload["arguments"] = raw_arguments
    return payload

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
            block: dict[str, object] = {
                "type": "text",
                "text": text,
            }
            if item_type == "input_text":
                block["origin"] = "input"
            elif item_type == "output_text":
                block["origin"] = "output"
            blocks.append(block)
            continue

        if item_type == "image":
            blocks.append(
                {
                    "type": "image",
                    "native": item,
                }
            )
            continue

        if item_type in {"function_call", "tool_call", "tool_use"}:
            blocks.append(_codex_tool_call_content_block(item))
            continue

        if item_type in {"function_call_output", "tool_result"}:
            blocks.append(_codex_tool_result_content_block(item))
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

def _codex_record_native(
    record: _CodexRawRecord,
    *,
    payload_type: str,
) -> dict[str, object]:
    return {
        "record_type": record.record_type or "unknown",
        "payload_type": payload_type,
        "record_index": record.record_index,
    }

def _codex_message_native(
    record: _CodexRawRecord,
    *,
    payload_type: str,
    role: str,
    content_types: list[str],
) -> dict[str, object]:
    native = _codex_record_native(record, payload_type=payload_type)
    native["role"] = role
    if content_types:
        native["content_types"] = content_types
    return native

def _codex_message_event_producer(
    role: str,
    visibility: str,
) -> dict[str, object]:
    if visibility == "context" and role == "user":
        return _semantic_event_producer("provider")
    if role in {"user", "assistant", "system", "developer"}:
        return _semantic_event_producer(role)
    return _semantic_event_producer("provider")

def _codex_message_event_surfaces(visibility: str) -> dict[str, object]:
    if visibility == "conversation":
        return _semantic_event_surfaces(
            transcript="visible",
            model_input="visible",
        )
    if visibility == "context":
        return _semantic_event_surfaces(
            transcript="hidden",
            model_input="visible",
        )
    return _semantic_event_surfaces(
        transcript="hidden",
        model_input="visible",
    )

def _codex_tool_call_content_block(item: dict[str, Any]) -> dict[str, object]:
    block: dict[str, object] = {
        "type": "tool_call",
        "native": item,
    }
    call_id = _string_or_none(item.get("id")) or _string_or_none(item.get("call_id"))
    if call_id is not None:
        block["call_id"] = call_id
    tool_name = _string_or_none(item.get("name"))
    if tool_name is not None:
        block["tool_name"] = tool_name
    arguments = item.get("input")
    if arguments is None:
        arguments = item.get("arguments")
    if arguments is not None:
        block["arguments"] = arguments
    return block

def _codex_tool_result_content_block(item: dict[str, Any]) -> dict[str, object]:
    block: dict[str, object] = {
        "type": "tool_result",
        "native": item,
    }
    call_id = _string_or_none(item.get("tool_use_id")) or _string_or_none(
        item.get("call_id")
    )
    if call_id is not None:
        block["call_id"] = call_id
    content = item.get("content")
    if content is None:
        content = item.get("output")
    if content is not None:
        block["content"] = content
    is_error = item.get("is_error")
    if isinstance(is_error, bool):
        block["is_error"] = is_error
    return block

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
