from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from agentos.chat.extractors.claude_code import is_claude_code_session_path

from ._shared import *

@dataclass(frozen=True)
class _ClaudeRawRecord:
    record_index: int
    line: int
    uuid: str | None
    parent_uuid: str | None
    timestamp: str | None
    record_type: str | None
    message: dict[str, Any]
    data: dict[str, Any]
    tool_use_result: dict[str, Any]
    payload: dict[str, Any]
    source_refs: list[dict[str, object]]

@dataclass(frozen=True)
class _ClaudeRawSession:
    path: Path
    source_ref_id: str | None
    records: list[_ClaudeRawRecord]
    warnings: list[str]

@dataclass(frozen=True)
class _ClaudeToolRequestRecord:
    raw_record: _ClaudeRawRecord
    content_index: int
    call_id: str
    payload: dict[str, Any]
    source_refs: list[dict[str, object]]

@dataclass(frozen=True)
class _ClaudeToolResultRecord:
    raw_record: _ClaudeRawRecord
    content_index: int
    call_id: str
    payload: dict[str, Any]
    tool_use_result: dict[str, Any]
    source_refs: list[dict[str, object]]

def _experimental_normalize_claude_code_raw_session(
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
        if not is_claude_code_session_path(primary_path):
            return None
    except OSError:
        return None

    source_ref_id = _source_ref_id_for_artifact(primary_artifact, sources=sources)
    raw_session = _load_claude_raw_session_records(
        primary_path,
        source_ref_id=source_ref_id,
    )
    raw_counts = _claude_raw_record_counts(raw_session)
    tool_result = _claude_tool_invocations_from_raw_session(raw_session)
    tool_invocations = _dict_list(tool_result["tool_invocations"])
    tool_invocation_refs_by_call_id = _tool_invocation_refs_by_call_id(
        tool_invocations,
    )
    event_result = _claude_events_from_raw_session(
        raw_session,
        tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
    )
    events = _dict_list(
        event_result["events"]
    )
    _attach_event_refs_to_tool_invocations(
        tool_invocations,
        events=events,
    )
    message_result = _claude_messages_from_events(events)
    messages = _dict_list(message_result["messages"])
    model_run_result = _claude_model_runs_from_raw_session(
        raw_session,
        messages=messages,
        tool_invocations=tool_invocations,
        events=events,
    )
    model_runs = _dict_list(model_run_result["model_runs"])
    _claude_attach_model_run_refs_to_events(
        model_runs,
        events=events,
    )
    usage_result = _claude_usage_from_events(events)
    usage = _dict_list(usage_result["usage"])
    deferred_concepts: list[str] = []

    warnings = [
        *raw_session.warnings,
        (
            "claude raw session parsed for future normalization: "
            f"{len(raw_session.records)} records"
        ),
    ]
    last_prompt_count = _claude_last_prompt_record_count(raw_counts)
    if last_prompt_count:
        warnings.append(
            "claude raw session excludes last-prompt artifact residue from canonical events: "
            f"{last_prompt_count} records"
        )
    if messages:
        warnings.append(
            "claude raw session messages projected from canonical events: "
            f"{len(messages)} messages"
        )
    if tool_invocations:
        warnings.append(
            "claude raw session tool invocations normalized by tool_use.id: "
            f"{len(tool_invocations)} invocations"
        )
    if model_runs:
        warnings.append(
            "claude raw session model runs normalized by requestId: "
            f"{len(model_runs)} runs"
        )
    reasoning_count = _model_run_reasoning_count(model_runs)
    if reasoning_count:
        warnings.append(
            "claude raw session reasoning normalized from thinking blocks: "
            f"{reasoning_count} entries"
        )
    if usage:
        warnings.append(
            "claude raw session usage projected from canonical usage events: "
            f"{len(usage)} records"
        )
    if events:
        warnings.append(
            "claude raw session semantic events normalized from raw records: "
            f"{len(events)} events"
        )
    warnings.extend(_string_list(message_result["warnings"]))
    warnings.extend(_string_list(tool_result["warnings"]))
    warnings.extend(_string_list(event_result["warnings"]))
    warnings.extend(_string_list(model_run_result["warnings"]))
    warnings.extend(_string_list(usage_result["warnings"]))
    warnings.extend(
        _claude_reasoning_attachment_warnings(
            raw_counts=raw_counts,
            model_runs=model_runs,
        )
    )
    warnings.extend(
        _claude_usage_attachment_warnings(
            raw_counts=raw_counts,
            usage=usage,
        )
    )
    warnings.append(
        "claude raw session normalization covers messages, events, tool invocations, model runs, reasoning, and usage"
    )

    return _ExperimentalNormalizationResult(
        messages=messages,
        model_runs=model_runs,
        tool_invocations=tool_invocations,
        events=events,
        usage=usage,
        normalizer="claude-code.raw_session.experimental.v1",
        source_mode="claude_code_raw_session",
        warnings=warnings,
        unsupported_concepts=_claude_unsupported_concepts(
            raw_counts=raw_counts,
            messages=messages,
            model_runs=model_runs,
            tool_invocations=tool_invocations,
            events=events,
            usage=usage,
        ),
        metadata=_claude_normalization_metadata(
            raw_counts=raw_counts,
            messages=messages,
            model_runs=model_runs,
            tool_invocations=tool_invocations,
            events=events,
            usage=usage,
            deferred_concepts=deferred_concepts,
        ),
    )

def _claude_raw_record_counts(raw_session: _ClaudeRawSession) -> dict[str, object]:
    record_types: dict[str, int] = {}
    visible_message_record_count = 0
    tool_use_count = 0
    tool_result_count = 0
    progress_count = 0
    reasoning_evidence_count = 0
    request_ids: set[str] = set()
    usage_evidence_count = 0

    for record in raw_session.records:
        record_kind = _claude_record_kind(record)
        record_types[record_kind] = record_types.get(record_kind, 0) + 1
        if record_kind == "progress":
            progress_count += 1
        if _claude_record_has_visible_message(record):
            visible_message_record_count += 1
        tool_use_count += _claude_record_content_item_count(record, item_type="tool_use")
        tool_result_count += _claude_record_content_item_count(
            record,
            item_type="tool_result",
        )
        reasoning_evidence_count += _claude_record_content_item_count(
            record,
            item_type="thinking",
        )
        request_id = _claude_record_request_id(record)
        if request_id is not None:
            request_ids.add(request_id)
        if _claude_record_has_usage_payload(record):
            usage_evidence_count += 1

    return {
        "records": len(raw_session.records),
        "record_types": _sorted_count_dict(record_types),
        "parse_warning_count": len(raw_session.warnings),
        "visible_message_record_count": visible_message_record_count,
        "tool_use_count": tool_use_count,
        "tool_result_count": tool_result_count,
        "progress_count": progress_count,
        "reasoning_evidence_count": reasoning_evidence_count,
        "usage_evidence_count": usage_evidence_count,
        "distinct_request_count": len(request_ids),
    }

def _claude_events_from_raw_session(
    raw_session: _ClaudeRawSession,
    *,
    tool_invocation_refs_by_call_id: dict[str, str] | None = None,
) -> dict[str, object]:
    event_builder = _SemanticEventBuilder()
    warnings: list[str] = []
    current_interaction_ref: str | None = None
    interaction_count = 0

    for record in raw_session.records:
        if _claude_record_kind(record) == "last-prompt":
            continue

        if _claude_record_starts_interaction(record):
            interaction_count += 1
            current_interaction_ref = f"interaction-{interaction_count}"
        interaction_ref = current_interaction_ref or "session"
        _claude_append_record_semantic_events(
            event_builder=event_builder,
            record=record,
            interaction_ref=interaction_ref,
            tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id or {},
            warnings=warnings,
        )

    return {
        "events": event_builder.events,
        "warnings": warnings,
    }

def _claude_append_record_semantic_events(
    *,
    event_builder: _SemanticEventBuilder,
    record: _ClaudeRawRecord,
    interaction_ref: str,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> None:
    if record.record_type == "progress":
        _claude_append_progress_event(
            event_builder=event_builder,
            record=record,
            interaction_ref=interaction_ref,
            tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
            warnings=warnings,
        )
        return

    if record.record_type == "system":
        _claude_append_system_event(
            event_builder=event_builder,
            record=record,
            interaction_ref=interaction_ref,
        )
        return

    role = _claude_message_role(record)
    if role in {"user", "assistant"}:
        _claude_append_message_record_events(
            event_builder=event_builder,
            record=record,
            interaction_ref=interaction_ref,
            tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
            warnings=warnings,
        )
        if _claude_record_has_usage_payload(record):
            _claude_append_usage_event(
                event_builder=event_builder,
                record=record,
                interaction_ref=interaction_ref,
            )
        return

    _claude_append_session_update_event(
        event_builder=event_builder,
        record=record,
        interaction_ref=interaction_ref,
    )

def _claude_append_message_record_events(
    *,
    event_builder: _SemanticEventBuilder,
    record: _ClaudeRawRecord,
    interaction_ref: str,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> None:
    role = _claude_message_role(record)
    if role not in {"user", "assistant"}:
        return

    content = record.message.get("content")
    if isinstance(content, str):
        text = _string_or_none(content)
        if text is not None:
            _claude_append_message_event(
                event_builder=event_builder,
                record=record,
                interaction_ref=interaction_ref,
                role=role,
                content=[{"type": "text", "text": text}],
                content_types=["string"],
            )
        return
    if not isinstance(content, list):
        return

    visible_blocks: list[dict[str, object]] = []
    visible_content_types: list[str] = []

    def flush_visible_blocks() -> None:
        nonlocal visible_blocks, visible_content_types
        if not visible_blocks:
            return
        _claude_append_message_event(
            event_builder=event_builder,
            record=record,
            interaction_ref=interaction_ref,
            role=role,
            content=visible_blocks,
            content_types=visible_content_types,
        )
        visible_blocks = []
        visible_content_types = []

    for content_index, item in enumerate(content, start=1):
        if not isinstance(item, dict):
            visible_blocks.append(
                {
                    "type": "unknown",
                    "native": {"value": item},
                }
            )
            visible_content_types.append("unknown")
            warnings.append(
                f"claude {role} message record {record.record_index} content item {content_index} is not an object"
            )
            continue

        item_type = _string_or_none(item.get("type"))
        if item_type == "text":
            text = _string_or_none(item.get("text"))
            if text is None:
                warnings.append(
                    f"claude {role} message record {record.record_index} content item {content_index} has no text"
                )
                continue
            visible_blocks.append({"type": "text", "text": text})
            visible_content_types.append("text")
            continue

        if item_type == "image":
            visible_blocks.append({"type": "image", "native": item})
            visible_content_types.append("image")
            continue

        if item_type == "thinking":
            flush_visible_blocks()
            _claude_append_reasoning_event(
                event_builder=event_builder,
                record=record,
                content_index=content_index,
                item=item,
                interaction_ref=interaction_ref,
            )
            continue

        if item_type == "tool_use":
            flush_visible_blocks()
            _claude_append_tool_call_event(
                event_builder=event_builder,
                record=record,
                content_index=content_index,
                item=item,
                interaction_ref=interaction_ref,
                tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
                warnings=warnings,
            )
            continue

        if item_type == "tool_result":
            flush_visible_blocks()
            _claude_append_tool_result_event(
                event_builder=event_builder,
                record=record,
                content_index=content_index,
                item=item,
                interaction_ref=interaction_ref,
                tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
                warnings=warnings,
            )
            continue

        visible_blocks.append({"type": "unknown", "native": item})
        visible_content_types.append(item_type or "unknown")

    flush_visible_blocks()

def _claude_append_message_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _ClaudeRawRecord,
    interaction_ref: str,
    role: str,
    content: list[dict[str, object]],
    content_types: list[str],
) -> None:
    event_builder.append(
        kind="message",
        producer=_semantic_event_producer(role),
        surfaces=_semantic_event_surfaces(
            transcript="visible",
            model_input="visible",
        ),
        interaction_ref=interaction_ref,
        payload={
            "role": role,
            "content": content,
        },
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        legacy_type=_claude_event_type(record),
        legacy_native=_claude_message_native(
            record,
            content_types=content_types,
        ),
        extra=_claude_common_event_extra(record),
    )

def _claude_append_reasoning_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _ClaudeRawRecord,
    content_index: int,
    item: dict[str, Any],
    interaction_ref: str,
) -> None:
    text = _string_or_none(item.get("thinking"))
    if text is None:
        return
    payload: dict[str, object] = {
        "visibility": "visible",
        "content": text,
    }
    signature = _string_or_none(item.get("signature"))
    if signature is not None:
        payload["signature"] = signature
    event_builder.append(
        kind="reasoning",
        producer=_semantic_event_producer("assistant"),
        surfaces=_semantic_event_surfaces(transcript="hidden"),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=_claude_item_source_refs(
            record,
            content_index=content_index,
        ),
        legacy_type="claude-code.reasoning",
        legacy_native=_claude_reasoning_native(
            record,
            content_index=content_index,
            item=item,
        ),
        extra={
            **_claude_common_event_extra(record),
            "content_index": content_index,
        },
    )

def _claude_append_tool_call_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _ClaudeRawRecord,
    content_index: int,
    item: dict[str, Any],
    interaction_ref: str,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> None:
    call_id = _string_or_none(item.get("id"))
    if call_id is None:
        warnings.append(
            f"claude assistant tool-use record {record.record_index} content item {content_index} has no id"
        )
        return

    payload: dict[str, object] = {"call_id": call_id}
    tool_name = _string_or_none(item.get("name"))
    if tool_name is not None:
        payload["tool_name"] = tool_name
    arguments = item.get("input")
    if arguments is not None:
        payload["input"] = {"arguments": arguments}

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
        source_refs=_claude_item_source_refs(
            record,
            content_index=content_index,
        ),
        legacy_type="claude-code.tool.call",
        legacy_native=_claude_content_event_native(
            record,
            content_index=content_index,
            content_type="tool_use",
        ),
        extra={
            **_claude_common_event_extra(record),
            "call_id": call_id,
            "content_index": content_index,
        },
    )
    _claude_attach_tool_invocation_ref_to_event(
        event,
        record=record,
        call_id=call_id,
        tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
        warnings=warnings,
    )

def _claude_append_tool_result_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _ClaudeRawRecord,
    content_index: int,
    item: dict[str, Any],
    interaction_ref: str,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> None:
    call_id = _string_or_none(item.get("tool_use_id"))
    if call_id is None:
        warnings.append(
            f"claude user tool-result record {record.record_index} content item {content_index} has no tool_use_id"
        )
        return

    payload: dict[str, object] = {"call_id": call_id}
    content = item.get("content")
    if content is not None:
        payload["content"] = content
    is_error = item.get("is_error")
    if isinstance(is_error, bool):
        payload["is_error"] = is_error
    execution = _claude_tool_execution_from_tool_use_result(record.tool_use_result)
    if execution:
        payload["execution"] = execution

    event = event_builder.append(
        kind="tool.result",
        producer=_semantic_event_producer(
            "tool",
            name=_claude_record_tool_name(record),
        ),
        surfaces=_semantic_event_surfaces(
            transcript="hidden",
            model_input="visible",
        ),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=_claude_item_source_refs(
            record,
            content_index=content_index,
        ),
        outcome=_claude_tool_result_outcome(
            item=item,
            tool_use_result=record.tool_use_result,
        ),
        legacy_type="claude-code.tool.result",
        legacy_native=_claude_content_event_native(
            record,
            content_index=content_index,
            content_type="tool_result",
        ),
        extra={
            **_claude_common_event_extra(record),
            "call_id": call_id,
            "content_index": content_index,
        },
    )
    _claude_attach_tool_invocation_ref_to_event(
        event,
        record=record,
        call_id=call_id,
        tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
        warnings=warnings,
    )

def _claude_append_progress_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _ClaudeRawRecord,
    interaction_ref: str,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> None:
    call_id = _claude_record_call_id(record)
    payload = _claude_progress_event_payload(record)
    if call_id is not None:
        payload["call_id"] = call_id
    event = event_builder.append(
        kind="tool.progress",
        producer=_semantic_event_producer(
            "system",
            name=_string_or_none(record.data.get("hookName")),
        ),
        surfaces=_semantic_event_surfaces(transcript="hidden"),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        legacy_type="claude-code.tool.progress",
        legacy_native=_claude_content_event_native(
            record,
            content_type="progress",
        ),
        extra={
            **_claude_common_event_extra(record),
            "call_id": call_id,
        },
    )
    if call_id is not None:
        _claude_attach_tool_invocation_ref_to_event(
            event,
            record=record,
            call_id=call_id,
            tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
            warnings=warnings,
        )

def _claude_append_usage_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _ClaudeRawRecord,
    interaction_ref: str,
) -> None:
    usage_payload = record.message.get("usage")
    if not isinstance(usage_payload, dict):
        return
    event_builder.append(
        kind="usage",
        producer=_semantic_event_producer("provider"),
        surfaces=_semantic_event_surfaces(transcript="hidden"),
        interaction_ref=interaction_ref,
        payload=_claude_usage_event_payload(
            record,
            usage_payload=usage_payload,
        ),
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        legacy_type="claude-code.usage",
        legacy_native=_claude_usage_native(
            record,
            request_id=_claude_record_request_id(record),
            usage_payload=usage_payload,
        ),
        extra=_claude_common_event_extra(record),
    )

def _claude_append_system_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _ClaudeRawRecord,
    interaction_ref: str,
) -> None:
    subtype = _string_or_none(record.payload.get("subtype"))
    kind = "metric" if subtype == "turn_duration" else "session.update"
    event_builder.append(
        kind=kind,
        producer=_semantic_event_producer("provider"),
        surfaces=_semantic_event_surfaces(transcript="hidden"),
        interaction_ref=interaction_ref,
        payload=_claude_system_event_payload(record),
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        legacy_type=_claude_event_type(record),
        legacy_native=_claude_content_event_native(record),
        extra=_claude_common_event_extra(record),
    )

def _claude_append_session_update_event(
    *,
    event_builder: _SemanticEventBuilder,
    record: _ClaudeRawRecord,
    interaction_ref: str,
) -> None:
    event_builder.append(
        kind="session.update",
        producer=_semantic_event_producer("provider"),
        surfaces=_semantic_event_surfaces(transcript="hidden"),
        interaction_ref=interaction_ref,
        payload=_claude_session_update_payload(record),
        timestamp=record.timestamp,
        source_refs=record.source_refs,
        legacy_type=_claude_event_type(record),
        legacy_native=_claude_content_event_native(record),
        extra=_claude_common_event_extra(record),
    )

def _claude_attach_tool_invocation_ref_to_event(
    event: dict[str, object],
    *,
    record: _ClaudeRawRecord,
    call_id: str,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> None:
    tool_invocation_ref = tool_invocation_refs_by_call_id.get(call_id)
    if tool_invocation_ref is not None:
        event["tool_invocation_ref"] = tool_invocation_ref
        return
    warnings.append(
        "claude tool-related event "
        f"{record.record_index} has no matching tool invocation for tool_use id {call_id}"
    )

def _claude_progress_event_payload(record: _ClaudeRawRecord) -> dict[str, object]:
    payload: dict[str, object] = {}
    _copy_present_fields(
        payload,
        record.data,
        (
            ("type", "progress_type"),
            ("hookEvent", "hook_event"),
            ("hookName", "hook_name"),
            ("command", "command"),
        ),
    )
    return payload

def _claude_system_event_payload(record: _ClaudeRawRecord) -> dict[str, object]:
    payload: dict[str, object] = {}
    _copy_present_fields(
        payload,
        record.payload,
        (
            ("subtype", "subtype"),
            ("durationMs", "duration_ms"),
            ("isMeta", "is_meta"),
        ),
    )
    return payload

def _claude_session_update_payload(record: _ClaudeRawRecord) -> dict[str, object]:
    payload: dict[str, object] = {}
    record_kind = _claude_record_kind(record)
    if record_kind != "unknown":
        payload["record_kind"] = record_kind
    return payload

def _claude_tool_result_outcome(
    *,
    item: dict[str, Any],
    tool_use_result: dict[str, Any],
) -> str:
    if item.get("is_error") is True:
        return "error"
    if tool_use_result.get("interrupted") is True:
        return "interrupted"
    return "ok"

def _claude_tool_execution_from_tool_use_result(
    tool_use_result: dict[str, Any],
) -> dict[str, object]:
    execution: dict[str, object] = {}
    _copy_present_fields(
        execution,
        tool_use_result,
        (
            ("stdout", "stdout"),
            ("stderr", "stderr"),
            ("interrupted", "interrupted"),
            ("isImage", "is_image"),
            ("noOutputExpected", "no_output_expected"),
        ),
    )
    return execution

def _claude_usage_event_payload(
    record: _ClaudeRawRecord,
    *,
    usage_payload: dict[str, Any],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "scope": "model_run",
        "provider": "claude-code",
        "request_count": 1,
    }
    request_id = _claude_record_request_id(record)
    if request_id is not None:
        payload["request_id"] = request_id
    model = _string_or_none(record.message.get("model"))
    if model is not None:
        payload["model"] = model
    for source_key, target_key in (
        ("input_tokens", "input_tokens"),
        ("output_tokens", "output_tokens"),
        ("cache_read_input_tokens", "cache_read_tokens"),
        ("cache_creation_input_tokens", "cache_write_tokens"),
    ):
        value = _int_or_none(usage_payload.get(source_key))
        if value is not None:
            payload[target_key] = value
    return payload

def _claude_content_event_native(
    record: _ClaudeRawRecord,
    *,
    content_index: int | None = None,
    content_type: str | None = None,
) -> dict[str, object]:
    native = _claude_event_native(record)
    if content_index is not None:
        native["content_index"] = content_index
    if content_type is not None:
        native["content_type"] = content_type
    request_id = _claude_record_request_id(record)
    if request_id is not None:
        native["request_id"] = request_id
    message_id = _string_or_none(record.message.get("id"))
    if message_id is not None:
        native["message_id"] = message_id
    model = _string_or_none(record.message.get("model"))
    if model is not None:
        native["model"] = model
    return native

def _claude_common_event_extra(record: _ClaudeRawRecord) -> dict[str, object | None]:
    return {
        "parent_uuid": record.parent_uuid,
        "request_id": _claude_record_request_id(record),
        "message_id": _string_or_none(record.message.get("id")),
    }

def _claude_record_starts_interaction(record: _ClaudeRawRecord) -> bool:
    if _claude_message_role(record) != "user":
        return False
    if _claude_record_has_tool_evidence(record):
        return False
    return _claude_record_has_visible_message(record)

def _claude_record_tool_name(record: _ClaudeRawRecord) -> str | None:
    hook_name = _string_or_none(record.data.get("hookName"))
    if hook_name is not None and ":" in hook_name:
        return hook_name.split(":")[-1].strip() or None
    return None

def _claude_messages_from_events(
    events: list[dict[str, object]],
) -> dict[str, object]:
    return _project_messages_from_events(
        events,
        project_event=_claude_message_from_event,
    )

def _claude_message_from_event(
    event: dict[str, object],
    index: int,
) -> tuple[dict[str, object] | None, list[str]]:
    if event.get("kind") != "message":
        return None, []
    surfaces = event.get("surfaces")
    if isinstance(surfaces, dict) and surfaces.get("transcript") != "visible":
        return None, []

    payload = _claude_event_payload(event)
    role = _string_or_none(payload.get("role"))
    if role not in {"user", "assistant"}:
        return None, [
            f"claude message event {_int_or_zero(event.get('sequence'))} has no canonical role"
        ]
    content = _dict_list(payload.get("content"))
    if not content:
        return None, [
            f"claude message event {_int_or_zero(event.get('sequence'))} has no canonical content"
        ]

    message: dict[str, object] = {
        "message_id": f"message-{index}",
        "role": role,
        "visibility": "conversation",
        "content": content,
        "native": dict(_record_native_dict(event)),
    }
    _claude_attach_event_projection_provenance(message, event)
    return message, []

def _claude_tool_invocations_from_raw_session(
    raw_session: _ClaudeRawSession,
) -> dict[str, object]:
    warnings: list[str] = []
    groups: dict[
        str,
        dict[str, list[_ClaudeToolRequestRecord | _ClaudeToolResultRecord | _ClaudeRawRecord]],
    ] = {}

    for record in raw_session.records:
        for request in _claude_tool_request_records(
            record,
            warnings=warnings,
        ):
            group = groups.setdefault(
                request.call_id,
                {
                    "tool_use": [],
                    "tool_result": [],
                    "progress_pre": [],
                    "progress_post": [],
                },
            )
            group["tool_use"].append(request)

        for result in _claude_tool_result_records(
            record,
            warnings=warnings,
        ):
            group = groups.setdefault(
                result.call_id,
                {
                    "tool_use": [],
                    "tool_result": [],
                    "progress_pre": [],
                    "progress_post": [],
                },
            )
            group["tool_result"].append(result)

        progress_kind = _claude_tool_progress_group_kind(record)
        if progress_kind is None:
            continue
        call_id = _claude_record_call_id(record)
        if call_id is None:
            warnings.append(
                f"claude progress record {record.record_index} has no toolUseID"
            )
            continue
        group = groups.setdefault(
            call_id,
            {
                "tool_use": [],
                "tool_result": [],
                "progress_pre": [],
                "progress_post": [],
            },
        )
        group[progress_kind].append(record)

    tool_invocations: list[dict[str, object]] = []
    for call_id, group in sorted(groups.items(), key=_claude_tool_group_order):
        invocation, group_warnings = _claude_tool_invocation_from_group(
            call_id=call_id,
            group=group,
            index=len(tool_invocations) + 1,
        )
        tool_invocations.append(invocation)
        warnings.extend(group_warnings)

    return {
        "tool_invocations": tool_invocations,
        "warnings": warnings,
    }

def _claude_tool_request_records(
    record: _ClaudeRawRecord,
    *,
    warnings: list[str],
) -> list[_ClaudeToolRequestRecord]:
    if _claude_message_role(record) != "assistant":
        return []
    content = record.message.get("content")
    if not isinstance(content, list):
        return []

    requests: list[_ClaudeToolRequestRecord] = []
    for content_index, item in enumerate(content, start=1):
        if not isinstance(item, dict):
            warnings.append(
                f"claude assistant tool-use record {record.record_index} content item {content_index} is not an object"
            )
            continue
        if _string_or_none(item.get("type")) != "tool_use":
            continue
        call_id = _string_or_none(item.get("id"))
        if call_id is None:
            warnings.append(
                f"claude assistant tool-use record {record.record_index} content item {content_index} has no id"
            )
            continue
        requests.append(
            _ClaudeToolRequestRecord(
                raw_record=record,
                content_index=content_index,
                call_id=call_id,
                payload=item,
                source_refs=_claude_item_source_refs(
                    record,
                    content_index=content_index,
                ),
            )
        )
    return requests

def _claude_tool_result_records(
    record: _ClaudeRawRecord,
    *,
    warnings: list[str],
) -> list[_ClaudeToolResultRecord]:
    if _claude_message_role(record) != "user":
        return []
    content = record.message.get("content")
    if not isinstance(content, list):
        return []

    results: list[_ClaudeToolResultRecord] = []
    for content_index, item in enumerate(content, start=1):
        if not isinstance(item, dict):
            warnings.append(
                f"claude user tool-result record {record.record_index} content item {content_index} is not an object"
            )
            continue
        if _string_or_none(item.get("type")) != "tool_result":
            continue
        call_id = _string_or_none(item.get("tool_use_id"))
        if call_id is None:
            warnings.append(
                f"claude user tool-result record {record.record_index} content item {content_index} has no tool_use_id"
            )
            continue
        results.append(
            _ClaudeToolResultRecord(
                raw_record=record,
                content_index=content_index,
                call_id=call_id,
                payload=item,
                tool_use_result=dict(record.tool_use_result),
                source_refs=_claude_item_source_refs(
                    record,
                    content_index=content_index,
                ),
            )
        )
    return results

def _claude_item_source_refs(
    record: _ClaudeRawRecord,
    *,
    content_index: int,
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for source_ref in record.source_refs:
        ref = dict(source_ref)
        ref["content_index"] = content_index
        refs.append(ref)
    return refs

def _claude_tool_progress_group_kind(record: _ClaudeRawRecord) -> str | None:
    if record.record_type != "progress":
        return None
    hook_event = _string_or_none(record.data.get("hookEvent"))
    if hook_event == "PreToolUse":
        return "progress_pre"
    if hook_event == "PostToolUse":
        return "progress_post"
    return None

def _claude_tool_group_order(
    item: tuple[
        str,
        dict[str, list[_ClaudeToolRequestRecord | _ClaudeToolResultRecord | _ClaudeRawRecord]],
    ],
) -> tuple[int, int]:
    _call_id, group = item
    positions = [
        _claude_tool_evidence_position(evidence)
        for records in group.values()
        for evidence in records
    ]
    return min(positions) if positions else (0, 0)

def _claude_tool_evidence_position(
    evidence: _ClaudeToolRequestRecord | _ClaudeToolResultRecord | _ClaudeRawRecord,
) -> tuple[int, int]:
    if isinstance(evidence, (_ClaudeToolRequestRecord, _ClaudeToolResultRecord)):
        return (evidence.raw_record.record_index, evidence.content_index)
    return (evidence.record_index, 0)

def _claude_tool_invocation_from_group(
    *,
    call_id: str,
    group: dict[str, list[_ClaudeToolRequestRecord | _ClaudeToolResultRecord | _ClaudeRawRecord]],
    index: int,
) -> tuple[dict[str, object], list[str]]:
    warnings: list[str] = []
    requests = [
        item
        for item in group["tool_use"]
        if isinstance(item, _ClaudeToolRequestRecord)
    ]
    results = [
        item
        for item in group["tool_result"]
        if isinstance(item, _ClaudeToolResultRecord)
    ]
    pre_progress = [
        item
        for item in group["progress_pre"]
        if isinstance(item, _ClaudeRawRecord)
    ]
    post_progress = [
        item
        for item in group["progress_post"]
        if isinstance(item, _ClaudeRawRecord)
    ]

    _warn_about_tool_group_records(
        warnings=warnings,
        provider_label=_CLAUDE_TOOL_GROUP_LABEL,
        call_id=call_id,
        kind="assistant tool_use",
        records=requests,
    )
    _warn_about_tool_group_records(
        warnings=warnings,
        provider_label=_CLAUDE_TOOL_GROUP_LABEL,
        call_id=call_id,
        kind="user tool_result",
        records=results,
    )
    _warn_about_tool_group_records(
        warnings=warnings,
        provider_label=_CLAUDE_TOOL_GROUP_LABEL,
        call_id=call_id,
        kind="PreToolUse progress",
        records=pre_progress,
    )
    _warn_about_tool_group_records(
        warnings=warnings,
        provider_label=_CLAUDE_TOOL_GROUP_LABEL,
        call_id=call_id,
        kind="PostToolUse progress",
        records=post_progress,
    )

    first_request = requests[0] if requests else None
    first_result = results[0] if results else None
    first_pre_progress = pre_progress[0] if pre_progress else None
    first_post_progress = post_progress[0] if post_progress else None

    invocation: dict[str, object] = {
        "tool_invocation_id": f"tool-invocation-{index}",
        "call_id": call_id,
        "tool_name": _claude_tool_name(
            first_request,
            first_pre_progress,
            first_post_progress,
        ),
        "status": _claude_tool_status(
            first_result,
            first_post_progress,
        ),
        "native": _claude_tool_native(
            requests=requests,
            results=results,
            pre_progress=pre_progress,
            post_progress=post_progress,
        ),
    }

    started_at = _claude_tool_started_at(
        first_request,
        first_pre_progress,
        first_result,
        first_post_progress,
    )
    if started_at is not None:
        invocation["started_at"] = started_at
    ended_at = _claude_tool_ended_at(
        first_request,
        first_pre_progress,
        first_result,
        first_post_progress,
    )
    if ended_at is not None:
        invocation["ended_at"] = ended_at

    tool_input = _claude_tool_input(first_request)
    if tool_input:
        invocation["input"] = tool_input
    output = _claude_tool_output(first_result)
    if output:
        invocation["output"] = output
    execution = _claude_tool_execution(first_result)
    if execution:
        invocation["execution"] = execution

    model = _claude_tool_model(first_request, first_result)
    if model is not None:
        invocation["model"] = model
    request_id = _claude_tool_request_id(first_request, first_result)
    if request_id is not None:
        invocation["request_id"] = request_id
    message_id = _claude_tool_message_id(first_request, first_result)
    if message_id is not None:
        invocation["message_id"] = message_id

    source_refs = _claude_tool_source_refs(
        requests,
        results,
        pre_progress,
        post_progress,
    )
    if source_refs:
        invocation["source_refs"] = source_refs

    return invocation, warnings

_CLAUDE_TOOL_GROUP_LABEL = "claude tool_use id"

def _claude_tool_name(
    request: _ClaudeToolRequestRecord | None,
    pre_progress: _ClaudeRawRecord | None,
    post_progress: _ClaudeRawRecord | None,
) -> str:
    for value in (
        request.payload.get("name") if request is not None else None,
        _claude_progress_tool_name(pre_progress),
        _claude_progress_tool_name(post_progress),
    ):
        name = _string_or_none(value)
        if name is not None:
            return name
    return "unknown"

def _claude_progress_tool_name(record: _ClaudeRawRecord | None) -> str | None:
    if record is None:
        return None
    hook_name = _string_or_none(record.data.get("hookName"))
    if hook_name is None or ":" not in hook_name:
        return None
    return hook_name.split(":")[-1].strip() or None

def _claude_tool_status(
    result: _ClaudeToolResultRecord | None,
    post_progress: _ClaudeRawRecord | None,
) -> str:
    if result is not None:
        if result.payload.get("is_error") is True:
            return "failed"
        if result.tool_use_result.get("interrupted") is True:
            return "failed"
        return "completed"
    if post_progress is not None:
        return "completed"
    return "requested"

def _claude_tool_started_at(
    request: _ClaudeToolRequestRecord | None,
    pre_progress: _ClaudeRawRecord | None,
    result: _ClaudeToolResultRecord | None,
    post_progress: _ClaudeRawRecord | None,
) -> str | None:
    return _claude_timestamp_min(
        request.raw_record.timestamp if request is not None else None,
        pre_progress.timestamp if pre_progress is not None else None,
        result.raw_record.timestamp if result is not None else None,
        post_progress.timestamp if post_progress is not None else None,
    )

def _claude_tool_ended_at(
    request: _ClaudeToolRequestRecord | None,
    pre_progress: _ClaudeRawRecord | None,
    result: _ClaudeToolResultRecord | None,
    post_progress: _ClaudeRawRecord | None,
) -> str | None:
    return _claude_timestamp_max(
        request.raw_record.timestamp if request is not None else None,
        pre_progress.timestamp if pre_progress is not None else None,
        result.raw_record.timestamp if result is not None else None,
        post_progress.timestamp if post_progress is not None else None,
    )

def _claude_timestamp_min(*values: object) -> str | None:
    timestamps = [
        timestamp
        for timestamp in (_string_or_none(value) for value in values)
        if timestamp is not None
    ]
    return min(timestamps) if timestamps else None

def _claude_timestamp_max(*values: object) -> str | None:
    timestamps = [
        timestamp
        for timestamp in (_string_or_none(value) for value in values)
        if timestamp is not None
    ]
    return max(timestamps) if timestamps else None

def _claude_tool_input(
    request: _ClaudeToolRequestRecord | None,
) -> dict[str, object]:
    if request is None:
        return {}
    tool_input = request.payload.get("input")
    if tool_input is None:
        return {}
    return {"arguments": tool_input}

def _claude_tool_output(
    result: _ClaudeToolResultRecord | None,
) -> dict[str, object]:
    if result is None:
        return {}
    output: dict[str, object] = {}
    for value in (
        result.payload.get("content"),
        result.tool_use_result.get("stdout"),
        result.tool_use_result.get("stderr"),
    ):
        text = _string_or_none(value)
        if text is not None:
            output["content"] = text
            break
    return output

def _claude_tool_execution(
    result: _ClaudeToolResultRecord | None,
) -> dict[str, object]:
    if result is None:
        return {}
    execution: dict[str, object] = {}
    _copy_present_fields(
        execution,
        result.tool_use_result,
        (
            ("stdout", "stdout"),
            ("stderr", "stderr"),
            ("interrupted", "interrupted"),
            ("isImage", "is_image"),
            ("noOutputExpected", "no_output_expected"),
        ),
    )
    return execution

def _claude_tool_model(
    request: _ClaudeToolRequestRecord | None,
    result: _ClaudeToolResultRecord | None,
) -> str | None:
    for value in (
        request.raw_record.message.get("model") if request is not None else None,
        result.raw_record.message.get("model") if result is not None else None,
    ):
        model = _string_or_none(value)
        if model is not None:
            return model
    return None

def _claude_tool_request_id(
    request: _ClaudeToolRequestRecord | None,
    result: _ClaudeToolResultRecord | None,
) -> str | None:
    for value in (
        _claude_record_request_id(request.raw_record) if request is not None else None,
        _claude_record_request_id(result.raw_record) if result is not None else None,
    ):
        request_id = _string_or_none(value)
        if request_id is not None:
            return request_id
    return None

def _claude_tool_message_id(
    request: _ClaudeToolRequestRecord | None,
    result: _ClaudeToolResultRecord | None,
) -> str | None:
    for value in (
        request.raw_record.message.get("id") if request is not None else None,
        result.raw_record.message.get("id") if result is not None else None,
    ):
        message_id = _string_or_none(value)
        if message_id is not None:
            return message_id
    return None

def _claude_tool_source_refs(
    requests: list[_ClaudeToolRequestRecord],
    results: list[_ClaudeToolResultRecord],
    pre_progress: list[_ClaudeRawRecord],
    post_progress: list[_ClaudeRawRecord],
) -> list[dict[str, object]]:
    source_refs: list[dict[str, object]] = []
    for request in requests:
        source_refs.extend(request.source_refs)
    for record in pre_progress:
        source_refs.extend(record.source_refs)
    for result in results:
        source_refs.extend(result.source_refs)
    for record in post_progress:
        source_refs.extend(record.source_refs)
    return sorted(
        _dedupe_dicts(source_refs),
        key=lambda source_ref: (
            _int_or_zero(source_ref.get("record_index")),
            _int_or_zero(source_ref.get("content_index")),
            _int_or_zero(source_ref.get("line")),
        ),
    )

def _claude_tool_native(
    *,
    requests: list[_ClaudeToolRequestRecord],
    results: list[_ClaudeToolResultRecord],
    pre_progress: list[_ClaudeRawRecord],
    post_progress: list[_ClaudeRawRecord],
) -> dict[str, object]:
    native: dict[str, object] = {
        "request_present": bool(requests),
        "result_present": bool(results),
        "pre_progress_present": bool(pre_progress),
        "post_progress_present": bool(post_progress),
        "record_indices": {
            "tool_use": [
                {
                    "record_index": request.raw_record.record_index,
                    "content_index": request.content_index,
                }
                for request in requests
            ],
            "tool_result": [
                {
                    "record_index": result.raw_record.record_index,
                    "content_index": result.content_index,
                }
                for result in results
            ],
            "progress.pre": [record.record_index for record in pre_progress],
            "progress.post": [record.record_index for record in post_progress],
        },
    }
    if requests:
        native["tool_use"] = requests[0].payload
    if results:
        native["tool_result"] = results[0].payload
        if results[0].tool_use_result:
            native["tool_use_result"] = results[0].tool_use_result
        source_tool_assistant_uuid = _string_or_none(
            results[0].raw_record.payload.get("sourceToolAssistantUUID")
        )
        if source_tool_assistant_uuid is not None:
            native["source_tool_assistant_uuid"] = source_tool_assistant_uuid
    if pre_progress:
        native["progress_pre"] = pre_progress[0].data
    if post_progress:
        native["progress_post"] = post_progress[0].data
    return native

def _claude_record_has_tool_evidence(record: _ClaudeRawRecord) -> bool:
    return bool(
        _claude_tool_request_records(record, warnings=[])
        or _claude_tool_result_records(record, warnings=[])
        or _claude_tool_progress_group_kind(record) is not None
    )

def _claude_model_runs_from_raw_session(
    raw_session: _ClaudeRawSession,
    *,
    messages: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
) -> dict[str, object]:
    warnings: list[str] = []
    request_groups: dict[str, list[_ClaudeRawRecord]] = {}

    for record in raw_session.records:
        if _claude_message_role(record) != "assistant":
            continue
        request_id = _claude_record_request_id(record)
        if request_id is None:
            continue
        request_groups.setdefault(request_id, []).append(record)

    ordered_groups = sorted(
        request_groups.items(),
        key=lambda item: item[1][0].record_index if item[1] else 0,
    )
    canonical_end_index = _claude_last_canonical_record_index(raw_session)

    model_runs: list[dict[str, object]] = []
    previous_span_end_index = 0
    for group_index, (request_id, records) in enumerate(ordered_groups):
        if not records:
            continue
        next_start_record = (
            ordered_groups[group_index + 1][1][0]
            if group_index + 1 < len(ordered_groups) and ordered_groups[group_index + 1][1]
            else None
        )
        span_start_index = previous_span_end_index + 1 if previous_span_end_index else 1
        span_end_index = (
            next_start_record.record_index - 1
            if next_start_record is not None
            else canonical_end_index
        )
        if span_end_index < records[-1].record_index:
            span_end_index = records[-1].record_index
        model_run = _claude_model_run_from_request_group(
            request_id=request_id,
            records=records,
            raw_session=raw_session,
            span_start_index=span_start_index,
            span_end_index=span_end_index,
            next_start_record=next_start_record,
            messages=messages,
            tool_invocations=tool_invocations,
            events=events,
            index=len(model_runs) + 1,
        )
        model_runs.append(model_run)
        previous_span_end_index = span_end_index

    return {
        "model_runs": model_runs,
        "warnings": warnings,
    }

def _claude_model_run_from_request_group(
    *,
    request_id: str,
    records: list[_ClaudeRawRecord],
    raw_session: _ClaudeRawSession,
    span_start_index: int,
    span_end_index: int,
    next_start_record: _ClaudeRawRecord | None,
    messages: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
    index: int,
) -> dict[str, object]:
    first_record = records[0]
    last_request_record = records[-1]
    span_end_record = _claude_record_at_index(
        raw_session,
        span_end_index,
    )

    assistant_message_ids = _claude_model_run_message_ids(records)
    native: dict[str, object] = {
        "request_record_count": len(records),
        "assistant_record_indices": [record.record_index for record in records],
        "first_request_record_index": first_record.record_index,
        "last_request_record_index": last_request_record.record_index,
        "span_start_record_index": span_start_index,
        "span_end_record_index": span_end_index,
    }
    if assistant_message_ids:
        native["assistant_message_ids"] = assistant_message_ids
    stop_reason = _claude_model_run_stop_reason(records)
    if stop_reason is not None:
        native["stop_reason"] = stop_reason

    model_run: dict[str, object] = {
        "model_run_id": f"model-run-{index}",
        "provider": "claude-code",
        "status": _claude_model_run_status(
            records=records,
            next_start_record=next_start_record,
            span_end_index=span_end_index,
        ),
        "native": native,
        "request_id": request_id,
    }

    model = _claude_model_run_model(records)
    if model is not None:
        model_run["model"] = model
    started_at = _claude_model_run_started_at(records)
    if started_at is not None:
        model_run["started_at"] = started_at
    ended_at = _claude_model_run_ended_at(
        raw_session,
        span_start_index=span_start_index,
        span_end_index=span_end_index,
    )
    if ended_at is not None:
        model_run["ended_at"] = ended_at

    source_refs = _claude_model_run_source_refs(
        first_record=first_record,
        span_end_record=span_end_record,
    )
    if source_refs:
        model_run["source_refs"] = source_refs

    message_refs = _claude_model_run_message_refs(
        messages,
        span_start_index=span_start_index,
        span_end_index=span_end_index,
    )
    if message_refs:
        model_run["message_refs"] = message_refs

    tool_refs = _claude_model_run_tool_refs(
        tool_invocations,
        request_id=request_id,
        span_start_index=span_start_index,
        span_end_index=span_end_index,
    )
    if tool_refs:
        model_run["tool_invocation_refs"] = tool_refs

    event_refs = _claude_model_run_event_refs(
        events,
        span_start_index=span_start_index,
        span_end_index=span_end_index,
    )
    if event_refs:
        model_run["event_refs"] = event_refs

    reasoning_trace = _claude_model_run_reasoning_trace_from_events(
        events,
        span_start_index=span_start_index,
        span_end_index=span_end_index,
        model_run_index=index,
    )
    if reasoning_trace:
        model_run["reasoning_trace"] = reasoning_trace

    return model_run

def _claude_last_canonical_record_index(
    raw_session: _ClaudeRawSession,
) -> int:
    for record in reversed(raw_session.records):
        if _claude_record_kind(record) == "last-prompt":
            continue
        return record.record_index
    return 0

def _claude_record_at_index(
    raw_session: _ClaudeRawSession,
    record_index: int,
) -> _ClaudeRawRecord | None:
    if record_index <= 0:
        return None
    index = record_index - 1
    if index < 0 or index >= len(raw_session.records):
        return None
    return raw_session.records[index]

def _claude_model_run_message_ids(
    records: list[_ClaudeRawRecord],
) -> list[str]:
    seen: set[str] = set()
    message_ids: list[str] = []
    for record in records:
        message_id = _string_or_none(record.message.get("id"))
        if message_id is None or message_id in seen:
            continue
        seen.add(message_id)
        message_ids.append(message_id)
    return message_ids

def _claude_model_run_stop_reason(
    records: list[_ClaudeRawRecord],
) -> str | None:
    for record in reversed(records):
        stop_reason = _string_or_none(record.message.get("stop_reason"))
        if stop_reason is not None:
            return stop_reason
    return None

def _claude_model_run_status(
    *,
    records: list[_ClaudeRawRecord],
    next_start_record: _ClaudeRawRecord | None,
    span_end_index: int,
) -> str:
    stop_reason = _claude_model_run_stop_reason(records)
    if stop_reason is not None:
        return "completed"
    if next_start_record is not None:
        return "unknown"
    if span_end_index > records[-1].record_index:
        return "unknown"
    return "running"

def _claude_model_run_model(
    records: list[_ClaudeRawRecord],
) -> str | None:
    for record in records:
        model = _string_or_none(record.message.get("model"))
        if model is not None:
            return model
    return None

def _claude_model_run_started_at(
    records: list[_ClaudeRawRecord],
) -> str | None:
    return _claude_timestamp_min(
        *(record.timestamp for record in records)
    )

def _claude_model_run_ended_at(
    raw_session: _ClaudeRawSession,
    *,
    span_start_index: int,
    span_end_index: int,
) -> str | None:
    return _claude_timestamp_max(
        *(
            record.timestamp
            for record in raw_session.records
            if span_start_index <= record.record_index <= span_end_index
            and _claude_record_kind(record) != "last-prompt"
        )
    )

def _claude_model_run_source_refs(
    *,
    first_record: _ClaudeRawRecord,
    span_end_record: _ClaudeRawRecord | None,
) -> list[dict[str, object]]:
    source_refs = list(first_record.source_refs)
    if span_end_record is not None:
        source_refs.extend(span_end_record.source_refs)
    return sorted(
        _dedupe_dicts(source_refs),
        key=lambda source_ref: (
            _int_or_zero(source_ref.get("record_index")),
            _int_or_zero(source_ref.get("line")),
        ),
    )

def _claude_model_run_message_refs(
    messages: list[dict[str, object]],
    *,
    span_start_index: int,
    span_end_index: int,
) -> list[str]:
    refs: list[str] = []
    for message in messages:
        message_id = _string_or_none(message.get("message_id"))
        record_index = _record_native_int_field(message, "record_index")
        if message_id is None or record_index is None:
            continue
        if span_start_index <= record_index <= span_end_index:
            refs.append(message_id)
    return refs

def _claude_model_run_tool_refs(
    tool_invocations: list[dict[str, object]],
    *,
    request_id: str,
    span_start_index: int,
    span_end_index: int,
) -> list[str]:
    refs: list[str] = []
    for invocation in tool_invocations:
        invocation_id = _string_or_none(invocation.get("tool_invocation_id"))
        if invocation_id is None:
            continue
        if _string_or_none(invocation.get("request_id")) == request_id:
            refs.append(invocation_id)
            continue
        source_refs = _dict_list(invocation.get("source_refs"))
        if any(
            span_start_index <= _int_or_zero(source_ref.get("record_index")) <= span_end_index
            for source_ref in source_refs
        ):
            refs.append(invocation_id)
    return refs

def _claude_model_run_event_refs(
    events: list[dict[str, object]],
    *,
    span_start_index: int,
    span_end_index: int,
) -> list[str]:
    refs: list[str] = []
    for event in events:
        event_id = _string_or_none(event.get("event_id"))
        record_index = _record_native_int_field(event, "record_index")
        if event_id is None or record_index is None:
            continue
        if span_start_index <= record_index <= span_end_index:
            refs.append(event_id)
    return refs

def _claude_model_run_reasoning_trace_from_events(
    events: list[dict[str, object]],
    *,
    span_start_index: int,
    span_end_index: int,
    model_run_index: int,
) -> list[dict[str, object]]:
    reasoning_trace: list[dict[str, object]] = []
    for event in events:
        if event.get("kind") != "reasoning":
            continue
        record_index = _record_native_int_field(event, "record_index")
        if record_index is None:
            continue
        if not span_start_index <= record_index <= span_end_index:
            continue
        payload = _claude_event_payload(event)
        content = _string_or_none(payload.get("content"))
        if content is None:
            continue
        reasoning: dict[str, object] = {
            "reasoning_id": f"reasoning-{model_run_index}-{len(reasoning_trace) + 1}",
            "visibility": _string_or_none(payload.get("visibility")) or "visible",
            "content": content,
            "native": dict(_record_native_dict(event)),
        }
        _claude_attach_event_projection_provenance(reasoning, event)
        reasoning_trace.append(reasoning)
    return reasoning_trace

def _claude_attach_model_run_refs_to_events(
    model_runs: list[dict[str, object]],
    *,
    events: list[dict[str, object]],
) -> None:
    model_run_ref_by_event_id: dict[str, str] = {}
    for model_run in model_runs:
        model_run_id = _string_or_none(model_run.get("model_run_id"))
        if model_run_id is None:
            continue
        for event_ref in _string_list(model_run.get("event_refs")):
            model_run_ref_by_event_id[event_ref] = model_run_id

    for event in events:
        event_id = _string_or_none(event.get("event_id"))
        if event_id is None:
            continue
        model_run_ref = model_run_ref_by_event_id.get(event_id)
        if model_run_ref is not None:
            event["model_run_ref"] = model_run_ref

def _claude_reasoning_native(
    record: _ClaudeRawRecord,
    *,
    content_index: int,
    item: dict[str, Any],
) -> dict[str, object]:
    native = _claude_event_native(record)
    native["reasoning_key"] = "thinking"
    native["content_index"] = content_index
    message_id = _string_or_none(record.message.get("id"))
    if message_id is not None:
        native["message_id"] = message_id
    request_id = _claude_record_request_id(record)
    if request_id is not None:
        native["request_id"] = request_id
    model = _string_or_none(record.message.get("model"))
    if model is not None:
        native["model"] = model
    signature = _string_or_none(item.get("signature"))
    if signature is not None:
        native["signature"] = signature
    return native

def _claude_usage_from_events(
    events: list[dict[str, object]],
) -> dict[str, object]:
    return _project_usage_from_events(
        events,
        project_event=_claude_usage_from_event,
    )

def _claude_usage_from_event(
    event: dict[str, object],
    index: int,
) -> tuple[dict[str, object] | list[dict[str, object]] | None, list[str]]:
    if event.get("kind") != "usage":
        return None, []

    payload = _claude_event_payload(event)
    usage: dict[str, object] = {
        "usage_id": f"usage-{index}",
        "scope": _string_or_none(payload.get("scope")) or "model_run",
        "provider": _string_or_none(payload.get("provider")) or "claude-code",
        "native": dict(_record_native_dict(event)),
    }
    model = _string_or_none(payload.get("model"))
    if model is not None:
        usage["model"] = model
    model_run_ref = _string_or_none(event.get("model_run_ref"))
    if model_run_ref is not None:
        usage["model_run_ref"] = model_run_ref
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
    ):
        value = _int_or_none(payload.get(key))
        if value is not None:
            usage[key] = value
    usage["request_count"] = _int_or_none(payload.get("request_count")) or 1
    _claude_attach_event_projection_provenance(usage, event)
    return usage, []

def _claude_usage_native(
    record: _ClaudeRawRecord,
    *,
    request_id: str | None,
    usage_payload: dict[str, Any],
) -> dict[str, object]:
    native = _claude_event_native(record)
    if request_id is not None:
        native["request_id"] = request_id
    message_id = _string_or_none(record.message.get("id"))
    if message_id is not None:
        native["message_id"] = message_id
    native["usage"] = usage_payload
    return native

def _claude_reasoning_attachment_warnings(
    *,
    raw_counts: dict[str, object],
    model_runs: list[dict[str, object]],
) -> list[str]:
    raw_reasoning_count = _int_or_zero(raw_counts.get("reasoning_evidence_count"))
    normalized_reasoning_count = _model_run_reasoning_count(model_runs)
    if raw_reasoning_count <= normalized_reasoning_count:
        return []
    return [
        "claude thinking evidence outside normalized request groups is preserved in events/messages only: "
        f"raw={raw_reasoning_count} normalized={normalized_reasoning_count}"
    ]

def _claude_usage_attachment_warnings(
    *,
    raw_counts: dict[str, object],
    usage: list[dict[str, object]],
) -> list[str]:
    raw_usage_count = _int_or_zero(raw_counts.get("usage_evidence_count"))
    if raw_usage_count <= len(usage):
        return []
    return [
        "claude usage evidence outside normalized request groups is preserved in events/messages only: "
        f"raw={raw_usage_count} normalized={len(usage)}"
    ]

def _claude_record_kind(record: _ClaudeRawRecord) -> str:
    if record.record_type is not None:
        return record.record_type
    role = _claude_message_role(record)
    if role is not None:
        return role
    return "unknown"

def _claude_event_type(record: _ClaudeRawRecord) -> str:
    record_type = record.record_type
    if record_type == "progress":
        return "claude-code.progress"
    if record_type == "system":
        subtype = _string_or_none(record.payload.get("subtype"))
        if subtype is not None:
            return f"claude-code.system.{subtype}"
        return "claude-code.system"

    role = _claude_message_role(record)
    if role is not None:
        return f"claude-code.{role}.message"

    if record_type is not None:
        return f"claude-code.{record_type}"
    return "claude-code.unknown"

def _claude_message_role(record: _ClaudeRawRecord) -> str | None:
    return _string_or_none(record.message.get("role"))

def _claude_record_request_id(record: _ClaudeRawRecord) -> str | None:
    return _string_or_none(record.payload.get("requestId"))

def _claude_record_call_id(record: _ClaudeRawRecord) -> str | None:
    call_id = _string_or_none(record.payload.get("toolUseID"))
    if call_id is not None:
        return call_id
    call_id = _string_or_none(record.payload.get("parentToolUseID"))
    if call_id is not None:
        return call_id

    content = record.message.get("content")
    if not isinstance(content, list):
        return None
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = _string_or_none(item.get("type"))
        if item_type == "tool_use":
            call_id = _string_or_none(item.get("id"))
            if call_id is not None:
                return call_id
        if item_type == "tool_result":
            call_id = _string_or_none(item.get("tool_use_id"))
            if call_id is not None:
                return call_id
    return None

def _claude_record_has_usage_payload(record: _ClaudeRawRecord) -> bool:
    return isinstance(record.message.get("usage"), dict)

def _claude_record_has_visible_message(record: _ClaudeRawRecord) -> bool:
    role = _claude_message_role(record)
    if role == "assistant":
        return _claude_record_content_item_count(record, item_type="text") > 0
    if role != "user":
        return False

    content = record.message.get("content")
    if _string_or_none(content) is not None:
        return True
    if not isinstance(content, list):
        return False
    return any(
        isinstance(item, dict)
        and _string_or_none(item.get("type")) == "text"
        and _string_or_none(item.get("text")) is not None
        for item in content
    )

def _claude_record_content_item_count(
    record: _ClaudeRawRecord,
    *,
    item_type: str,
) -> int:
    content = record.message.get("content")
    if not isinstance(content, list):
        return 0

    count = 0
    for item in content:
        if not isinstance(item, dict):
            continue
        if _string_or_none(item.get("type")) != item_type:
            continue
        if item_type == "text" and _string_or_none(item.get("text")) is None:
            continue
        if item_type == "thinking" and _string_or_none(item.get("thinking")) is None:
            continue
        count += 1
    return count

def _claude_message_native(
    record: _ClaudeRawRecord,
    *,
    content_types: list[str],
) -> dict[str, object]:
    native = _claude_event_native(record)
    role = _claude_message_role(record)
    if role is not None:
        native["role"] = role
    if content_types:
        native["content_types"] = content_types

    for source_key, target_key in (
        ("id", "message_id"),
        ("model", "model"),
        ("type", "message_type"),
        ("stop_reason", "stop_reason"),
        ("stop_sequence", "stop_sequence"),
    ):
        value = record.message.get(source_key)
        if value is not None:
            native[target_key] = value

    request_id = _claude_record_request_id(record)
    if request_id is not None:
        native["request_id"] = request_id

    stop_details = record.message.get("stop_details")
    if isinstance(stop_details, dict) and stop_details:
        native["stop_details"] = stop_details

    usage = record.message.get("usage")
    if isinstance(usage, dict) and usage:
        native["usage"] = usage

    return native

def _claude_event_payload(event: dict[str, object]) -> dict[str, Any]:
    payload = event.get("payload")
    if isinstance(payload, dict):
        return dict(payload)
    return {}

def _claude_event_native(record: _ClaudeRawRecord) -> dict[str, object]:
    native: dict[str, object] = {
        "record_index": record.record_index,
        "line": record.line,
        "record_type": record.record_type or "message",
    }
    if record.uuid is not None:
        native["uuid"] = record.uuid
    if record.parent_uuid is not None:
        native["parent_uuid"] = record.parent_uuid
    role = _claude_message_role(record)
    if role is not None:
        native["message_role"] = role
    return native

def _claude_attach_event_projection_provenance(
    payload: dict[str, object],
    event: dict[str, object],
) -> None:
    timestamp = _string_or_none(event.get("timestamp"))
    if timestamp is not None:
        payload["timestamp"] = timestamp
    source_refs = _dict_list(event.get("source_refs"))
    if source_refs:
        payload["source_refs"] = source_refs

def _claude_last_prompt_record_count(raw_counts: dict[str, object]) -> int:
    return _count_payload(raw_counts.get("record_types")).get("last-prompt", 0)

def _claude_canonical_event_candidate_count(raw_counts: dict[str, object]) -> int:
    record_types = _count_payload(raw_counts.get("record_types"))
    semantic_count = (
        _int_or_zero(raw_counts.get("visible_message_record_count"))
        + _int_or_zero(raw_counts.get("tool_use_count"))
        + _int_or_zero(raw_counts.get("tool_result_count"))
        + _int_or_zero(raw_counts.get("progress_count"))
        + _int_or_zero(raw_counts.get("reasoning_evidence_count"))
        + _int_or_zero(raw_counts.get("usage_evidence_count"))
        + record_types.get("system", 0)
        + record_types.get("unknown", 0)
    )
    if semantic_count:
        return semantic_count
    return max(
        0,
        _int_or_zero(raw_counts.get("records")) - _claude_last_prompt_record_count(raw_counts),
    )

def _claude_unsupported_concepts(
    *,
    raw_counts: dict[str, object],
    messages: list[dict[str, object]],
    model_runs: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
    usage: list[dict[str, object]],
) -> list[str]:
    unsupported: list[str] = []
    if _int_or_zero(raw_counts.get("visible_message_record_count")) and not messages:
        unsupported.append("messages")
    if _int_or_zero(raw_counts.get("distinct_request_count")) and not model_runs:
        unsupported.append("model_runs")
    if _int_or_zero(raw_counts.get("tool_use_count")) and not tool_invocations:
        unsupported.append("tool_invocations")
    if _claude_canonical_event_candidate_count(raw_counts) and not events:
        unsupported.append("events")
    raw_reasoning_count = _int_or_zero(raw_counts.get("reasoning_evidence_count"))
    if raw_reasoning_count and _model_run_reasoning_count(model_runs) < raw_reasoning_count:
        unsupported.append("reasoning")
    raw_usage_count = _int_or_zero(raw_counts.get("usage_evidence_count"))
    if raw_usage_count and len(usage) < raw_usage_count:
        unsupported.append("usage")
    return unsupported

def _claude_normalization_metadata(
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
        "coverage": _claude_normalization_coverage(
            raw_counts=raw_counts,
            messages=messages,
            model_runs=model_runs,
            tool_invocations=tool_invocations,
            events=events,
            usage=usage,
        ),
        "deferred_concepts": deferred_concepts,
    }

def _claude_normalization_coverage(
    *,
    raw_counts: dict[str, object],
    messages: list[dict[str, object]],
    model_runs: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
    usage: list[dict[str, object]],
) -> dict[str, object]:
    reasoning_count = _model_run_reasoning_count(model_runs)
    raw_event_candidate_count = _claude_canonical_event_candidate_count(raw_counts)
    event_status = _coverage_status(len(events))
    if raw_event_candidate_count and len(events) >= raw_event_candidate_count:
        event_status = "normalized"
    elif raw_event_candidate_count and len(events):
        event_status = "partial"
    raw_visible_message_count = _int_or_zero(raw_counts.get("visible_message_record_count"))
    message_status = _coverage_status(len(messages))
    if raw_visible_message_count and len(messages) == raw_visible_message_count:
        message_status = "normalized"
    elif raw_visible_message_count and len(messages):
        message_status = "partial"
    raw_request_count = _int_or_zero(raw_counts.get("distinct_request_count"))
    model_run_status = _coverage_status(len(model_runs))
    if raw_request_count and len(model_runs) == raw_request_count:
        model_run_status = "normalized"
    elif raw_request_count and len(model_runs):
        model_run_status = "partial"
    raw_tool_use_count = _int_or_zero(raw_counts.get("tool_use_count"))
    tool_status = _coverage_status(len(tool_invocations))
    if raw_tool_use_count and len(tool_invocations) == raw_tool_use_count:
        tool_status = "normalized"
    elif raw_tool_use_count and len(tool_invocations):
        tool_status = "partial"
    raw_reasoning_count = _int_or_zero(raw_counts.get("reasoning_evidence_count"))
    reasoning_status = _coverage_status(reasoning_count)
    if raw_reasoning_count and reasoning_count == raw_reasoning_count:
        reasoning_status = "normalized"
    elif raw_reasoning_count and reasoning_count:
        reasoning_status = "partial"
    raw_usage_count = _int_or_zero(raw_counts.get("usage_evidence_count"))
    usage_status = _coverage_status(len(usage))
    if raw_usage_count and len(usage) == raw_usage_count:
        usage_status = "normalized"
    elif raw_usage_count and len(usage):
        usage_status = "partial"
    return {
        "messages": {
            "status": message_status,
            "raw_visible_message_record_count": raw_visible_message_count,
            "normalized_count": len(messages),
        },
        "model_runs": {
            "status": model_run_status,
            "raw_request_count": raw_request_count,
            "normalized_count": len(model_runs),
        },
        "tool_invocations": {
            "status": tool_status,
            "raw_tool_use_count": raw_tool_use_count,
            "raw_tool_result_count": _int_or_zero(raw_counts.get("tool_result_count")),
            "normalized_count": len(tool_invocations),
        },
        "events": {
            "status": event_status,
            "raw_record_count": _int_or_zero(raw_counts.get("records")),
            "raw_canonical_candidate_count": raw_event_candidate_count,
            "raw_progress_count": _int_or_zero(raw_counts.get("progress_count")),
            "normalized_count": len(events),
        },
        "reasoning": {
            "status": reasoning_status,
            "raw_evidence_count": raw_reasoning_count,
            "normalized_count": reasoning_count,
        },
        "usage": {
            "status": usage_status,
            "raw_evidence_count": raw_usage_count,
            "normalized_count": len(usage),
        },
    }

def _load_claude_raw_session_records(
    path: Path,
    *,
    source_ref_id: str | None,
) -> _ClaudeRawSession:
    records: list[_ClaudeRawRecord] = []
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
                    f"claude raw session line {line_number} is invalid json: {exc.msg}"
                )
                continue
            if not isinstance(obj, dict):
                warnings.append(
                    f"claude raw session line {line_number} is not a json object"
                )
                continue

            message = obj.get("message")
            if not isinstance(message, dict):
                message = {}
            data = obj.get("data")
            if not isinstance(data, dict):
                data = {}
            tool_use_result = obj.get("toolUseResult")
            if not isinstance(tool_use_result, dict):
                tool_use_result = {}

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
                _ClaudeRawRecord(
                    record_index=record_index,
                    line=line_number,
                    uuid=_string_or_none(obj.get("uuid")),
                    parent_uuid=_string_or_none(obj.get("parentUuid")),
                    timestamp=_string_or_none(obj.get("timestamp")),
                    record_type=_string_or_none(obj.get("type")),
                    message=message,
                    data=data,
                    tool_use_result=tool_use_result,
                    payload=obj,
                    source_refs=source_refs,
                )
            )
    return _ClaudeRawSession(
        path=path,
        source_ref_id=source_ref_id,
        records=records,
        warnings=warnings,
    )
