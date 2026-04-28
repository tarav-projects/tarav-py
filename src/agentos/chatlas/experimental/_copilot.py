from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.chat.extractors.copilot_cli import is_copilot_cli_session_path

from ._shared import *

_COPILOT_MESSAGE_NATIVE_FIELDS = (
    ("messageId", "message_id"),
    ("requestId", "request_id"),
    ("phase", "phase"),
    ("outputTokens", "output_tokens"),
    ("toolRequests", "tool_requests"),
    ("reasoningText", "reasoning_text"),
    ("reasoningOpaque", "reasoning_opaque"),
    ("encryptedContent", "encrypted_content"),
    ("interactionId", "interaction_id"),
)

_COPILOT_REASONING_NATIVE_FIELDS = (
    ("messageId", "message_id"),
    ("requestId", "request_id"),
    ("phase", "phase"),
    ("interactionId", "interaction_id"),
    ("outputTokens", "output_tokens"),
)

_COPILOT_USAGE_NATIVE_FIELDS = (
    ("shutdownType", "shutdown_type"),
    ("totalPremiumRequests", "total_premium_requests"),
    ("totalApiDurationMs", "total_api_duration_ms"),
    ("sessionStartTime", "session_start_time"),
    ("currentModel", "current_model"),
)

@dataclass(frozen=True)
class _CopilotRawEvent:
    event_index: int
    line: int
    event_id: str | None
    parent_id: str | None
    timestamp: str | None
    event_type: str | None
    data: dict[str, Any]
    source_refs: list[dict[str, object]]

@dataclass(frozen=True)
class _CopilotRawEvents:
    path: Path
    source_ref_id: str | None
    events: list[_CopilotRawEvent]
    warnings: list[str]

@dataclass(frozen=True)
class _CopilotToolRequestRecord:
    raw_event: _CopilotRawEvent
    request_index: int
    call_id: str
    payload: dict[str, Any]
    source_refs: list[dict[str, object]]

def _experimental_normalize_copilot_cli_raw_events(
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
        if not is_copilot_cli_session_path(primary_path):
            return None
    except (CliError, OSError):
        return None

    source_ref_id = _source_ref_id_for_artifact(primary_artifact, sources=sources)
    raw_events = _load_copilot_raw_events(
        primary_path,
        source_ref_id=source_ref_id,
    )
    raw_counts = _copilot_raw_event_counts(raw_events)

    message_result = _copilot_messages_from_raw_events(raw_events)
    messages = _dict_list(message_result["messages"])
    tool_result = _copilot_tool_invocations_from_raw_events(raw_events)
    tool_invocations = _dict_list(tool_result["tool_invocations"])
    tool_invocation_refs_by_call_id = _tool_invocation_refs_by_call_id(
        tool_invocations,
    )
    event_result = _copilot_events_from_raw_events(
        raw_events,
        tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
    )
    events = _dict_list(event_result["events"])
    _attach_event_refs_to_tool_invocations(
        tool_invocations,
        events=events,
    )
    model_run_result = _copilot_model_runs_from_raw_events(
        raw_events,
        messages=messages,
        tool_invocations=tool_invocations,
        events=events,
    )
    model_runs = _dict_list(model_run_result["model_runs"])
    usage_result = _copilot_usage_from_raw_events(raw_events)
    usage = _dict_list(usage_result["usage"])
    residual_unsupported_concepts = _copilot_residual_unsupported_concepts(
        raw_counts=raw_counts,
        usage=usage,
    )

    warnings = [
        *raw_events.warnings,
        (
            "copilot raw events parsed for future normalization: "
            f"{len(raw_events.events)} events"
        ),
    ]
    if events:
        warnings.append(
            "copilot raw events normalized from events.jsonl: "
            f"{len(events)} events"
        )
    if messages:
        warnings.append(
            "copilot raw events messages normalized from message events: "
            f"{len(messages)} messages"
        )
    if tool_invocations:
        warnings.append(
            "copilot raw events tool invocations normalized by toolCallId: "
            f"{len(tool_invocations)} invocations"
        )
    if model_runs:
        warnings.append(
            "copilot raw events model runs normalized from turn events: "
            f"{len(model_runs)} runs"
        )
    if usage:
        warnings.append(
            "copilot raw events usage normalized from session.shutdown.modelMetrics: "
            f"{len(usage)} records"
        )
    warnings.extend(_string_list(message_result["warnings"]))
    warnings.extend(_string_list(tool_result["warnings"]))
    warnings.extend(_string_list(event_result["warnings"]))
    warnings.extend(_string_list(model_run_result["warnings"]))
    warnings.extend(_string_list(usage_result["warnings"]))
    warnings.extend(
        _copilot_reasoning_attachment_warnings(
            raw_counts=raw_counts,
            model_runs=model_runs,
        )
    )

    return _ExperimentalNormalizationResult(
        messages=messages,
        model_runs=model_runs,
        tool_invocations=tool_invocations,
        events=events,
        usage=usage,
        normalizer="copilot-cli.raw_events.experimental.v1",
        source_mode="copilot_cli_raw_events",
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
        metadata=_copilot_normalization_metadata(
            raw_counts=raw_counts,
            messages=messages,
            model_runs=model_runs,
            tool_invocations=tool_invocations,
            events=events,
            usage=usage,
            deferred_concepts=residual_unsupported_concepts,
        ),
    )

def _copilot_events_from_raw_events(
    raw_events: _CopilotRawEvents,
    *,
    tool_invocation_refs_by_call_id: dict[str, str] | None = None,
) -> dict[str, object]:
    event_builder = _SemanticEventBuilder()
    warnings: list[str] = []
    interaction_refs_by_raw_id: dict[str, str] = {}
    current_interaction_ref: str | None = None

    for raw_event in raw_events.events:
        event_type = raw_event.event_type or "unknown"
        if raw_event.event_type is None:
            warnings.append(
                f"copilot event record {raw_event.event_index} has no event type"
            )

        interaction_ref = _copilot_event_interaction_ref(
            raw_event,
            interaction_refs_by_raw_id=interaction_refs_by_raw_id,
            current_interaction_ref=current_interaction_ref,
        )
        if interaction_ref != "session":
            current_interaction_ref = interaction_ref
        event = event_builder.append(
            kind=_copilot_event_kind(raw_event),
            producer=_copilot_event_producer(raw_event),
            surfaces=_copilot_event_surfaces(raw_event),
            interaction_ref=interaction_ref,
            payload=dict(raw_event.data),
            timestamp=raw_event.timestamp,
            source_refs=raw_event.source_refs,
            outcome=_copilot_event_outcome(raw_event),
            legacy_type=f"copilot-cli.{event_type}",
            legacy_data=dict(raw_event.data),
            legacy_native=_copilot_event_native(raw_event),
        )

        turn_id = _copilot_event_turn_id(raw_event)
        if turn_id is not None:
            event["turn_id"] = turn_id

        call_id = _copilot_event_call_id(raw_event)
        if call_id is not None:
            event["call_id"] = call_id
            tool_invocation_ref = (
                tool_invocation_refs_by_call_id or {}
            ).get(call_id)
            if tool_invocation_ref is not None:
                event["tool_invocation_ref"] = tool_invocation_ref
            elif raw_event.event_type in {
                "tool.execution_start",
                "tool.execution_complete",
            }:
                warnings.append(
                    f"copilot tool event {raw_event.event_index} has no matching tool invocation for toolCallId {call_id}"
                )

    return {
        "events": event_builder.events,
        "warnings": warnings,
    }

def _copilot_event_interaction_ref(
    raw_event: _CopilotRawEvent,
    *,
    interaction_refs_by_raw_id: dict[str, str],
    current_interaction_ref: str | None,
) -> str:
    event_type = raw_event.event_type
    if event_type in {"session.start", "session.model_change", "session.shutdown"}:
        return "session"
    raw_interaction_id = _string_or_none(raw_event.data.get("interactionId"))
    if raw_interaction_id is not None:
        interaction_ref = interaction_refs_by_raw_id.get(raw_interaction_id)
        if interaction_ref is None:
            interaction_ref = current_interaction_ref or (
                f"interaction-{len(interaction_refs_by_raw_id) + 1}"
            )
            interaction_refs_by_raw_id[raw_interaction_id] = interaction_ref
        return interaction_ref
    if event_type == "user.message":
        if current_interaction_ref is None:
            return "interaction-1"
        next_index = _copilot_interaction_ref_index(current_interaction_ref) + 1
        return f"interaction-{next_index}"
    if event_type == "system.message" and current_interaction_ref is None:
        return "session"
    if current_interaction_ref is not None:
        return current_interaction_ref
    return "interaction-1"

def _copilot_interaction_ref_index(interaction_ref: str) -> int:
    prefix = "interaction-"
    if not interaction_ref.startswith(prefix):
        return 1
    return _int_or_none(interaction_ref[len(prefix):]) or 1

def _copilot_event_kind(raw_event: _CopilotRawEvent) -> str:
    event_type = raw_event.event_type
    if event_type == "session.start":
        return "session.start"
    if event_type == "session.shutdown":
        return "session.end"
    if event_type == "session.model_change":
        return "session.update"
    if event_type == "system.message":
        return "context"
    if event_type in {"user.message", "assistant.message"}:
        if (
            event_type == "assistant.message"
            and _copilot_is_tool_request_only_message(raw_event)
            and not _copilot_event_has_readable_content(raw_event)
        ):
            return "tool.call"
        return "message"
    if event_type == "assistant.turn_start":
        return "run.start"
    if event_type == "assistant.turn_end":
        return "run.end"
    if event_type == "tool.execution_start":
        return "tool.progress"
    if event_type == "tool.execution_complete":
        return "tool.result"
    return "session.update"

def _copilot_event_producer(raw_event: _CopilotRawEvent) -> dict[str, object]:
    event_type = raw_event.event_type
    if event_type == "user.message":
        return _semantic_event_producer("user")
    if event_type in {
        "assistant.message",
        "assistant.turn_start",
        "assistant.turn_end",
    }:
        return _semantic_event_producer("assistant")
    if event_type in {"tool.execution_start", "tool.execution_complete"}:
        return _semantic_event_producer(
            "tool",
            name=_string_or_none(raw_event.data.get("toolName")),
        )
    if event_type == "system.message":
        return _semantic_event_producer("system")
    return _semantic_event_producer("provider")

def _copilot_event_surfaces(raw_event: _CopilotRawEvent) -> dict[str, object]:
    event_type = raw_event.event_type
    if event_type == "system.message":
        return _semantic_event_surfaces(
            transcript="hidden",
            model_input="visible",
        )
    if event_type in {"user.message", "assistant.message"}:
        if (
            event_type == "assistant.message"
            and _copilot_is_tool_request_only_message(raw_event)
            and not _copilot_event_has_readable_content(raw_event)
        ):
            return _semantic_event_surfaces(
                transcript="hidden",
                model_input="visible",
            )
        return _semantic_event_surfaces(
            transcript="visible",
            model_input="visible",
        )
    if event_type == "tool.execution_complete":
        return _semantic_event_surfaces(
            transcript="hidden",
            model_input="visible",
        )
    if event_type == "tool.execution_start":
        return _semantic_event_surfaces(transcript="hidden")
    return _semantic_event_surfaces(transcript="hidden")

def _copilot_event_outcome(raw_event: _CopilotRawEvent) -> str | None:
    event_type = raw_event.event_type
    if event_type == "assistant.turn_end":
        return "ok"
    if event_type == "session.shutdown":
        return "ok"
    if event_type != "tool.execution_complete":
        return None
    success = raw_event.data.get("success")
    if success is True:
        return "ok"
    if success is False:
        return "error"
    return None

def _copilot_event_has_readable_content(raw_event: _CopilotRawEvent) -> bool:
    content = raw_event.data.get("content")
    if _string_or_none(content) is not None:
        return True
    if isinstance(content, list):
        for item in content:
            if _string_or_none(item) is not None:
                return True
            if (
                isinstance(item, dict)
                and _string_or_none(item.get("text")) is not None
            ):
                return True
    return False

def _copilot_event_native(raw_event: _CopilotRawEvent) -> dict[str, object]:
    native: dict[str, object] = {
        "event_type": raw_event.event_type or "unknown",
        "event_index": raw_event.event_index,
        "line": raw_event.line,
    }
    if raw_event.event_id is not None:
        native["event_id"] = raw_event.event_id
    if raw_event.parent_id is not None:
        native["parent_id"] = raw_event.parent_id
    interaction_id = _string_or_none(raw_event.data.get("interactionId"))
    if interaction_id is not None:
        native["interaction_id"] = interaction_id
    return native

def _copilot_event_turn_id(raw_event: _CopilotRawEvent) -> str | None:
    return _string_or_none(raw_event.data.get("turnId"))

def _copilot_event_call_id(raw_event: _CopilotRawEvent) -> str | None:
    return _string_or_none(raw_event.data.get("toolCallId"))

def _copilot_attach_event_provenance(
    payload: dict[str, object],
    raw_event: _CopilotRawEvent,
) -> None:
    if raw_event.timestamp is not None:
        payload["timestamp"] = raw_event.timestamp
    if raw_event.source_refs:
        payload["source_refs"] = raw_event.source_refs

def _copilot_record_event_index(record: dict[str, object]) -> int | None:
    event_index = _record_native_int_field(record, "event_index")
    if event_index is not None:
        return event_index
    return _source_ref_first_event_index(record.get("source_refs"))

def _copilot_record_event_id(record: dict[str, object]) -> str | None:
    return _record_native_string_field(record, "event_id")

def _copilot_messages_from_raw_events(
    raw_events: _CopilotRawEvents,
) -> dict[str, object]:
    messages: list[dict[str, object]] = []
    warnings: list[str] = []

    for raw_event in raw_events.events:
        if raw_event.event_type not in {
            "system.message",
            "user.message",
            "assistant.message",
        }:
            continue

        role = _copilot_message_role(raw_event)
        content, content_types, content_warnings = _copilot_message_content_blocks(
            raw_event,
        )
        warnings.extend(content_warnings)

        if not content:
            if _copilot_is_tool_request_only_message(raw_event):
                continue
            warnings.append(
                f"copilot message event {raw_event.event_index} has no readable content"
            )
            continue

        message: dict[str, object] = {
            "message_id": f"message-{len(messages) + 1}",
            "role": role,
            "visibility": _copilot_message_visibility(raw_event),
            "content": content,
            "native": _copilot_message_native(
                raw_event,
                content_types=content_types,
            ),
        }
        _copilot_attach_event_provenance(message, raw_event)

        messages.append(message)

    return {
        "messages": messages,
        "warnings": warnings,
    }

def _copilot_message_role(raw_event: _CopilotRawEvent) -> str:
    if raw_event.event_type == "system.message":
        return _string_or_none(raw_event.data.get("role")) or "system"
    if raw_event.event_type == "user.message":
        return "user"
    if raw_event.event_type == "assistant.message":
        return "assistant"
    return "unknown"

def _copilot_message_visibility(raw_event: _CopilotRawEvent) -> str:
    if raw_event.event_type == "system.message":
        return "context"
    if raw_event.event_type in {"user.message", "assistant.message"}:
        return "conversation"
    return "unknown"

def _copilot_message_content_blocks(
    raw_event: _CopilotRawEvent,
) -> tuple[list[dict[str, object]], list[str], list[str]]:
    content_value = raw_event.data.get("content")
    if content_value is None:
        blocks, content_types, warnings = [], [], []
    else:
        blocks, content_types, warnings = _copilot_text_content_blocks(
            content_value,
            context=f"copilot message event {raw_event.event_index} content",
        )
    tool_request_blocks, tool_request_types, tool_request_warnings = (
        _copilot_tool_request_content_blocks(
            raw_event.data.get("toolRequests"),
            context=f"copilot message event {raw_event.event_index} toolRequests",
        )
    )
    attachment_blocks, attachment_types, attachment_warnings = (
        _copilot_attachment_content_blocks(
            raw_event.data.get("attachments"),
            context=f"copilot message event {raw_event.event_index} attachments",
        )
    )
    return (
        [*blocks, *tool_request_blocks, *attachment_blocks],
        [*content_types, *tool_request_types, *attachment_types],
        [*warnings, *tool_request_warnings, *attachment_warnings],
    )

def _copilot_text_content_blocks(
    value: object,
    *,
    context: str,
) -> tuple[list[dict[str, object]], list[str], list[str]]:
    if isinstance(value, str):
        text = _string_or_none(value)
        if text is None:
            return [], ["string"], []
        return [{"type": "text", "text": text}], ["string"], []

    if not isinstance(value, list):
        return [], [], [f"{context} is not readable text"]

    blocks: list[dict[str, object]] = []
    content_types: list[str] = []
    warnings: list[str] = []
    for item_index, item in enumerate(value, start=1):
        if isinstance(item, str):
            text = _string_or_none(item)
            if text is not None:
                blocks.append({"type": "text", "text": text})
                content_types.append("string")
            continue

        if not isinstance(item, dict):
            blocks.append(
                {
                    "type": "unknown",
                    "native": {"value": item},
                }
            )
            warnings.append(f"{context} item {item_index} is not an object")
            continue

        item_type = _string_or_none(item.get("type"))
        if item_type is not None:
            content_types.append(item_type)

        if item_type == "image":
            blocks.append(
                {
                    "type": "image",
                    "native": item,
                }
            )
            continue

        text = _string_or_none(item.get("text"))
        if text is None:
            blocks.append(
                {
                    "type": "unknown",
                    "native": item,
                }
            )
            warnings.append(f"{context} item {item_index} has no text")
            continue

        blocks.append({"type": "text", "text": text})

    return blocks, content_types, warnings

def _copilot_tool_request_content_blocks(
    value: object,
    *,
    context: str,
) -> tuple[list[dict[str, object]], list[str], list[str]]:
    if not isinstance(value, list):
        return [], [], []
    blocks: list[dict[str, object]] = []
    warnings: list[str] = []
    for item_index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            warnings.append(f"{context} item {item_index} is not an object")
            continue
        block: dict[str, object] = {
            "type": "tool_call",
            "native": item,
        }
        call_id = _string_or_none(item.get("toolCallId"))
        if call_id is not None:
            block["call_id"] = call_id
        tool_name = _string_or_none(item.get("name")) or _string_or_none(
            item.get("toolName")
        )
        if tool_name is not None:
            block["tool_name"] = tool_name
        arguments = item.get("arguments")
        if arguments is not None:
            block["arguments"] = arguments
        blocks.append(block)
    return blocks, ["tool_request"] * len(blocks), warnings

def _copilot_attachment_content_blocks(
    value: object,
    *,
    context: str,
) -> tuple[list[dict[str, object]], list[str], list[str]]:
    if not isinstance(value, list):
        return [], [], []
    blocks: list[dict[str, object]] = []
    warnings: list[str] = []
    for item_index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            blocks.append(
                {
                    "type": "unknown",
                    "native": {"value": item},
                }
            )
            warnings.append(f"{context} item {item_index} is not an object")
            continue
        mime_type = _copilot_attachment_mime_type(item)
        blocks.append(
            {
                "type": "image"
                if mime_type is not None and mime_type.startswith("image/")
                else "unknown",
                "native": item,
            }
        )
    return blocks, ["attachment"] * len(blocks), warnings

def _copilot_attachment_mime_type(attachment: dict[str, Any]) -> str | None:
    for key in ("mimeType", "mime_type", "contentType", "content_type"):
        mime_type = _string_or_none(attachment.get(key))
        if mime_type is not None:
            return mime_type
    return None

def _copilot_is_tool_request_only_message(raw_event: _CopilotRawEvent) -> bool:
    if raw_event.event_type != "assistant.message":
        return False
    tool_requests = raw_event.data.get("toolRequests")
    return isinstance(tool_requests, list) and bool(tool_requests)

def _copilot_message_native(
    raw_event: _CopilotRawEvent,
    *,
    content_types: list[str],
) -> dict[str, object]:
    native = _copilot_event_native(raw_event)
    native["role"] = _copilot_message_role(raw_event)
    if content_types:
        native["content_types"] = content_types

    transformed_content = _string_or_none(raw_event.data.get("transformedContent"))
    if transformed_content is not None:
        native["transformed_content"] = transformed_content

    _copy_present_fields(
        native,
        raw_event.data,
        _COPILOT_MESSAGE_NATIVE_FIELDS,
    )

    attachments = raw_event.data.get("attachments")
    if isinstance(attachments, list) and attachments:
        native["attachments"] = attachments

    supported_mime_types = raw_event.data.get("supportedNativeDocumentMimeTypes")
    if isinstance(supported_mime_types, list) and supported_mime_types:
        native["supported_native_document_mime_types"] = supported_mime_types

    return native

def _copilot_tool_invocations_from_raw_events(
    raw_events: _CopilotRawEvents,
) -> dict[str, object]:
    warnings: list[str] = []
    groups: dict[
        str,
        dict[str, list[_CopilotToolRequestRecord | _CopilotRawEvent]],
    ] = {}

    for raw_event in raw_events.events:
        if raw_event.event_type == "assistant.message":
            for request in _copilot_tool_request_records(
                raw_event,
                warnings=warnings,
            ):
                group = groups.setdefault(
                    request.call_id,
                    {
                        "tool_request": [],
                        "execution_start": [],
                        "execution_complete": [],
                    },
                )
                group["tool_request"].append(request)
            continue

        if raw_event.event_type not in {
            "tool.execution_start",
            "tool.execution_complete",
        }:
            continue

        call_id = _copilot_event_call_id(raw_event)
        if call_id is None:
            warnings.append(
                f"copilot tool event {raw_event.event_index} has no toolCallId"
            )
            continue

        group = groups.setdefault(
            call_id,
            {
                "tool_request": [],
                "execution_start": [],
                "execution_complete": [],
            },
        )
        if raw_event.event_type == "tool.execution_start":
            group["execution_start"].append(raw_event)
        else:
            group["execution_complete"].append(raw_event)

    tool_invocations: list[dict[str, object]] = []
    for call_id, group in sorted(groups.items(), key=_copilot_tool_group_order):
        invocation, group_warnings = _copilot_tool_invocation_from_group(
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

def _copilot_tool_request_records(
    raw_event: _CopilotRawEvent,
    *,
    warnings: list[str],
) -> list[_CopilotToolRequestRecord]:
    tool_requests = raw_event.data.get("toolRequests")
    if tool_requests is None:
        return []
    if not isinstance(tool_requests, list):
        warnings.append(
            f"copilot assistant message event {raw_event.event_index} has non-list toolRequests"
        )
        return []

    records: list[_CopilotToolRequestRecord] = []
    for request_index, item in enumerate(tool_requests, start=1):
        if not isinstance(item, dict):
            warnings.append(
                f"copilot assistant message event {raw_event.event_index} toolRequest {request_index} is not an object"
            )
            continue
        call_id = _copilot_tool_request_call_id(item)
        if call_id is None:
            warnings.append(
                f"copilot assistant message event {raw_event.event_index} toolRequest {request_index} has no toolCallId"
            )
            continue
        records.append(
            _CopilotToolRequestRecord(
                raw_event=raw_event,
                request_index=request_index,
                call_id=call_id,
                payload=item,
                source_refs=raw_event.source_refs,
            )
        )
    return records

def _copilot_tool_request_call_id(payload: dict[str, Any]) -> str | None:
    for key in ("toolCallId", "callId", "id"):
        call_id = _string_or_none(payload.get(key))
        if call_id is not None:
            return call_id
    return None

def _copilot_tool_group_order(
    item: tuple[
        str,
        dict[str, list[_CopilotToolRequestRecord | _CopilotRawEvent]],
    ],
) -> tuple[int, int]:
    _call_id, group = item
    positions = [
        _copilot_tool_evidence_position(evidence)
        for records in group.values()
        for evidence in records
    ]
    return min(positions) if positions else (0, 0)

def _copilot_tool_evidence_position(
    evidence: _CopilotToolRequestRecord | _CopilotRawEvent,
) -> tuple[int, int]:
    if isinstance(evidence, _CopilotToolRequestRecord):
        return (evidence.raw_event.event_index, evidence.request_index)
    return (evidence.event_index, 0)

def _copilot_tool_invocation_from_group(
    *,
    call_id: str,
    group: dict[str, list[_CopilotToolRequestRecord | _CopilotRawEvent]],
    index: int,
) -> tuple[dict[str, object], list[str]]:
    warnings: list[str] = []
    requests = [
        item
        for item in group["tool_request"]
        if isinstance(item, _CopilotToolRequestRecord)
    ]
    starts = [
        item
        for item in group["execution_start"]
        if isinstance(item, _CopilotRawEvent)
    ]
    completes = [
        item
        for item in group["execution_complete"]
        if isinstance(item, _CopilotRawEvent)
    ]

    _warn_about_tool_group_records(
        warnings=warnings,
        provider_label=_COPILOT_TOOL_GROUP_LABEL,
        call_id=call_id,
        kind="assistant toolRequest",
        records=requests,
    )
    _warn_about_tool_group_records(
        warnings=warnings,
        provider_label=_COPILOT_TOOL_GROUP_LABEL,
        call_id=call_id,
        kind="tool.execution_start",
        records=starts,
    )
    _warn_about_tool_group_records(
        warnings=warnings,
        provider_label=_COPILOT_TOOL_GROUP_LABEL,
        call_id=call_id,
        kind="tool.execution_complete",
        records=completes,
    )

    first_request = requests[0] if requests else None
    first_start = starts[0] if starts else None
    first_complete = completes[0] if completes else None

    invocation: dict[str, object] = {
        "tool_invocation_id": f"tool-invocation-{index}",
        "call_id": call_id,
        "tool_name": _copilot_tool_name(first_request, first_start, first_complete),
        "status": _copilot_tool_status(first_start, first_complete),
        "native": _copilot_tool_native(
            requests=requests,
            starts=starts,
            completes=completes,
        ),
    }

    started_at = _copilot_tool_started_at(first_request, first_start, first_complete)
    if started_at is not None:
        invocation["started_at"] = started_at
    ended_at = _string_or_none(
        first_complete.timestamp if first_complete is not None else None
    )
    if ended_at is not None:
        invocation["ended_at"] = ended_at

    tool_input = _copilot_tool_input(first_request, first_start)
    if tool_input:
        invocation["input"] = tool_input
    if first_complete is not None:
        output = _copilot_tool_output(first_complete)
        if output:
            invocation["output"] = output

    model = _copilot_tool_model(first_request, first_start, first_complete)
    if model is not None:
        invocation["model"] = model
    interaction_id = _copilot_tool_interaction_id(
        first_request,
        first_start,
        first_complete,
    )
    if interaction_id is not None:
        invocation["native"]["interaction_id"] = interaction_id
    turn_id = _copilot_tool_turn_id(first_request, first_start, first_complete)
    if turn_id is not None:
        invocation["turn_id"] = turn_id

    source_refs = _copilot_tool_source_refs(requests, starts, completes)
    if source_refs:
        invocation["source_refs"] = source_refs

    return invocation, warnings

_COPILOT_TOOL_GROUP_LABEL = "copilot toolCallId"

def _copilot_tool_name(
    request: _CopilotToolRequestRecord | None,
    start: _CopilotRawEvent | None,
    complete: _CopilotRawEvent | None,
) -> str:
    for value in (
        request.payload.get("name") if request is not None else None,
        request.payload.get("toolName") if request is not None else None,
        start.data.get("toolName") if start is not None else None,
        complete.data.get("toolName") if complete is not None else None,
    ):
        name = _string_or_none(value)
        if name is not None:
            return name
    return "unknown"

def _copilot_tool_status(
    start: _CopilotRawEvent | None,
    complete: _CopilotRawEvent | None,
) -> str:
    if complete is None:
        return "requested"
    success = complete.data.get("success")
    if success is False:
        return "failed"
    return "completed"

def _copilot_tool_native(
    *,
    requests: list[_CopilotToolRequestRecord],
    starts: list[_CopilotRawEvent],
    completes: list[_CopilotRawEvent],
) -> dict[str, object]:
    native: dict[str, object] = {
        "request_present": bool(requests),
        "execution_start_present": bool(starts),
        "execution_complete_present": bool(completes),
        "event_indices": {
            "tool_request": [
                {
                    "event_index": request.raw_event.event_index,
                    "request_index": request.request_index,
                }
                for request in requests
            ],
            "tool.execution_start": [event.event_index for event in starts],
            "tool.execution_complete": [event.event_index for event in completes],
        },
    }
    if requests:
        native["request"] = requests[0].payload
    if starts:
        native["execution_start"] = starts[0].data
    if completes:
        native["execution_complete"] = completes[0].data
    return native

def _copilot_tool_started_at(
    request: _CopilotToolRequestRecord | None,
    start: _CopilotRawEvent | None,
    complete: _CopilotRawEvent | None,
) -> str | None:
    for value in (
        start.timestamp if start is not None else None,
        request.raw_event.timestamp if request is not None else None,
        complete.timestamp if complete is not None else None,
    ):
        timestamp = _string_or_none(value)
        if timestamp is not None:
            return timestamp
    return None

def _copilot_tool_input(
    request: _CopilotToolRequestRecord | None,
    start: _CopilotRawEvent | None,
) -> dict[str, object]:
    tool_input: dict[str, object] = {}
    arguments = (
        request.payload.get("arguments") if request is not None else None
    )
    if arguments is None and start is not None:
        arguments = start.data.get("arguments")
    if arguments is None and start is not None:
        command = _string_or_none(start.data.get("command"))
        if command is not None:
            arguments = {"command": command}
    if arguments is not None:
        tool_input["arguments"] = arguments
    return tool_input

def _copilot_tool_output(event: _CopilotRawEvent) -> dict[str, object]:
    output: dict[str, object] = {}
    result = event.data.get("result")
    if result is None:
        result = event.data.get("output")
    if isinstance(result, dict):
        content = result.get("content")
        if content is None:
            content = result.get("text")
        if content is not None:
            output["content"] = content
        detailed_content = result.get("detailedContent")
        if detailed_content is not None:
            output["detailed_content"] = detailed_content
        error = result.get("error")
        if error is not None:
            output["error"] = error
        if not output:
            output["native_result"] = result
        return output

    if result is not None:
        output["content"] = result
    return output

def _copilot_tool_model(
    request: _CopilotToolRequestRecord | None,
    start: _CopilotRawEvent | None,
    complete: _CopilotRawEvent | None,
) -> str | None:
    for value in (
        complete.data.get("model") if complete is not None else None,
        start.data.get("model") if start is not None else None,
        request.payload.get("model") if request is not None else None,
    ):
        model = _string_or_none(value)
        if model is not None:
            return model
    return None

def _copilot_tool_interaction_id(
    request: _CopilotToolRequestRecord | None,
    start: _CopilotRawEvent | None,
    complete: _CopilotRawEvent | None,
) -> str | None:
    for value in (
        complete.data.get("interactionId") if complete is not None else None,
        start.data.get("interactionId") if start is not None else None,
        request.raw_event.data.get("interactionId") if request is not None else None,
        request.payload.get("interactionId") if request is not None else None,
    ):
        interaction_id = _string_or_none(value)
        if interaction_id is not None:
            return interaction_id
    return None

def _copilot_tool_turn_id(
    request: _CopilotToolRequestRecord | None,
    start: _CopilotRawEvent | None,
    complete: _CopilotRawEvent | None,
) -> str | None:
    for event in (
        start,
        complete,
        request.raw_event if request is not None else None,
    ):
        if event is None:
            continue
        turn_id = _copilot_event_turn_id(event)
        if turn_id is not None:
            return turn_id
    return None

def _copilot_tool_source_refs(
    requests: list[_CopilotToolRequestRecord],
    starts: list[_CopilotRawEvent],
    completes: list[_CopilotRawEvent],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for request in requests:
        refs.extend(request.source_refs)
    for event in [*starts, *completes]:
        refs.extend(event.source_refs)
    return _dedupe_dicts(refs)

def _copilot_model_runs_from_raw_events(
    raw_events: _CopilotRawEvents,
    *,
    messages: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
) -> dict[str, object]:
    warnings: list[str] = []
    start_groups: dict[str, list[_CopilotRawEvent]] = {}
    end_groups: dict[str, list[_CopilotRawEvent]] = {}
    event_by_id = {
        event.event_id: event
        for event in raw_events.events
        if event.event_id is not None
    }

    for raw_event in raw_events.events:
        if raw_event.event_type not in {
            "assistant.turn_start",
            "assistant.turn_end",
        }:
            continue
        if _copilot_event_turn_id(raw_event) is None:
            warnings.append(
                f"copilot {raw_event.event_type} event {raw_event.event_index} has no turnId"
            )
        group_key = _copilot_turn_group_key(raw_event)
        if raw_event.event_type == "assistant.turn_start":
            start_groups.setdefault(group_key, []).append(raw_event)
        else:
            end_groups.setdefault(group_key, []).append(raw_event)

    shutdown_event = _copilot_shutdown_event(raw_events)
    ordered_starts = sorted(
        start_groups.items(),
        key=lambda item: item[1][0].event_index if item[1] else 0,
    )

    model_runs: list[dict[str, object]] = []
    for group_index, (group_key, starts) in enumerate(ordered_starts, start=1):
        if not starts:
            continue
        if len(starts) > 1:
            warnings.append(
                f"copilot turn group {group_key} has {len(starts)} assistant.turn_start events; using first"
            )
        start_event = starts[0]
        end_events = [
            event
            for event in end_groups.get(group_key, [])
            if event.event_index >= start_event.event_index
        ]
        if len(end_events) > 1:
            warnings.append(
                f"copilot turn group {group_key} has {len(end_events)} assistant.turn_end events; using first"
            )
        end_event = end_events[0] if end_events else None
        next_start_event = (
            ordered_starts[group_index][1][0]
            if group_index < len(ordered_starts)
            else None
        )
        model_run = _copilot_model_run_from_turn(
            raw_events=raw_events,
            start_event=start_event,
            end_event=end_event,
            next_start_event=next_start_event,
            shutdown_event=shutdown_event,
            messages=messages,
            tool_invocations=tool_invocations,
            events=events,
            event_by_id=event_by_id,
            index=len(model_runs) + 1,
        )
        model_runs.append(model_run)

    for group_key, ends in sorted(
        end_groups.items(),
        key=lambda item: item[1][0].event_index if item[1] else 0,
    ):
        if group_key not in start_groups and ends:
            warnings.append(
                f"copilot turn group {group_key} has assistant.turn_end without assistant.turn_start"
            )

    return {
        "model_runs": model_runs,
        "warnings": warnings,
    }

def _copilot_turn_group_key(raw_event: _CopilotRawEvent) -> str:
    return _copilot_event_turn_id(raw_event) or f"event-index-{raw_event.event_index}"

def _copilot_shutdown_event(
    raw_events: _CopilotRawEvents,
) -> _CopilotRawEvent | None:
    for raw_event in reversed(raw_events.events):
        if raw_event.event_type == "session.shutdown":
            return raw_event
    return None

def _copilot_model_run_from_turn(
    *,
    raw_events: _CopilotRawEvents,
    start_event: _CopilotRawEvent,
    end_event: _CopilotRawEvent | None,
    next_start_event: _CopilotRawEvent | None,
    shutdown_event: _CopilotRawEvent | None,
    messages: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
    event_by_id: dict[str, _CopilotRawEvent],
    index: int,
) -> dict[str, object]:
    span_end_index = _copilot_turn_span_end_index(
        start_event=start_event,
        end_event=end_event,
        next_start_event=next_start_event,
        total_events=len(raw_events.events),
    )
    span_end_event = raw_events.events[span_end_index - 1]
    model, model_source = _copilot_model_for_turn(
        raw_events,
        turn_start_event=start_event,
    )
    native: dict[str, object] = {
        "turn_start_present": True,
        "turn_end_present": end_event is not None,
        "turn_start_event_index": start_event.event_index,
        "span_end_event_index": span_end_index,
    }
    if model_source is not None:
        native["model_source"] = model_source
    if start_event.event_id is not None:
        native["turn_start_event_id"] = start_event.event_id
    if end_event is not None:
        native["turn_end_event_index"] = end_event.event_index
        if end_event.event_id is not None:
            native["turn_end_event_id"] = end_event.event_id

    model_run: dict[str, object] = {
        "model_run_id": f"model-run-{index}",
        "provider": "copilot-cli",
        "status": _copilot_model_run_status(
            start_event=start_event,
            end_event=end_event,
            next_start_event=next_start_event,
            shutdown_event=shutdown_event,
        ),
        "native": native,
    }
    turn_id = _copilot_event_turn_id(start_event)
    if turn_id is not None:
        model_run["turn_id"] = turn_id
    if start_event.timestamp is not None:
        model_run["started_at"] = start_event.timestamp
    if end_event is not None and end_event.timestamp is not None:
        model_run["ended_at"] = end_event.timestamp
    if model is not None:
        model_run["model"] = model

    interaction_id = _copilot_model_run_interaction_id(
        raw_events,
        start_event=start_event,
        end_event=end_event,
        span_end_index=span_end_index,
    )
    if interaction_id is not None:
        native["interaction_id"] = interaction_id

    output_tokens = _copilot_model_run_output_tokens(
        raw_events,
        start_index=start_event.event_index,
        end_index=span_end_index,
    )
    if output_tokens:
        model_run["output_tokens"] = output_tokens

    source_refs = _copilot_model_run_source_refs(
        start_event=start_event,
        end_event=end_event,
        span_end_event=span_end_event,
    )
    if source_refs:
        model_run["source_refs"] = source_refs

    message_refs = _copilot_model_run_message_refs(
        messages,
        start_event=start_event,
        span_end_index=span_end_index,
        event_by_id=event_by_id,
    )
    if message_refs:
        model_run["message_refs"] = message_refs

    tool_refs = _copilot_model_run_tool_refs(
        tool_invocations,
        start_index=start_event.event_index,
        end_index=span_end_index,
    )
    if tool_refs:
        model_run["tool_invocation_refs"] = tool_refs

    event_refs = _copilot_model_run_event_refs(
        events,
        start_index=start_event.event_index,
        end_index=span_end_index,
    )
    if event_refs:
        model_run["event_refs"] = event_refs

    reasoning_trace = _copilot_model_run_reasoning_trace(
        raw_events,
        start_index=start_event.event_index,
        end_index=span_end_index,
        model_run_index=index,
    )
    if reasoning_trace:
        model_run["reasoning_trace"] = reasoning_trace

    return model_run

def _copilot_turn_span_end_index(
    *,
    start_event: _CopilotRawEvent,
    end_event: _CopilotRawEvent | None,
    next_start_event: _CopilotRawEvent | None,
    total_events: int,
) -> int:
    if end_event is not None:
        return end_event.event_index
    if next_start_event is not None:
        return max(start_event.event_index, next_start_event.event_index - 1)
    return max(start_event.event_index, total_events)

def _copilot_model_run_status(
    *,
    start_event: _CopilotRawEvent,
    end_event: _CopilotRawEvent | None,
    next_start_event: _CopilotRawEvent | None,
    shutdown_event: _CopilotRawEvent | None,
) -> str:
    if end_event is not None:
        return "completed"
    if next_start_event is not None:
        return "unknown"
    if (
        shutdown_event is not None
        and shutdown_event.event_index > start_event.event_index
    ):
        return "unknown"
    return "running"

def _copilot_model_for_turn(
    raw_events: _CopilotRawEvents,
    *,
    turn_start_event: _CopilotRawEvent,
) -> tuple[str | None, str | None]:
    for raw_event in reversed(raw_events.events[: turn_start_event.event_index]):
        if raw_event.event_type != "session.model_change":
            continue
        model = _string_or_none(raw_event.data.get("newModel"))
        if model is not None:
            return model, "session.model_change.newModel"

    shutdown_event = _copilot_shutdown_event(raw_events)
    if shutdown_event is None:
        return None, None
    model = _string_or_none(shutdown_event.data.get("currentModel"))
    if model is not None:
        return model, "session.shutdown.currentModel"
    return None, None

def _copilot_model_run_interaction_id(
    raw_events: _CopilotRawEvents,
    *,
    start_event: _CopilotRawEvent,
    end_event: _CopilotRawEvent | None,
    span_end_index: int,
) -> str | None:
    for value in (
        start_event.data.get("interactionId"),
        end_event.data.get("interactionId") if end_event is not None else None,
    ):
        interaction_id = _string_or_none(value)
        if interaction_id is not None:
            return interaction_id

    for raw_event in raw_events.events[start_event.event_index - 1 : span_end_index]:
        interaction_id = _string_or_none(raw_event.data.get("interactionId"))
        if interaction_id is not None:
            return interaction_id
    return None

def _copilot_model_run_output_tokens(
    raw_events: _CopilotRawEvents,
    *,
    start_index: int,
    end_index: int,
) -> int:
    output_tokens = 0
    for raw_event in raw_events.events[start_index - 1 : end_index]:
        if raw_event.event_type != "assistant.message":
            continue
        output_tokens += _int_or_zero(raw_event.data.get("outputTokens"))
    return output_tokens

def _copilot_model_run_source_refs(
    *,
    start_event: _CopilotRawEvent,
    end_event: _CopilotRawEvent | None,
    span_end_event: _CopilotRawEvent,
) -> list[dict[str, object]]:
    refs = [*start_event.source_refs]
    if end_event is not None:
        refs.extend(end_event.source_refs)
    elif span_end_event.event_index != start_event.event_index:
        refs.extend(span_end_event.source_refs)
    return _dedupe_dicts(refs)

def _copilot_model_run_message_refs(
    messages: list[dict[str, object]],
    *,
    start_event: _CopilotRawEvent,
    span_end_index: int,
    event_by_id: dict[str, _CopilotRawEvent],
) -> list[str]:
    refs: list[str] = []
    direct_parent_id = _copilot_direct_parent_message_ref(
        messages,
        start_event=start_event,
        event_by_id=event_by_id,
    )
    if direct_parent_id is not None:
        refs.append(direct_parent_id)

    for message in messages:
        message_id = _string_or_none(message.get("message_id"))
        if message_id is None:
            continue
        event_index = _copilot_record_event_index(message)
        if event_index is None:
            continue
        if start_event.event_index <= event_index <= span_end_index and message_id not in refs:
            refs.append(message_id)
    return refs

def _copilot_direct_parent_message_ref(
    messages: list[dict[str, object]],
    *,
    start_event: _CopilotRawEvent,
    event_by_id: dict[str, _CopilotRawEvent],
) -> str | None:
    parent_id = start_event.parent_id
    if parent_id is None:
        return None
    parent_event = event_by_id.get(parent_id)
    if parent_event is None or parent_event.event_type not in {
        "system.message",
        "user.message",
        "assistant.message",
    }:
        return None
    for message in messages:
        message_id = _string_or_none(message.get("message_id"))
        raw_event_id = _copilot_record_event_id(message)
        if message_id is not None and raw_event_id == parent_id:
            return message_id
    return None

def _copilot_model_run_tool_refs(
    tool_invocations: list[dict[str, object]],
    *,
    start_index: int,
    end_index: int,
) -> list[str]:
    refs: list[str] = []
    for invocation in tool_invocations:
        invocation_id = _string_or_none(invocation.get("tool_invocation_id"))
        if invocation_id is None:
            continue
        event_indices = _source_ref_event_indices(invocation.get("source_refs"))
        if any(start_index <= event_index <= end_index for event_index in event_indices):
            refs.append(invocation_id)
    return refs

def _copilot_model_run_event_refs(
    events: list[dict[str, object]],
    *,
    start_index: int,
    end_index: int,
) -> list[str]:
    refs: list[str] = []
    for event in events:
        event_id = _string_or_none(event.get("event_id"))
        if event_id is None:
            continue
        event_index = _copilot_record_event_index(event)
        if event_index is None:
            continue
        if start_index <= event_index <= end_index:
            refs.append(event_id)
    return refs

def _copilot_model_run_reasoning_trace(
    raw_events: _CopilotRawEvents,
    *,
    start_index: int,
    end_index: int,
    model_run_index: int,
) -> list[dict[str, object]]:
    reasoning_trace: list[dict[str, object]] = []
    for raw_event in raw_events.events[start_index - 1 : end_index]:
        if raw_event.event_type != "assistant.message":
            continue
        reasoning_trace.extend(
            _copilot_reasoning_entries_from_event(
                raw_event,
                model_run_index=model_run_index,
                offset=len(reasoning_trace),
            )
        )
    return reasoning_trace

def _copilot_reasoning_entries_from_event(
    raw_event: _CopilotRawEvent,
    *,
    model_run_index: int,
    offset: int,
) -> list[dict[str, object]]:
    reasoning_trace: list[dict[str, object]] = []
    for source_key, visibility in (
        ("reasoningText", "visible"),
        ("reasoningOpaque", "opaque"),
        ("encryptedContent", "encrypted"),
    ):
        value = _string_or_none(raw_event.data.get(source_key))
        if value is None:
            continue
        reasoning: dict[str, object] = {
            "reasoning_id": f"reasoning-{model_run_index}-{offset + len(reasoning_trace) + 1}",
            "visibility": visibility,
            "content": value,
            "native": _copilot_reasoning_native(
                raw_event,
                reasoning_key=source_key,
            ),
        }
        _copilot_attach_event_provenance(reasoning, raw_event)
        reasoning_trace.append(reasoning)
    return reasoning_trace

def _copilot_reasoning_native(
    raw_event: _CopilotRawEvent,
    *,
    reasoning_key: str,
) -> dict[str, object]:
    native = _copilot_event_native(raw_event)
    native["reasoning_key"] = reasoning_key
    _copy_present_fields(
        native,
        raw_event.data,
        _COPILOT_REASONING_NATIVE_FIELDS,
    )
    return native

def _copilot_reasoning_attachment_warnings(
    *,
    raw_counts: dict[str, object],
    model_runs: list[dict[str, object]],
) -> list[str]:
    raw_reasoning_count = _int_or_zero(raw_counts.get("reasoning_evidence_count"))
    normalized_reasoning_count = _model_run_reasoning_count(model_runs)
    if raw_reasoning_count <= normalized_reasoning_count:
        return []
    return [
        "copilot reasoning evidence outside normalized turn spans is preserved in messages/events only: "
        f"raw={raw_reasoning_count} normalized={normalized_reasoning_count}"
    ]

def _copilot_usage_from_raw_events(
    raw_events: _CopilotRawEvents,
) -> dict[str, object]:
    warnings: list[str] = []
    shutdown_events = [
        raw_event
        for raw_event in raw_events.events
        if raw_event.event_type == "session.shutdown"
    ]
    if not shutdown_events:
        return {
            "usage": [],
            "warnings": warnings,
        }
    if len(shutdown_events) > 1:
        warnings.append(
            f"copilot raw events has {len(shutdown_events)} session.shutdown events; using last"
        )

    shutdown_event = shutdown_events[-1]
    model_metrics = shutdown_event.data.get("modelMetrics")
    if not isinstance(model_metrics, dict):
        return {
            "usage": [],
            "warnings": warnings,
        }

    entry_result = _copilot_model_metric_entries(model_metrics)
    entries = entry_result["entries"]
    warnings.extend(_string_list(entry_result["warnings"]))

    usage: list[dict[str, object]] = []
    for model_name, entry in entries:
        usage.append(
            _copilot_usage_record_from_model_metrics(
                shutdown_event=shutdown_event,
                model_name=model_name,
                entry=entry,
                index=len(usage) + 1,
            )
        )

    return {
        "usage": usage,
        "warnings": warnings,
    }

def _copilot_model_metric_entries(
    model_metrics: dict[str, Any],
) -> dict[str, object]:
    warnings: list[str] = []
    entries: list[tuple[str, dict[str, Any]]] = []
    flat_usage_keys = {
        "inputTokens",
        "outputTokens",
        "cacheReadTokens",
        "cacheWriteTokens",
        "reasoningTokens",
    }

    if any(key in flat_usage_keys for key in model_metrics):
        warnings.append(
            "copilot session.shutdown modelMetrics has flat shape; usage projection requires per-model entries"
        )
        return {
            "entries": entries,
            "warnings": warnings,
        }

    for model_name, value in sorted(model_metrics.items()):
        if not isinstance(model_name, str):
            warnings.append(
                "copilot session.shutdown modelMetrics has non-string model key"
            )
            continue
        if not isinstance(value, dict):
            warnings.append(
                f"copilot session.shutdown modelMetrics entry {model_name} is not an object"
            )
            continue
        if not isinstance(value.get("usage"), dict) and not isinstance(
            value.get("requests"),
            dict,
        ):
            warnings.append(
                f"copilot session.shutdown modelMetrics entry {model_name} has unsupported shape"
            )
            continue
        entries.append((model_name, value))

    return {
        "entries": entries,
        "warnings": warnings,
    }

def _copilot_usage_record_from_model_metrics(
    *,
    shutdown_event: _CopilotRawEvent,
    model_name: str,
    entry: dict[str, Any],
    index: int,
) -> dict[str, object]:
    requests = entry.get("requests")
    if not isinstance(requests, dict):
        requests = {}
    usage_metrics = entry.get("usage")
    if not isinstance(usage_metrics, dict):
        usage_metrics = {}

    usage: dict[str, object] = {
        "usage_id": f"usage-{index}",
        "scope": "session",
        "provider": "copilot-cli",
        "model": model_name,
        "native": _copilot_usage_native(
            shutdown_event=shutdown_event,
            model_name=model_name,
            entry=entry,
        ),
    }
    for source_key, target_key in (
        ("inputTokens", "input_tokens"),
        ("outputTokens", "output_tokens"),
        ("cacheReadTokens", "cache_read_tokens"),
        ("cacheWriteTokens", "cache_write_tokens"),
        ("reasoningTokens", "reasoning_tokens"),
    ):
        value = _int_or_none(usage_metrics.get(source_key))
        if value is not None:
            usage[target_key] = value

    request_count = _int_or_none(requests.get("count"))
    if request_count is not None:
        usage["request_count"] = request_count

    billing_cost = _int_or_none(requests.get("cost"))
    if billing_cost is not None:
        usage["provider_billing_units"] = {
            "kind": "copilot_premium_request_cost",
            "value": billing_cost,
        }

    if shutdown_event.source_refs:
        usage["source_refs"] = shutdown_event.source_refs

    return usage

def _copilot_usage_native(
    *,
    shutdown_event: _CopilotRawEvent,
    model_name: str,
    entry: dict[str, Any],
) -> dict[str, object]:
    native = _copilot_event_native(shutdown_event)
    native["model_metrics_key"] = model_name
    native["model_metrics_entry"] = entry
    _copy_present_fields(
        native,
        shutdown_event.data,
        _COPILOT_USAGE_NATIVE_FIELDS,
    )

    session_token_counters: dict[str, object] = {}
    for source_key, native_key in (
        ("currentTokens", "current_tokens"),
        ("systemTokens", "system_tokens"),
        ("conversationTokens", "conversation_tokens"),
        ("toolDefinitionsTokens", "tool_definitions_tokens"),
    ):
        value = _int_or_none(shutdown_event.data.get(source_key))
        if value is not None:
            session_token_counters[native_key] = value
    if session_token_counters:
        native["session_token_counters"] = session_token_counters

    code_changes = shutdown_event.data.get("codeChanges")
    if isinstance(code_changes, dict) and code_changes:
        native["code_changes"] = code_changes

    return native

def _copilot_raw_event_counts(raw_events: _CopilotRawEvents) -> dict[str, object]:
    event_types: dict[str, int] = {}
    reasoning_evidence_count = 0
    usage_evidence_count = 0
    cost_evidence_count = 0
    tool_request_count = 0

    for event in raw_events.events:
        if event.event_type is not None:
            event_types[event.event_type] = event_types.get(event.event_type, 0) + 1
        reasoning_evidence_count += _copilot_event_reasoning_evidence_count(event)
        if _copilot_event_has_usage_evidence(event):
            usage_evidence_count += 1
        if _copilot_event_has_cost_like_evidence(event):
            cost_evidence_count += 1
        tool_request_count += _copilot_event_tool_request_count(event)

    return {
        "records": len(raw_events.events),
        "event_types": _sorted_count_dict(event_types),
        "parse_warning_count": len(raw_events.warnings),
        "reasoning_evidence_count": reasoning_evidence_count,
        "usage_evidence_count": usage_evidence_count,
        "cost_evidence_count": cost_evidence_count,
        "tool_request_count": tool_request_count,
    }

def _copilot_event_has_reasoning_evidence(event: _CopilotRawEvent) -> bool:
    return _copilot_event_reasoning_evidence_count(event) > 0

def _copilot_event_reasoning_evidence_count(event: _CopilotRawEvent) -> int:
    if event.event_type != "assistant.message":
        return 0
    count = 0
    for key in ("reasoningText", "reasoningOpaque", "encryptedContent"):
        if _string_or_none(event.data.get(key)) is not None:
            count += 1
    return count

def _copilot_event_has_usage_evidence(event: _CopilotRawEvent) -> bool:
    if event.event_type == "assistant.message" and _int_or_zero(
        event.data.get("outputTokens")
    ):
        return True
    if event.event_type != "session.shutdown":
        return False
    if isinstance(event.data.get("modelMetrics"), dict):
        return True
    return any(
        _int_or_zero(event.data.get(key))
        for key in (
            "currentTokens",
            "systemTokens",
            "conversationTokens",
            "toolDefinitionsTokens",
        )
    )

def _copilot_event_has_cost_like_evidence(event: _CopilotRawEvent) -> bool:
    if event.event_type != "session.shutdown":
        return False
    if _int_or_zero(event.data.get("totalPremiumRequests")):
        return True
    model_metrics = event.data.get("modelMetrics")
    if not isinstance(model_metrics, dict):
        return False
    for value in model_metrics.values():
        if not isinstance(value, dict):
            continue
        requests = value.get("requests")
        if isinstance(requests, dict) and _int_or_zero(requests.get("cost")):
            return True
    return False

def _copilot_event_tool_request_count(event: _CopilotRawEvent) -> int:
    if event.event_type != "assistant.message":
        return 0
    tool_requests = event.data.get("toolRequests")
    if not isinstance(tool_requests, list):
        return 0
    return len(tool_requests)

def _copilot_normalization_metadata(
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
        "coverage": _copilot_normalization_coverage(
            raw_counts=raw_counts,
            messages=messages,
            model_runs=model_runs,
            tool_invocations=tool_invocations,
            events=events,
            usage=usage,
        ),
        "deferred_concepts": deferred_concepts,
    }

def _copilot_normalization_coverage(
    *,
    raw_counts: dict[str, object],
    messages: list[dict[str, object]],
    model_runs: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    events: list[dict[str, object]],
    usage: list[dict[str, object]],
) -> dict[str, object]:
    event_types = _count_payload(raw_counts.get("event_types"))
    reasoning_evidence_count = _int_or_zero(raw_counts.get("reasoning_evidence_count"))
    usage_evidence_count = _int_or_zero(raw_counts.get("usage_evidence_count"))
    cost_evidence_count = _int_or_zero(raw_counts.get("cost_evidence_count"))
    tool_request_count = _int_or_zero(raw_counts.get("tool_request_count"))
    reasoning_count = _model_run_reasoning_count(model_runs)
    cost_normalized_count = _copilot_usage_billing_count(usage)
    return {
        "messages": {
            "status": _coverage_status(len(messages)),
            "raw_message_event_count": (
                event_types.get("system.message", 0)
                + event_types.get("user.message", 0)
                + event_types.get("assistant.message", 0)
            ),
            "normalized_count": len(messages),
        },
        "model_runs": {
            "status": _coverage_status(len(model_runs)),
            "raw_turn_start_count": event_types.get("assistant.turn_start", 0),
            "raw_turn_end_count": event_types.get("assistant.turn_end", 0),
            "normalized_count": len(model_runs),
        },
        "tool_invocations": {
            "status": _coverage_status(len(tool_invocations)),
            "raw_tool_request_count": tool_request_count,
            "raw_tool_execution_start_count": event_types.get(
                "tool.execution_start",
                0,
            ),
            "raw_tool_execution_complete_count": event_types.get(
                "tool.execution_complete",
                0,
            ),
            "normalized_count": len(tool_invocations),
        },
        "events": {
            "status": _coverage_status(len(events)),
            "raw_count": _int_or_zero(raw_counts.get("records")),
            "normalized_count": len(events),
        },
        "reasoning": {
            "status": _coverage_status(reasoning_count),
            "raw_evidence_count": reasoning_evidence_count,
            "normalized_count": reasoning_count,
        },
        "usage": {
            "status": _coverage_status(len(usage)),
            "raw_evidence_count": usage_evidence_count,
            "normalized_count": len(usage),
        },
        "cost": {
            "status": (
                "normalized"
                if cost_normalized_count
                else "event_only" if cost_evidence_count else "no_raw_evidence"
            ),
            "raw_evidence_count": cost_evidence_count,
            "normalized_count": cost_normalized_count,
        },
    }

def _copilot_residual_unsupported_concepts(
    *,
    raw_counts: dict[str, object],
    usage: list[dict[str, object]],
) -> list[str]:
    unsupported: list[str] = []
    if _int_or_zero(raw_counts.get("usage_evidence_count")) and not usage:
        unsupported.append("usage")
    if (
        _int_or_zero(raw_counts.get("cost_evidence_count"))
        and not _copilot_usage_billing_count(usage)
    ):
        unsupported.append("cost")
    return unsupported

def _copilot_usage_billing_count(usage: list[dict[str, object]]) -> int:
    count = 0
    for item in usage:
        provider_billing_units = item.get("provider_billing_units")
        if isinstance(provider_billing_units, dict):
            count += 1
    return count

def _load_copilot_raw_events(
    path: Path,
    *,
    source_ref_id: str | None,
) -> _CopilotRawEvents:
    events: list[_CopilotRawEvent] = []
    warnings: list[str] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            event_index = len(events) + 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                warnings.append(
                    f"copilot raw events line {line_number} is invalid json: {exc.msg}"
                )
                continue
            if not isinstance(obj, dict):
                warnings.append(
                    f"copilot raw events line {line_number} is not a json object"
                )
                continue

            data = obj.get("data")
            if not isinstance(data, dict):
                data = {}

            source_refs: list[dict[str, object]] = []
            if source_ref_id is not None:
                source_refs.append(
                    {
                        "source_ref_id": source_ref_id,
                        "event_index": event_index,
                        "line": line_number,
                    }
                )

            events.append(
                _CopilotRawEvent(
                    event_index=event_index,
                    line=line_number,
                    event_id=_string_or_none(obj.get("id")),
                    parent_id=_string_or_none(obj.get("parentId")),
                    timestamp=_string_or_none(obj.get("timestamp")),
                    event_type=_string_or_none(obj.get("type")),
                    data=data,
                    source_refs=source_refs,
                )
            )
    return _CopilotRawEvents(
        path=path,
        source_ref_id=source_ref_id,
        events=events,
        warnings=warnings,
    )
