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
    message_result = _claude_messages_from_raw_session(raw_session)
    messages = _dict_list(message_result["messages"])
    event_result = _claude_events_from_raw_session(raw_session)
    events = _dict_list(event_result["events"])
    deferred_concepts = [
        "tool_invocations",
        "model_runs",
        "reasoning",
        "usage",
    ]

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
            "claude raw session messages normalized from visible message records: "
            f"{len(messages)} messages"
        )
    if events:
        warnings.append(
            "claude raw session events normalized from raw records: "
            f"{len(events)} events"
        )
    warnings.extend(_string_list(message_result["warnings"]))
    warnings.extend(_string_list(event_result["warnings"]))
    warnings.append(
        "claude raw session messages and events phase is active; tool invocations, model runs, "
        "reasoning, and usage remain deferred"
    )

    return _ExperimentalNormalizationResult(
        messages=messages,
        model_runs=[],
        tool_invocations=[],
        events=events,
        usage=[],
        normalizer="claude-code.raw_session.experimental.v1",
        source_mode="claude_code_raw_session",
        warnings=warnings,
        unsupported_concepts=[
            *_experimental_unsupported_concepts(
                messages=messages,
                model_runs=[],
                tool_invocations=[],
                events=events,
            ),
            "reasoning",
            "usage",
        ],
        metadata=_claude_normalization_metadata(
            raw_counts=raw_counts,
            messages=messages,
            model_runs=[],
            tool_invocations=[],
            events=events,
            usage=[],
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
    usage_evidence_keys: set[str] = set()

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
            usage_evidence_keys.add(request_id or f"record-{record.record_index}")

    return {
        "records": len(raw_session.records),
        "record_types": _sorted_count_dict(record_types),
        "parse_warning_count": len(raw_session.warnings),
        "visible_message_record_count": visible_message_record_count,
        "tool_use_count": tool_use_count,
        "tool_result_count": tool_result_count,
        "progress_count": progress_count,
        "reasoning_evidence_count": reasoning_evidence_count,
        "usage_evidence_count": len(usage_evidence_keys),
        "distinct_request_count": len(request_ids),
    }

def _claude_events_from_raw_session(
    raw_session: _ClaudeRawSession,
) -> dict[str, object]:
    events: list[dict[str, object]] = []
    warnings: list[str] = []

    for record in raw_session.records:
        if _claude_record_kind(record) == "last-prompt":
            continue

        event: dict[str, object] = {
            "event_id": f"event-{len(events) + 1}",
            "type": _claude_event_type(record),
            "data": _claude_event_data(record),
            "native": _claude_event_native(record),
        }
        _claude_attach_event_provenance(event, record)

        parent_uuid = record.parent_uuid
        if parent_uuid is not None:
            event["parent_uuid"] = parent_uuid

        request_id = _claude_record_request_id(record)
        if request_id is not None:
            event["request_id"] = request_id

        message_id = _string_or_none(record.message.get("id"))
        if message_id is not None:
            event["message_id"] = message_id

        call_id = _claude_record_call_id(record)
        if call_id is not None:
            event["call_id"] = call_id

        events.append(event)

    return {
        "events": events,
        "warnings": warnings,
    }

def _claude_messages_from_raw_session(
    raw_session: _ClaudeRawSession,
) -> dict[str, object]:
    messages: list[dict[str, object]] = []
    warnings: list[str] = []

    for record in raw_session.records:
        role = _claude_message_role(record)
        if role not in {"user", "assistant"}:
            continue

        content, content_types, content_warnings = _claude_message_content_blocks(record)
        warnings.extend(content_warnings)
        if not content:
            continue

        message: dict[str, object] = {
            "message_id": f"message-{len(messages) + 1}",
            "role": role,
            "visibility": "conversation",
            "content": content,
            "native": _claude_message_native(
                record,
                content_types=content_types,
            ),
        }
        _claude_attach_event_provenance(message, record)
        messages.append(message)

    return {
        "messages": messages,
        "warnings": warnings,
    }

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

def _claude_message_content_blocks(
    record: _ClaudeRawRecord,
) -> tuple[list[dict[str, object]], list[str], list[str]]:
    role = _claude_message_role(record)
    content = record.message.get("content")

    if role == "user":
        if isinstance(content, str):
            text = _string_or_none(content)
            if text is None:
                return [], ["string"], []
            return [{"type": "text", "text": text}], ["string"], []
        if not isinstance(content, list):
            return [], [], []

        blocks: list[dict[str, object]] = []
        content_types: list[str] = []
        warnings: list[str] = []
        for item_index, item in enumerate(content, start=1):
            if not isinstance(item, dict):
                warnings.append(
                    f"claude user message record {record.record_index} content item {item_index} is not an object"
                )
                continue
            item_type = _string_or_none(item.get("type"))
            if item_type is not None:
                content_types.append(item_type)
            if item_type != "text":
                continue
            text = _string_or_none(item.get("text"))
            if text is None:
                warnings.append(
                    f"claude user message record {record.record_index} content item {item_index} has no text"
                )
                continue
            blocks.append({"type": "text", "text": text})
        return blocks, content_types, warnings

    if role != "assistant":
        return [], [], []
    if not isinstance(content, list):
        return [], [], []

    blocks: list[dict[str, object]] = []
    content_types: list[str] = []
    warnings = []
    for item_index, item in enumerate(content, start=1):
        if not isinstance(item, dict):
            warnings.append(
                f"claude assistant message record {record.record_index} content item {item_index} is not an object"
            )
            continue
        item_type = _string_or_none(item.get("type"))
        if item_type is not None:
            content_types.append(item_type)
        if item_type != "text":
            continue
        text = _string_or_none(item.get("text"))
        if text is None:
            warnings.append(
                f"claude assistant message record {record.record_index} content item {item_index} has no text"
            )
            continue
        blocks.append({"type": "text", "text": text})
    return blocks, content_types, warnings

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

def _claude_event_data(record: _ClaudeRawRecord) -> dict[str, object]:
    data: dict[str, object] = {}
    if record.message:
        data["message"] = dict(record.message)
    if record.data:
        data["data"] = dict(record.data)
    if record.tool_use_result:
        data["tool_use_result"] = dict(record.tool_use_result)

    for source_key, target_key in (
        ("sessionId", "session_id"),
        ("cwd", "cwd"),
        ("version", "version"),
        ("gitBranch", "git_branch"),
        ("isSidechain", "is_sidechain"),
        ("userType", "user_type"),
        ("permissionMode", "permission_mode"),
        ("sourceToolAssistantUUID", "source_tool_assistant_uuid"),
        ("toolUseID", "tool_use_id"),
        ("parentToolUseID", "parent_tool_use_id"),
        ("subtype", "subtype"),
        ("durationMs", "duration_ms"),
        ("isMeta", "is_meta"),
    ):
        value = record.payload.get(source_key)
        if value is not None:
            data[target_key] = value

    return data

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

def _claude_attach_event_provenance(
    payload: dict[str, object],
    record: _ClaudeRawRecord,
) -> None:
    if record.timestamp is not None:
        payload["timestamp"] = record.timestamp
    if record.source_refs:
        payload["source_refs"] = record.source_refs

def _claude_last_prompt_record_count(raw_counts: dict[str, object]) -> int:
    return _count_payload(raw_counts.get("record_types")).get("last-prompt", 0)

def _claude_canonical_event_candidate_count(raw_counts: dict[str, object]) -> int:
    return max(
        0,
        _int_or_zero(raw_counts.get("records")) - _claude_last_prompt_record_count(raw_counts),
    )

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
    if raw_event_candidate_count and len(events) == raw_event_candidate_count:
        event_status = "normalized"
    elif raw_event_candidate_count and len(events):
        event_status = "partial"
    raw_visible_message_count = _int_or_zero(raw_counts.get("visible_message_record_count"))
    message_status = _coverage_status(len(messages))
    if raw_visible_message_count and len(messages) == raw_visible_message_count:
        message_status = "normalized"
    elif raw_visible_message_count and len(messages):
        message_status = "partial"
    return {
        "messages": {
            "status": message_status,
            "raw_visible_message_record_count": raw_visible_message_count,
            "normalized_count": len(messages),
        },
        "model_runs": {
            "status": _coverage_status(len(model_runs)),
            "raw_request_count": _int_or_zero(raw_counts.get("distinct_request_count")),
            "normalized_count": len(model_runs),
        },
        "tool_invocations": {
            "status": _coverage_status(len(tool_invocations)),
            "raw_tool_use_count": _int_or_zero(raw_counts.get("tool_use_count")),
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
            "status": _coverage_status(reasoning_count),
            "raw_evidence_count": _int_or_zero(raw_counts.get("reasoning_evidence_count")),
            "normalized_count": reasoning_count,
        },
        "usage": {
            "status": _coverage_status(len(usage)),
            "raw_evidence_count": _int_or_zero(raw_counts.get("usage_evidence_count")),
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
