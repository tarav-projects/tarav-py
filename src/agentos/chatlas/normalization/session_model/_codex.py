# $kw: ^codex-stored-event-refs --from Normalization.Pipeline::Chatlas.Session.Model --from Session.Event.Tape --note [CT] codex projections store Event.Ref objects and canonical events carry no event_id ^c20260728-16u
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from agentos.agent.providers.codex.session import CodexSession
from agentos.agent.providers.codex.extractor import is_codex_rollout_path

from agentos.chatlas._payload_helpers import (
    copy_present_fields,
    dedupe_dicts,
    dict_list,
    int_or_none,
    int_or_zero,
    string_list,
    string_or_none,
)
from agentos.chatlas.event_ref import (
    attach_event_refs_to_tool_invocations,
    attach_model_run_refs_to_events,
    event_ref,
)
from .events import (
    SemanticEventBuilder,
    event_native,
    event_timestamp,
    event_native_turn_id,
    first_event_for_turn,
    project_messages_from_events,
    project_reasoning_trace_from_events,
    semantic_event_outcome_from_status,
    semantic_event_producer,
    semantic_event_surfaces,
    set_event_native,
    tool_invocation_refs_by_call_id,
    warn_about_tool_group_kinds,
)
from .normalization import (
    NormalizationResult,
    count_payload,
    coverage_status,
    model_run_reasoning_count,
    normalized_counts,
    sorted_count_dict,
    unsupported_concepts,
)
from .source_refs import (
    record_native_dict,
    record_native_int_field,
    source_ref_first_record_index,
    source_ref_record_indices,
)
from .messages import user_content_text_marker
from ._transcript import _clean_transcript_result

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


def _normalize_codex_session(
    session: CodexSession,
) -> NormalizationResult | None:
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


    from agentos.chatlas.normalization.providers.codex_records import (
        codex_model_runs_normalizer,
        codex_tool_invocations_normalizer,
    )

    tool_result = codex_tool_invocations_normalizer(rollout)
    tool_invocations = dict_list(tool_result["tool_invocations"])
    tool_invocation_refs = tool_invocation_refs_by_call_id(
        tool_invocations,
    )
    event_result = _codex_events_from_raw_rollout(
        rollout,
        tool_invocation_refs_by_call_id=tool_invocation_refs,
    )
    events = dict_list(event_result["events"])
    attach_event_refs_to_tool_invocations(
        tool_invocations,
        events=events,
    )
    message_result = _codex_messages_from_events(events)
    messages = dict_list(message_result["messages"])
    model_run_result = codex_model_runs_normalizer(
        rollout,
        messages=messages,
        tool_invocations=tool_invocations,
        events=events,
    )
    model_runs = dict_list(model_run_result["model_runs"])
    attach_model_run_refs_to_events(
        model_runs,
        events=events,
    )
    usage = _codex_usage_from_events(events, model_runs=model_runs)
    raw_counts = _codex_raw_rollout_counts(rollout)
    residual_unsupported_concepts = _codex_residual_unsupported_concepts(
        raw_counts=raw_counts,
        events=events,
        usage=usage,
    )
    if messages or tool_invocations or events or model_runs:
        warnings = [*rollout.warnings]
        warnings.extend(string_list(message_result["warnings"]))
        warnings.extend(string_list(tool_result["warnings"]))
        warnings.extend(string_list(event_result["warnings"]))
        warnings.extend(string_list(model_run_result["warnings"]))
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
        return NormalizationResult(
            messages=messages,
            model_runs=model_runs,
            tool_invocations=tool_invocations,
            events=events,
            usage=usage,
            normalizer="codex.raw_rollout.experimental.v1",
            source_mode="codex_raw_rollout",
            warnings=warnings,
            unsupported_concepts=[
                *unsupported_concepts(
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

    fallback_artifact = {
        "role": "transcript",
        "path": str(primary_path),
    }
    fallback_source = {
        "source_ref_id": session.source_ref_id or "source-1",
        **fallback_artifact,
    }
    fallback = _clean_transcript_result(
        {
            "provider": session.provider,
            "session_id": session.session_id,
            "primary_backing_artifact": fallback_artifact,
            "backing_artifacts": [fallback_artifact],
        },
        sources=[fallback_source],
        normalizer="codex.raw_rollout.experimental.v1",
    )
    warnings = [
        *rollout.warnings,
        "codex raw rollout contained no response_item.message records; using clean transcript fallback",
        *string_list(tool_result["warnings"]),
        *string_list(event_result["warnings"]),
        *string_list(message_result["warnings"]),
        *string_list(model_run_result["warnings"]),
        *fallback.warnings,
    ]
    return NormalizationResult(
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
    return project_messages_from_events(
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
    role = string_or_none(payload.get("role"))
    if role is None:
        return None, []
    if role == "developer":

        role = "system"
    content = dict_list(payload.get("content"))
    if not content:
        return None, []
    visibility = string_or_none(payload.get("visibility"))
    if visibility is None:
        visibility = "context" if event.get("kind") == "context" else "conversation"

    producer = (
        event.get("producer")
        if isinstance(event.get("producer"), dict)
        else {"type": role}
    )
    if role == "user" and producer.get("type") == "human":
        marker = _codex_user_content_system_marker(content)
        if marker is not None:
            producer = semantic_event_producer("system", name=marker)
    message: dict[str, object] = {
        "message_id": f"message-{index}",
        "role": role,
        "producer": dict(producer),
        "visibility": visibility,
        "content": content,
        "native": dict(record_native_dict(event)),
    }
    timestamp = string_or_none(event.get("timestamp"))
    if timestamp is not None:
        message["timestamp"] = timestamp
    source_refs = dict_list(event.get("source_refs"))
    if source_refs:
        message["source_refs"] = source_refs
    return message, []


_CODEX_USER_SYSTEM_MARKERS: tuple[tuple[str, str], ...] = (
    ("<goal_context>", "goal-context"),
    ("<system-reminder>", "system-reminder"),
    ("<skill-context", "skill-context"),
    ("<environment_context>", "environment-context"),
)


def _codex_user_content_system_marker(content: list[dict[str, object]]) -> str | None:
    return user_content_text_marker(content, prefix_to_name=_CODEX_USER_SYSTEM_MARKERS)


def _codex_raw_rollout_counts(rollout: _CodexRawRollout) -> dict[str, object]:
    record_types: dict[str, int] = {}
    response_item_types: dict[str, int] = {}
    event_msg_types: dict[str, int] = {}
    for record in rollout.records:
        record_type = record.record_type or "unknown"
        record_types[record_type] = record_types.get(record_type, 0) + 1
        payload_type = string_or_none(record.payload.get("type")) or "unknown"
        if record_type == "response_item":
            response_item_types[payload_type] = (
                response_item_types.get(payload_type, 0) + 1
            )
        elif record_type == "event_msg":
            event_msg_types[payload_type] = event_msg_types.get(payload_type, 0) + 1
    return {
        "records": len(rollout.records),
        "record_types": sorted_count_dict(record_types),
        "response_item_types": sorted_count_dict(response_item_types),
        "event_msg_types": sorted_count_dict(event_msg_types),
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
        "counts": normalized_counts(
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
    response_item_types = count_payload(raw_counts.get("response_item_types"))
    event_msg_types = count_payload(raw_counts.get("event_msg_types"))
    reasoning_count = model_run_reasoning_count(model_runs)
    token_count_events = event_msg_types.get("token_count", 0)
    return {
        "messages": {
            "status": coverage_status(len(messages)),
            "raw_count": response_item_types.get("message", 0),
            "normalized_count": len(messages),
        },
        "model_runs": {
            "status": coverage_status(len(model_runs)),
            "raw_turn_context_count": count_payload(raw_counts.get("record_types")).get(
                "turn_context", 0
            ),
            "normalized_count": len(model_runs),
        },
        "tool_invocations": {
            "status": coverage_status(len(tool_invocations)),
            "raw_function_call_count": response_item_types.get("function_call", 0),
            "raw_custom_tool_call_count": response_item_types.get(
                "custom_tool_call", 0
            ),
            "raw_function_call_output_count": response_item_types.get(
                "function_call_output", 0
            ),
            "raw_exec_command_end_count": event_msg_types.get("exec_command_end", 0),
            "normalized_count": len(tool_invocations),
        },
        "events": {
            "status": coverage_status(len(events)),
            "raw_count": int_or_zero(raw_counts.get("raw_semantic_candidate_count")),
            "normalized_count": len(events),
        },
        "reasoning": {
            "status": coverage_status(reasoning_count),
            "raw_count": response_item_types.get("reasoning", 0),
            "normalized_count": reasoning_count,
        },
        "usage": {
            "status": coverage_status(len(usage))
            if token_count_events
            else "no_raw_evidence",
            "raw_token_count_event_count": token_count_events,
            "normalized_count": len(usage),
        },
        "cost": {
            "status": "event_only"
            if _codex_has_cost_like_events(events)
            else "no_raw_evidence",
            "normalized_count": 0,
        },
    }


def _codex_residual_unsupported_concepts(
    *,
    raw_counts: dict[str, object],
    events: list[dict[str, object]],
    usage: list[dict[str, object]],
) -> list[str]:
    unsupported: list[str] = []
    event_msg_types = count_payload(raw_counts.get("event_msg_types"))
    if event_msg_types.get("token_count", 0) and not usage:
        unsupported.append("usage")
    if _codex_has_cost_like_events(events):
        unsupported.append("cost")
    return unsupported


_CODEX_TOKEN_USAGE_FIELDS: tuple[tuple[str, str], ...] = (
    ("input_tokens", "input_tokens"),
    ("output_tokens", "output_tokens"),
    ("cached_input_tokens", "cache_read_tokens"),
    ("reasoning_output_tokens", "reasoning_tokens"),
)


def _codex_usage_record_from_token_usage(
    token_usage: dict[str, object],
    *,
    event: dict[str, object],
    scope: str,
    index: int,
    model_by_run: dict[str | None, object],
) -> dict[str, object]:
    record: dict[str, object] = {
        "usage_id": f"usage-{index}",
        "scope": scope,
        "provider": "codex",
    }
    model_run_ref = string_or_none(event.get("model_run_ref"))
    if scope == "model_run" and model_run_ref is not None:
        record["model_run_ref"] = model_run_ref
        model = string_or_none(model_by_run.get(model_run_ref))
        if model is not None:
            record["model"] = model
    for native_key, neutral_key in _CODEX_TOKEN_USAGE_FIELDS:
        value = int_or_none(token_usage.get(native_key))
        if value is not None:
            record[neutral_key] = value
    timestamp = string_or_none(event.get("timestamp"))
    if timestamp is not None:
        record["timestamp"] = timestamp
    source_refs = dict_list(event.get("source_refs"))
    if source_refs:
        record["source_refs"] = source_refs
    return record


def _codex_usage_from_events(
    events: list[dict[str, object]],
    *,
    model_runs: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Project usage records from token_count metric events: one model_run-scope
    record per turn's last_token_usage, plus one session-scope record from the final
    total_token_usage. The metric payload stays in place as raw evidence."""
    model_by_run: dict[str | None, object] = {
        string_or_none(run.get("model_run_id")): run.get("model") for run in model_runs
    }
    records: list[dict[str, object]] = []
    session_totals: dict[str, object] | None = None
    session_event: dict[str, object] | None = None
    for event in events:
        if event.get("kind") != "metric":
            continue
        info = (
            event.get("payload") if isinstance(event.get("payload"), dict) else {}
        ) or {}
        info = info.get("info")
        if not isinstance(info, dict):
            continue
        last_usage = info.get("last_token_usage")
        if isinstance(last_usage, dict):
            records.append(
                _codex_usage_record_from_token_usage(
                    last_usage,
                    event=event,
                    scope="model_run",
                    index=len(records) + 1,
                    model_by_run=model_by_run,
                )
            )
        totals = info.get("total_token_usage")
        if isinstance(totals, dict):
            session_totals = totals
            session_event = event
    if session_totals is not None and session_event is not None:
        records.append(
            _codex_usage_record_from_token_usage(
                session_totals,
                event=session_event,
                scope="session",
                index=len(records) + 1,
                model_by_run=model_by_run,
            )
        )
    return records


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
        raw_count = int_or_zero(detail.get("raw_count"))
        normalized_count = int_or_zero(detail.get("normalized_count"))
        if raw_count and raw_count != normalized_count:
            warnings.append(
                f"codex {concept} partial normalization: raw={raw_count} normalized={normalized_count}"
            )

    tool_detail = coverage.get("tool_invocations")
    if isinstance(tool_detail, dict):



        raw_call_count = int_or_zero(
            tool_detail.get("raw_function_call_count")
        ) + int_or_zero(tool_detail.get("raw_custom_tool_call_count"))
        normalized_count = int_or_zero(tool_detail.get("normalized_count"))
        if raw_call_count and normalized_count < raw_call_count:
            warnings.append(
                "codex tool_invocations partial normalization: "
                f"raw_calls={raw_call_count} normalized={normalized_count}"
            )

    if "usage" in residual_unsupported_concepts:
        token_count_events = int_or_zero(
            count_payload(raw_counts.get("event_msg_types")).get("token_count")
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
        payload_type = string_or_none(record.payload.get("type"))
        if record.record_type == "response_item" and payload_type in {
            "message",
            "reasoning",
            "function_call",
            "function_call_output",
            "custom_tool_call",
            "custom_tool_call_output",
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
            "thread_rolled_back",
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
        if string_or_none(record.payload.get("type")) != "message":
            continue
        role = string_or_none(record.payload.get("role")) or "unknown"
        text = _codex_message_text(record)
        if text is not None:
            keys.add((role, text))
    return keys


def _codex_event_msg_message_key(record: _CodexRawRecord) -> tuple[str, str]:
    payload_type = string_or_none(record.payload.get("type"))
    role = "user" if payload_type == "user_message" else "assistant"
    return role, string_or_none(record.payload.get("message")) or ""


def _codex_message_text(record: _CodexRawRecord) -> str | None:
    content_value = record.payload.get("content")
    if not isinstance(content_value, list):
        return None
    texts: list[str] = []
    for item in content_value:
        if not isinstance(item, dict):
            continue
        text = string_or_none(item.get("text"))
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
        if string_or_none(record.payload.get("type")) not in {
            "function_call_output",
            "custom_tool_call_output",
        }:
            continue
        call_id = string_or_none(record.payload.get("call_id"))
        if call_id is not None:
            call_ids.add(call_id)
    return call_ids


def _codex_events_from_raw_rollout(
    rollout: _CodexRawRollout,
    *,
    tool_invocation_refs_by_call_id: dict[str, str],
) -> dict[str, object]:


    from agentos.chatlas.normalization.providers.codex_events import (
        assemble_codex_events,
    )

    return assemble_codex_events(
        rollout,
        tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
    )


def _codex_record_semantic_type(record: _CodexRawRecord) -> str:
    if record.record_type in {"session_meta", "turn_context"}:
        return record.record_type
    payload_type = string_or_none(record.payload.get("type"))
    if payload_type is not None:
        return payload_type
    return record.record_type or "unknown"


def _codex_record_turn_id(record: _CodexRawRecord) -> str | None:
    return string_or_none(record.payload.get("turn_id"))


def _codex_turn_context_payload(turn_context: dict[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {"context_type": "turn_context"}
    copy_present_fields(
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
    effort = string_or_none(turn_context.get("effort"))
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
    event_builder: SemanticEventBuilder,
    record: _CodexRawRecord,
    turn_id: str,
    native_turn_id: str | None,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> None:
    payload_type = string_or_none(record.payload.get("type"))
    if payload_type is None:
        warnings.append(
            f"codex response_item record {record.record_index} has no payload type"
        )
        return
    if payload_type == "message":
        _codex_append_response_message_event(
            event_builder=event_builder,
            record=record,
            turn_id=turn_id,
            native_turn_id=native_turn_id,
            warnings=warnings,
        )
        return
    if payload_type == "reasoning":
        _codex_append_reasoning_event(
            event_builder=event_builder,
            record=record,
            turn_id=turn_id,
            native_turn_id=native_turn_id,
        )
        return
    if payload_type in {"function_call", "custom_tool_call"}:
        _codex_append_tool_call_event(
            event_builder=event_builder,
            record=record,
            turn_id=turn_id,
            native_turn_id=native_turn_id,
            tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
            payload_type=payload_type,
        )
        return
    if payload_type in {"function_call_output", "custom_tool_call_output"}:
        _codex_append_function_call_output_event(
            event_builder=event_builder,
            record=record,
            turn_id=turn_id,
            native_turn_id=native_turn_id,
            tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
            payload_type=payload_type,
        )


def _codex_append_response_message_event(
    *,
    event_builder: SemanticEventBuilder,
    record: _CodexRawRecord,
    turn_id: str,
    native_turn_id: str | None,
    warnings: list[str],
) -> None:
    role = string_or_none(record.payload.get("role")) or "unknown"
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
    phase = string_or_none(record.payload.get("phase"))
    if phase is not None:
        payload["phase"] = phase
    event = event_builder.append(
        kind=kind,
        producer=_codex_message_event_producer(role, visibility),
        surfaces=_codex_message_event_surfaces(visibility),
        turn_id=turn_id,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
    )
    set_event_native(event, "turn_id", native_turn_id)


def _codex_append_reasoning_event(
    *,
    event_builder: SemanticEventBuilder,
    record: _CodexRawRecord,
    turn_id: str,
    native_turn_id: str | None,
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
        producer=semantic_event_producer("assistant"),
        surfaces=semantic_event_surfaces(transcript="hidden"),
        turn_id=turn_id,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
    )
    set_event_native(event, "turn_id", native_turn_id)


def _codex_append_tool_call_event(
    *,
    event_builder: SemanticEventBuilder,
    record: _CodexRawRecord,
    turn_id: str,
    native_turn_id: str | None,
    tool_invocation_refs_by_call_id: dict[str, str],
    payload_type: str = "function_call",
) -> None:
    call_id = string_or_none(record.payload.get("call_id"))
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
        producer=semantic_event_producer("assistant"),
        surfaces=semantic_event_surfaces(
            transcript="hidden",
            model_input="visible",
        ),
        turn_id=turn_id,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        tool_invocation_ref=(
            tool_invocation_refs_by_call_id.get(call_id)
            if call_id is not None
            else None
        ),
        native={"call_id": call_id},
    )
    set_event_native(event, "turn_id", native_turn_id)


def _codex_append_function_call_output_event(
    *,
    event_builder: SemanticEventBuilder,
    record: _CodexRawRecord,
    turn_id: str,
    native_turn_id: str | None,
    tool_invocation_refs_by_call_id: dict[str, str],
    payload_type: str = "function_call_output",
) -> None:
    call_id = string_or_none(record.payload.get("call_id"))
    payload: dict[str, object] = {"result_source": "model_input"}
    if call_id is not None:
        payload["call_id"] = call_id
    output = record.payload.get("output")
    if output is not None:
        payload["content"] = output
    event = event_builder.append(
        kind="tool.result",
        producer=semantic_event_producer("tool"),
        surfaces=semantic_event_surfaces(
            transcript="hidden",
            model_input="visible",
        ),
        turn_id=turn_id,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        outcome="ok",
        tool_invocation_ref=(
            tool_invocation_refs_by_call_id.get(call_id)
            if call_id is not None
            else None
        ),
        native={"call_id": call_id},
    )
    set_event_native(event, "turn_id", native_turn_id)


def _codex_append_event_msg_event(
    *,
    event_builder: SemanticEventBuilder,
    record: _CodexRawRecord,
    turn_id: str,
    native_turn_id: str | None,
    response_message_keys: set[tuple[str, str]],
    call_ids_with_response_output: set[str],
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> None:
    payload_type = string_or_none(record.payload.get("type"))
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
            turn_id=turn_id,
            native_turn_id=native_turn_id,
        )
        return
    if payload_type == "task_started":
        _codex_append_task_event(
            event_builder=event_builder,
            record=record,
            kind="run.start",
            turn_id=turn_id,
            native_turn_id=native_turn_id,
        )
        return
    if payload_type == "task_complete":
        _codex_append_task_event(
            event_builder=event_builder,
            record=record,
            kind="run.end",
            turn_id=turn_id,
            native_turn_id=native_turn_id,
        )
        return
    if payload_type == "token_count":
        _codex_append_metric_event(
            event_builder=event_builder,
            record=record,
            turn_id=turn_id,
            native_turn_id=native_turn_id,
        )
        return
    if payload_type == "exec_command_end":
        _codex_append_exec_command_end_event(
            event_builder=event_builder,
            record=record,
            turn_id=turn_id,
            native_turn_id=native_turn_id,
            call_ids_with_response_output=call_ids_with_response_output,
            tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
        )
        return
    if payload_type == "thread_rolled_back":
        _codex_append_lineage_rollback_event(
            event_builder=event_builder,
            record=record,
            turn_id=turn_id,
            native_turn_id=native_turn_id,
        )


def _codex_append_event_msg_message_event(
    *,
    event_builder: SemanticEventBuilder,
    record: _CodexRawRecord,
    payload_type: str,
    turn_id: str,
    native_turn_id: str | None,
) -> None:
    role = "user" if payload_type == "user_message" else "assistant"
    text = string_or_none(record.payload.get("message"))
    content: list[dict[str, object]] = []
    if text is not None:
        content.append({"type": "text", "text": text})
    payload: dict[str, object] = {
        "role": role,
        "visibility": "conversation",
        "content": content,
    }
    phase = string_or_none(record.payload.get("phase"))
    if phase is not None:
        payload["phase"] = phase
    event = event_builder.append(
        kind="message",
        producer=_codex_message_event_producer(role, "conversation"),
        surfaces=semantic_event_surfaces(
            transcript="visible",
            model_input="visible",
        ),
        turn_id=turn_id,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
    )
    set_event_native(event, "turn_id", native_turn_id)


def _codex_append_lineage_rollback_event(
    *,
    event_builder: SemanticEventBuilder,
    record: _CodexRawRecord,
    turn_id: str,
    native_turn_id: str | None,
) -> None:


    payload = _codex_event_data(record.payload)
    payload["derived_from"] = "thread_rolled_back"
    num_turns = payload.get("num_turns")
    if isinstance(num_turns, int):
        payload["abandoned_turn_count"] = num_turns
    event = event_builder.append(
        kind="lineage.rollback",
        producer=semantic_event_producer("human"),
        surfaces=semantic_event_surfaces(transcript="hidden"),
        turn_id=turn_id,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
    )
    set_event_native(event, "turn_id", native_turn_id)


def _codex_attach_rollback_origins(events: list[dict[str, object]]) -> None:
    """Attach the provider-evidenced rollback's origin without path policy."""
    for index, event in enumerate(events):
        if event.get("kind") != "lineage.rollback":
            continue
        payload = event.get("payload")
        num_turns = payload.get("num_turns") if isinstance(payload, dict) else None
        if not isinstance(num_turns, int) or num_turns <= 0:
            continue
        turn_ids: list[str] = []
        for prior in events[:index]:
            native_turn_id = string_or_none(event_native(prior).get("turn_id"))
            if native_turn_id is not None and native_turn_id not in turn_ids:
                turn_ids.append(native_turn_id)
        abandoned_turn_ids = set(turn_ids[-num_turns:])
        origin = next(
            (
                prior
                for prior in reversed(events[:index])
                if string_or_none(event_native(prior).get("turn_id"))
                not in abandoned_turn_ids
            ),
            None,
        )
        if origin is None:
            continue
        event["lineage"] = {"origin_ref": event_ref(origin)}


def _codex_append_task_event(
    *,
    event_builder: SemanticEventBuilder,
    record: _CodexRawRecord,
    kind: str,
    turn_id: str,
    native_turn_id: str | None,
) -> None:
    payload = _codex_event_data(record.payload)
    event = event_builder.append(
        kind=kind,
        producer=semantic_event_producer("provider"),
        surfaces=semantic_event_surfaces(transcript="hidden"),
        turn_id=turn_id,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        outcome="ok" if kind == "run.end" else None,
    )
    set_event_native(event, "turn_id", native_turn_id)


def _codex_append_metric_event(
    *,
    event_builder: SemanticEventBuilder,
    record: _CodexRawRecord,
    turn_id: str,
    native_turn_id: str | None,
) -> None:
    payload = _codex_event_data(record.payload)
    event = event_builder.append(
        kind="metric",
        producer=semantic_event_producer("provider"),
        surfaces=semantic_event_surfaces(transcript="hidden"),
        turn_id=turn_id,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
    )
    set_event_native(event, "turn_id", native_turn_id)


def _codex_append_exec_command_end_event(
    *,
    event_builder: SemanticEventBuilder,
    record: _CodexRawRecord,
    turn_id: str,
    native_turn_id: str | None,
    call_ids_with_response_output: set[str],
    tool_invocation_refs_by_call_id: dict[str, str],
) -> None:
    call_id = string_or_none(record.payload.get("call_id"))
    payload = _codex_tool_execution(record)
    payload["result_source"] = "execution"
    if call_id is not None:
        payload["call_id"] = call_id
    has_model_output = call_id in call_ids_with_response_output if call_id else False
    event = event_builder.append(
        kind="tool.progress" if has_model_output else "tool.result",
        producer=semantic_event_producer(
            "tool",
            name=string_or_none(record.payload.get("source")),
        ),
        surfaces=semantic_event_surfaces(
            transcript="hidden",
            model_input="hidden" if has_model_output else "visible",
        ),
        turn_id=turn_id,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        outcome=_codex_event_outcome(record),
        tool_invocation_ref=(
            tool_invocation_refs_by_call_id.get(call_id)
            if call_id is not None
            else None
        ),
        native={"call_id": call_id},
    )
    set_event_native(event, "turn_id", native_turn_id)


def _codex_attach_tool_invocation_refs(
    events: list[dict[str, object]],
    *,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> None:
    for event in events:
        call_id = string_or_none(event_native(event).get("call_id"))
        if call_id is None:
            continue
        tool_invocation_ref = tool_invocation_refs_by_call_id.get(call_id)
        if tool_invocation_ref is not None:
            event["tool_invocation_ref"] = tool_invocation_ref
            continue
        if event.get("kind") in {"tool.call", "tool.result", "tool.progress"}:
            warnings.append(
                f"codex tool event at sequence {event.get('sequence')} has no matching tool invocation for call_id {call_id}"
            )


def _codex_opens_turn(record: _CodexRawRecord) -> bool:
    payload = record.payload
    return (
        string_or_none(payload.get("type")) == "message"
        and string_or_none(payload.get("role")) == "user"
    )


def _codex_event_turn_id(
    *,
    record: _CodexRawRecord,
    payload_type: str,
    native_turn_id: str | None,
    current_turn_id: str | None,
) -> str:
    """Codex usually hands the turn its own identity, so the model adopts it
    directly rather than numbering turns by position.

    Older rollouts carry no `turn_id`; there the identity is synthesized from
    the raw coordinate of the record that opens the turn. The raw file is
    append-only, so that coordinate is stable even though it is an index —
    unlike a normalized tape ordinal, which re-segmentation reassigns.
    """
    if payload_type == "session_meta" or payload_type.startswith("session."):
        return "session"
    if native_turn_id is not None:
        return native_turn_id
    if _codex_opens_turn(record):
        return f"turn-r{record.record_index}"
    if current_turn_id is not None:
        return current_turn_id
    return "session"


def _codex_event_outcome(record: _CodexRawRecord) -> str | None:
    payload_type = string_or_none(record.payload.get("type"))
    if payload_type == "task_complete":
        return "ok"
    if payload_type != "exec_command_end":
        return None
    status_outcome = semantic_event_outcome_from_status(
        _codex_canonical_tool_status(record)
    )
    if status_outcome is not None:
        return status_outcome
    exit_code = int_or_none(record.payload.get("exit_code"))
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
            for native_turn_id in inferred_turn_ids:
                model_runs.append(
                    _codex_inferred_model_run(
                        native_turn_id=native_turn_id,
                        index=len(model_runs) + 1,
                        session_meta=session_meta,
                        messages=messages,
                        tool_invocations=tool_invocations,
                        events=events,
                        reasoning_trace=reasoning_trace,
                        single_model_run=len(inferred_turn_ids) == 1,
                    )
                )
            warnings.append("codex model run inferred without turn_context record")

    attached_reasoning_count = sum(
        len(dict_list(model_run.get("reasoning_trace"))) for model_run in model_runs
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
    native_turn_id = string_or_none(record.payload.get("turn_id"))
    model_run = _codex_base_model_run(
        index=index,
        native_turn_id=native_turn_id,
        session_meta=session_meta,
        events=events,
        turn_context=record.payload,
    )
    native = record_native_dict(model_run)
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
        native_turn_id=native_turn_id,
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
    native_turn_id: str | None,
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
        native_turn_id=native_turn_id,
        session_meta=session_meta,
        events=events,
        turn_context=None,
    )
    native = record_native_dict(model_run)
    native["turn_context_present"] = False
    model_run["native"] = native
    _codex_attach_model_run_refs(
        model_run,
        native_turn_id=native_turn_id,
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
    native_turn_id: str | None,
    session_meta: dict[str, Any] | None,
    events: list[dict[str, object]],
    turn_context: dict[str, Any] | None,
) -> dict[str, object]:
    task_started = first_event_for_turn(
        events,
        native_turn_id=native_turn_id,
        event_type="codex.task_started",
    )
    task_complete = first_event_for_turn(
        events,
        native_turn_id=native_turn_id,
        event_type="codex.task_complete",
    )
    model_run: dict[str, object] = {
        "model_run_id": f"model-run-{index}",
        "provider": "codex",
        "status": _codex_model_run_status(task_started, task_complete),
        "native": {},
    }
    native = record_native_dict(model_run)
    if native_turn_id is not None:
        model_run["turn_id"] = native_turn_id

    model_provider = string_or_none(
        session_meta.get("model_provider") if session_meta is not None else None
    )
    if model_provider is not None:
        native["model_provider"] = model_provider

    if turn_context is not None:
        _codex_apply_turn_context_fields(model_run, native, turn_context)

    started_at = event_timestamp(task_started) or string_or_none(
        turn_context.get("timestamp") if turn_context is not None else None
    )
    if started_at is not None:
        model_run["started_at"] = started_at
    ended_at = event_timestamp(task_complete)
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
    model = string_or_none(turn_context.get("model"))
    if model is not None:
        model_run["model"] = model
    effort = string_or_none(turn_context.get("effort"))
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
    collaboration_mode = _codex_collaboration_mode(
        turn_context.get("collaboration_mode")
    )
    if collaboration_mode is not None:
        native["collaboration_mode"] = collaboration_mode


def _codex_collaboration_mode(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    mode = string_or_none(value.get("mode"))
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
    native_turn_id: str | None,
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
        native_turn_id=native_turn_id,
        single_model_run=single_model_run,
        span_start_record_index=span_start_record_index,
        span_end_record_index=span_end_record_index,
    )
    if tool_refs:
        model_run["tool_invocation_refs"] = tool_refs
    event_refs = _codex_model_run_event_refs(
        events,
        native_turn_id=native_turn_id,
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
    has_span = span_start_record_index is not None and span_end_record_index is not None
    if not has_span and not single_model_run:
        return refs
    for message in messages:
        message_id = string_or_none(message.get("message_id"))
        if message_id is None:
            continue
        record_index = record_native_int_field(message, "record_index")
        if record_index is None:
            record_index = source_ref_first_record_index(message.get("source_refs"))
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
    has_span = span_start_record_index is not None and span_end_record_index is not None
    if not has_span and not single_model_run:
        return []
    attached: list[dict[str, object]] = []
    for reasoning in reasoning_trace:
        record_index = record_native_int_field(reasoning, "record_index")
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
    native_turn_id: str | None,
    single_model_run: bool,
    span_start_record_index: int | None,
    span_end_record_index: int | None,
) -> list[str]:
    refs: list[str] = []
    has_span = span_start_record_index is not None and span_end_record_index is not None
    for invocation in tool_invocations:
        invocation_id = string_or_none(invocation.get("tool_invocation_id"))
        if invocation_id is None:
            continue
        invocation_native = invocation.get("native")
        invocation_turn_id = string_or_none(
            invocation_native.get("turn_id")
            if isinstance(invocation_native, dict)
            else None
        )
        if native_turn_id is not None and invocation_turn_id == native_turn_id:
            refs.append(invocation_id)
            continue
        if has_span and any(
            span_start_record_index <= record_index <= span_end_record_index
            for record_index in source_ref_record_indices(invocation.get("source_refs"))
        ):
            refs.append(invocation_id)
            continue
        if single_model_run and not has_span:
            refs.append(invocation_id)
    return refs


def _codex_model_run_event_refs(
    events: list[dict[str, object]],
    *,
    native_turn_id: str | None,
    single_model_run: bool,
    span_start_record_index: int | None,
    span_end_record_index: int | None,
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    has_span = span_start_record_index is not None and span_end_record_index is not None
    for event in events:
        if int_or_none(event.get("sequence")) is None:
            continue
        current_event_turn_id = event_native_turn_id(event)
        if native_turn_id is not None and current_event_turn_id == native_turn_id:
            refs.append(event_ref(event))
            continue
        record_index = record_native_int_field(event, "record_index")
        if has_span and record_index is not None:
            if span_start_record_index <= record_index <= span_end_record_index:
                refs.append(event_ref(event))
            continue
        if single_model_run and not has_span:
            refs.append(event_ref(event))
    return refs


def _codex_reasoning_trace_from_events(
    events: list[dict[str, object]],
) -> list[dict[str, object]]:
    return project_reasoning_trace_from_events(
        events,
        id_prefix="reasoning",
    )


def _codex_reasoning_content(payload: dict[str, Any]) -> object | None:
    content = payload.get("content")
    if content is not None:
        return content
    encrypted_content = string_or_none(payload.get("encrypted_content"))
    if encrypted_content is not None:
        return encrypted_content
    return payload.get("summary")


def _codex_reasoning_visibility(payload: dict[str, Any]) -> str:
    if payload.get("content") is not None:
        return "visible"
    if string_or_none(payload.get("encrypted_content")) is not None:
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
        native_turn_id = event_native_turn_id(event)
        if native_turn_id is not None and native_turn_id not in seen:
            seen.add(native_turn_id)
            turn_ids.append(native_turn_id)
    for invocation in tool_invocations:
        invocation_native = invocation.get("native")
        native_turn_id = string_or_none(
            invocation_native.get("turn_id")
            if isinstance(invocation_native, dict)
            else None
        )
        if native_turn_id is not None and native_turn_id not in seen:
            seen.add(native_turn_id)
            turn_ids.append(native_turn_id)
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
        call_id = string_or_none(record.payload.get("call_id"))
        if call_id is None:
            warnings.append(f"codex tool record {record.record_index} has no call_id")
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
    payload_type = string_or_none(record.payload.get("type"))
    if record.record_type == "response_item":
        if payload_type in {"function_call", "custom_tool_call"}:
            return "function_call"
        if payload_type in {"function_call_output", "custom_tool_call_output"}:
            return "function_call_output"
    if record.record_type == "event_msg" and payload_type == "exec_command_end":
        return "exec_command_end"
    return None


def _codex_tool_group_order(
    item: tuple[str, dict[str, list[_CodexRawRecord]]],
) -> int:
    _call_id, group = item
    record_indices = [
        record.record_index for records in group.values() for record in records
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

    warn_about_tool_group_kinds(
        warnings=warnings,
        provider_label=_CODEX_TOOL_GROUP_LABEL,
        call_id=call_id,
        kinds=[
            ("function_call", calls),
            ("function_call_output", outputs),
            ("exec_command_end", exec_ends),
        ],


        supplementary=frozenset({"exec_command_end"}),
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
                "function_call_output": [record.record_index for record in outputs],
                "exec_command_end": [record.record_index for record in exec_ends],
            },
        },
    }
    raw_status = string_or_none(
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
        native_turn_id = string_or_none(first_exec_end.payload.get("turn_id"))
        if native_turn_id is not None:
            invocation.setdefault("native", {})["turn_id"] = native_turn_id

    source_refs = _codex_tool_source_refs(calls, outputs, exec_ends)
    if source_refs:
        invocation["source_refs"] = source_refs

    return invocation, warnings


_CODEX_TOOL_GROUP_LABEL = "codex tool call_id"


def _codex_tool_name(record: _CodexRawRecord | None) -> str:
    if record is None:
        return "unknown"
    return string_or_none(record.payload.get("name")) or "unknown"


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
    raw_status = string_or_none(record.payload.get("status"))
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
    exit_code = int_or_none(record.payload.get("exit_code"))
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
    arguments_are_custom_input = raw_arguments is None
    if raw_arguments is None:
        raw_arguments = record.payload.get("input")
    if isinstance(raw_arguments, str):
        try:
            payload["arguments"] = json.loads(raw_arguments)
        except json.JSONDecodeError:
            payload["arguments"] = raw_arguments
            payload["arguments_format"] = "raw_string"
            if not arguments_are_custom_input:
                warnings.append(
                    f"codex tool call_id {record.payload.get('call_id')} has invalid json arguments"
                )
    elif raw_arguments is not None:
        payload["arguments"] = raw_arguments
    return payload, warnings


def _codex_tool_input_payload(record: _CodexRawRecord) -> dict[str, object]:
    payload: dict[str, object] = {}
    raw_arguments = record.payload.get("arguments")
    if raw_arguments is None:
        raw_arguments = record.payload.get("input")
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
    return dedupe_dicts(refs)


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

        item_type = string_or_none(item.get("type"))
        if item_type is not None:
            content_types.append(item_type)

        if item_type in {"input_text", "output_text", "text"}:
            text = string_or_none(item.get("text"))
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
    if role == "user":
        if visibility == "conversation":
            return semantic_event_producer("human")
        return semantic_event_producer("system")
    if role == "assistant":
        return semantic_event_producer("assistant")
    if role in {"system", "developer"}:
        return semantic_event_producer("system")
    return semantic_event_producer("provider")


def _codex_message_event_surfaces(visibility: str) -> dict[str, object]:
    if visibility == "conversation":
        return semantic_event_surfaces(
            transcript="visible",
            model_input="visible",
        )
    if visibility == "context":
        return semantic_event_surfaces(
            transcript="hidden",
            model_input="visible",
        )
    return semantic_event_surfaces(
        transcript="hidden",
        model_input="visible",
    )


def _codex_tool_call_content_block(item: dict[str, Any]) -> dict[str, object]:
    block: dict[str, object] = {
        "type": "tool_call",
        "native": item,
    }
    call_id = string_or_none(item.get("id")) or string_or_none(item.get("call_id"))
    if call_id is not None:
        block["call_id"] = call_id
    tool_name = string_or_none(item.get("name"))
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
    call_id = string_or_none(item.get("tool_use_id")) or string_or_none(
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
        text = string_or_none(block.get("text"))
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
                    timestamp=string_or_none(obj.get("timestamp")),
                    record_type=string_or_none(obj.get("type")),
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
