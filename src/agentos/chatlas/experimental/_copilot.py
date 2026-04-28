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
class _CopilotToolRequestEvent:
    event: dict[str, object]
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

    event_result = _copilot_events_from_raw_events(
        raw_events,
        tool_invocation_refs_by_call_id=None,
    )
    events = _dict_list(event_result["events"])
    message_result = _copilot_messages_from_events(events)
    messages = _dict_list(message_result["messages"])
    tool_result = _copilot_tool_invocations_from_events(events)
    tool_invocations = _dict_list(tool_result["tool_invocations"])
    _attach_tool_invocation_refs_to_events(
        events,
        tool_invocations=tool_invocations,
    )
    _attach_event_refs_to_tool_invocations(
        tool_invocations,
        events=events,
    )
    model_run_result = _copilot_model_runs_from_events(
        events,
        messages=messages,
        tool_invocations=tool_invocations,
    )
    model_runs = _dict_list(model_run_result["model_runs"])
    usage_result = _copilot_usage_from_events(events)
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
            "copilot raw events semantic events normalized from events.jsonl: "
            f"{len(events)} events"
        )
    if messages:
        warnings.append(
            "copilot raw events messages projected from canonical events: "
            f"{len(messages)} messages"
        )
    if tool_invocations:
        warnings.append(
            "copilot raw events tool invocations projected from canonical events by toolCallId: "
            f"{len(tool_invocations)} invocations"
        )
    if model_runs:
        warnings.append(
            "copilot raw events model runs projected from canonical events: "
            f"{len(model_runs)} runs"
        )
    if usage:
        warnings.append(
            "copilot raw events usage projected from canonical usage events: "
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
        _copilot_append_raw_event_semantic_events(
            event_builder=event_builder,
            raw_event=raw_event,
            interaction_ref=interaction_ref,
            tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id or {},
            warnings=warnings,
        )

    return {
        "events": event_builder.events,
        "warnings": warnings,
    }

def _copilot_append_raw_event_semantic_events(
    *,
    event_builder: _SemanticEventBuilder,
    raw_event: _CopilotRawEvent,
    interaction_ref: str,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> None:
    event_type = raw_event.event_type
    if event_type == "session.start":
        _copilot_append_session_start_event(
            event_builder=event_builder,
            raw_event=raw_event,
            interaction_ref=interaction_ref,
        )
        return
    if event_type == "session.model_change":
        _copilot_append_model_change_event(
            event_builder=event_builder,
            raw_event=raw_event,
            interaction_ref=interaction_ref,
        )
        return
    if event_type == "system.message":
        _copilot_append_message_event(
            event_builder=event_builder,
            raw_event=raw_event,
            interaction_ref=interaction_ref,
            role=_string_or_none(raw_event.data.get("role")) or "system",
            kind="context",
            producer=_semantic_event_producer("system"),
            surfaces=_semantic_event_surfaces(
                transcript="hidden",
                model_input="visible",
            ),
            visibility="context",
        )
        return
    if event_type == "user.message":
        _copilot_append_message_event(
            event_builder=event_builder,
            raw_event=raw_event,
            interaction_ref=interaction_ref,
            role="user",
            kind="message",
            producer=_semantic_event_producer("user"),
            surfaces=_semantic_event_surfaces(
                transcript="visible",
                model_input="visible",
            ),
            visibility="conversation",
        )
        return
    if event_type == "assistant.turn_start":
        _copilot_append_run_event(
            event_builder=event_builder,
            raw_event=raw_event,
            interaction_ref=interaction_ref,
            kind="run.start",
        )
        return
    if event_type == "assistant.message":
        _copilot_append_assistant_message_semantic_events(
            event_builder=event_builder,
            raw_event=raw_event,
            interaction_ref=interaction_ref,
            warnings=warnings,
        )
        return
    if event_type == "tool.execution_start":
        _copilot_append_tool_progress_event(
            event_builder=event_builder,
            raw_event=raw_event,
            interaction_ref=interaction_ref,
            tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
            warnings=warnings,
        )
        return
    if event_type == "tool.execution_complete":
        _copilot_append_tool_result_event(
            event_builder=event_builder,
            raw_event=raw_event,
            interaction_ref=interaction_ref,
            tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
            warnings=warnings,
        )
        return
    if event_type == "assistant.turn_end":
        _copilot_append_run_event(
            event_builder=event_builder,
            raw_event=raw_event,
            interaction_ref=interaction_ref,
            kind="run.end",
        )
        return
    if event_type == "session.shutdown":
        _copilot_append_session_end_event(
            event_builder=event_builder,
            raw_event=raw_event,
            interaction_ref=interaction_ref,
        )
        if _copilot_shutdown_has_usage_payload(raw_event):
            _copilot_append_usage_event(
                event_builder=event_builder,
                raw_event=raw_event,
                interaction_ref=interaction_ref,
            )
        return

    _copilot_append_session_update_event(
        event_builder=event_builder,
        raw_event=raw_event,
        interaction_ref=interaction_ref,
    )

def _copilot_append_session_start_event(
    *,
    event_builder: _SemanticEventBuilder,
    raw_event: _CopilotRawEvent,
    interaction_ref: str,
) -> None:
    payload: dict[str, object] = {"update_type": "session.start"}
    session_id = _string_or_none(raw_event.data.get("sessionId"))
    if session_id is not None:
        payload["session_id"] = session_id
    producer = _string_or_none(raw_event.data.get("producer"))
    if producer is not None:
        payload["producer"] = producer
    event_builder.append(
        kind="session.start",
        producer=_semantic_event_producer("provider"),
        surfaces=_semantic_event_surfaces(transcript="hidden"),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=raw_event.timestamp,
        source_refs=raw_event.source_refs,
        legacy_type="copilot-cli.session.start",
        legacy_native=_copilot_event_native(raw_event),
    )

def _copilot_append_model_change_event(
    *,
    event_builder: _SemanticEventBuilder,
    raw_event: _CopilotRawEvent,
    interaction_ref: str,
) -> None:
    payload: dict[str, object] = {"update_type": "model_change"}
    model = _string_or_none(raw_event.data.get("newModel"))
    if model is not None:
        payload["model"] = model
        payload["new_model"] = model
    event_builder.append(
        kind="session.update",
        producer=_semantic_event_producer("provider"),
        surfaces=_semantic_event_surfaces(transcript="hidden"),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=raw_event.timestamp,
        source_refs=raw_event.source_refs,
        legacy_type="copilot-cli.session.model_change",
        legacy_native=_copilot_event_native(raw_event),
    )

def _copilot_append_message_event(
    *,
    event_builder: _SemanticEventBuilder,
    raw_event: _CopilotRawEvent,
    interaction_ref: str,
    role: str,
    kind: str,
    producer: dict[str, object],
    surfaces: dict[str, object],
    visibility: str,
) -> None:
    content, content_types, _warnings = _copilot_text_content_blocks(
        raw_event.data.get("content"),
        context=f"copilot message event {raw_event.event_index} content",
    )
    if not content:
        return
    payload: dict[str, object] = {
        "role": role,
        "visibility": visibility,
        "content": content,
    }
    output_tokens = _int_or_none(raw_event.data.get("outputTokens"))
    if output_tokens is not None:
        payload["output_tokens"] = output_tokens
    event_builder.append(
        kind=kind,
        producer=producer,
        surfaces=surfaces,
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=raw_event.timestamp,
        source_refs=raw_event.source_refs,
        legacy_type=f"copilot-cli.{raw_event.event_type or 'unknown'}",
        legacy_native=_copilot_message_event_native(
            raw_event,
            content_types=content_types,
        ),
    )

def _copilot_append_run_event(
    *,
    event_builder: _SemanticEventBuilder,
    raw_event: _CopilotRawEvent,
    interaction_ref: str,
    kind: str,
) -> None:
    payload: dict[str, object] = {}
    turn_id = _copilot_event_turn_id(raw_event)
    if turn_id is not None:
        payload["turn_id"] = turn_id
    interaction_id = _string_or_none(raw_event.data.get("interactionId"))
    if interaction_id is not None:
        payload["interaction_id"] = interaction_id
    event = event_builder.append(
        kind=kind,
        producer=_semantic_event_producer("assistant"),
        surfaces=_semantic_event_surfaces(transcript="hidden"),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=raw_event.timestamp,
        source_refs=raw_event.source_refs,
        outcome="ok" if kind == "run.end" else None,
        legacy_type=f"copilot-cli.{raw_event.event_type or 'unknown'}",
        legacy_native=_copilot_event_native(raw_event),
    )
    if turn_id is not None:
        event["turn_id"] = turn_id

def _copilot_append_assistant_message_semantic_events(
    *,
    event_builder: _SemanticEventBuilder,
    raw_event: _CopilotRawEvent,
    interaction_ref: str,
    warnings: list[str],
) -> None:
    _copilot_append_message_event(
        event_builder=event_builder,
        raw_event=raw_event,
        interaction_ref=interaction_ref,
        role="assistant",
        kind="message",
        producer=_semantic_event_producer("assistant"),
        surfaces=_semantic_event_surfaces(
            transcript="visible",
            model_input="visible",
        ),
        visibility="conversation",
    )

    for reasoning_key, visibility in (
        ("reasoningText", "visible"),
        ("reasoningOpaque", "opaque"),
        ("encryptedContent", "encrypted"),
    ):
        content = _string_or_none(raw_event.data.get(reasoning_key))
        if content is None:
            continue
        _copilot_append_reasoning_event(
            event_builder=event_builder,
            raw_event=raw_event,
            interaction_ref=interaction_ref,
            reasoning_key=reasoning_key,
            visibility=visibility,
            content=content,
        )

    tool_requests = raw_event.data.get("toolRequests")
    if tool_requests is None:
        return
    if not isinstance(tool_requests, list):
        warnings.append(
            f"copilot assistant message event {raw_event.event_index} has non-list toolRequests"
        )
        return
    for request_index, item in enumerate(tool_requests, start=1):
        if not isinstance(item, dict):
            warnings.append(
                f"copilot assistant message event {raw_event.event_index} toolRequest {request_index} is not an object"
            )
            continue
        _copilot_append_tool_call_event(
            event_builder=event_builder,
            raw_event=raw_event,
            interaction_ref=interaction_ref,
            request_index=request_index,
            request=item,
            warnings=warnings,
        )

def _copilot_append_reasoning_event(
    *,
    event_builder: _SemanticEventBuilder,
    raw_event: _CopilotRawEvent,
    interaction_ref: str,
    reasoning_key: str,
    visibility: str,
    content: str,
) -> None:
    event_builder.append(
        kind="reasoning",
        producer=_semantic_event_producer("assistant"),
        surfaces=_semantic_event_surfaces(transcript="hidden"),
        interaction_ref=interaction_ref,
        payload={
            "visibility": visibility,
            "content": content,
        },
        timestamp=raw_event.timestamp,
        source_refs=raw_event.source_refs,
        legacy_type="copilot-cli.reasoning",
        legacy_native=_copilot_reasoning_event_native(
            raw_event,
            reasoning_key=reasoning_key,
        ),
    )

def _copilot_append_tool_call_event(
    *,
    event_builder: _SemanticEventBuilder,
    raw_event: _CopilotRawEvent,
    interaction_ref: str,
    request_index: int,
    request: dict[str, Any],
    warnings: list[str],
) -> None:
    call_id = _copilot_tool_request_call_id(request)
    if call_id is None:
        warnings.append(
            f"copilot assistant message event {raw_event.event_index} toolRequest {request_index} has no toolCallId"
        )
        return
    payload = _copilot_tool_call_payload(
        call_id=call_id,
        request=request,
    )
    event_builder.append(
        kind="tool.call",
        producer=_semantic_event_producer("assistant"),
        surfaces=_semantic_event_surfaces(
            transcript="hidden",
            model_input="visible",
        ),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=raw_event.timestamp,
        source_refs=_copilot_tool_request_source_refs(
            raw_event,
            request_index=request_index,
        ),
        legacy_type="copilot-cli.assistant.tool_call",
        legacy_native=_copilot_tool_call_event_native(
            raw_event,
            request_index=request_index,
            request=request,
        ),
        extra={
            "call_id": call_id,
            "request_index": request_index,
        },
    )

def _copilot_append_tool_progress_event(
    *,
    event_builder: _SemanticEventBuilder,
    raw_event: _CopilotRawEvent,
    interaction_ref: str,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> None:
    call_id = _copilot_event_call_id(raw_event)
    payload = _copilot_tool_progress_payload(raw_event)
    if call_id is not None:
        payload["call_id"] = call_id
    event = event_builder.append(
        kind="tool.progress",
        producer=_semantic_event_producer(
            "tool",
            name=_string_or_none(raw_event.data.get("toolName")),
        ),
        surfaces=_semantic_event_surfaces(transcript="hidden"),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=raw_event.timestamp,
        source_refs=raw_event.source_refs,
        legacy_type="copilot-cli.tool.execution_start",
        legacy_native=_copilot_event_native(raw_event),
        extra={"call_id": call_id},
    )
    _copilot_attach_tool_invocation_ref_to_event(
        event,
        raw_event=raw_event,
        call_id=call_id,
        tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
        warnings=warnings,
    )

def _copilot_append_tool_result_event(
    *,
    event_builder: _SemanticEventBuilder,
    raw_event: _CopilotRawEvent,
    interaction_ref: str,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> None:
    call_id = _copilot_event_call_id(raw_event)
    payload = _copilot_tool_result_payload(raw_event)
    if call_id is not None:
        payload["call_id"] = call_id
    event = event_builder.append(
        kind="tool.result",
        producer=_semantic_event_producer(
            "tool",
            name=_string_or_none(raw_event.data.get("toolName")),
        ),
        surfaces=_semantic_event_surfaces(
            transcript="hidden",
            model_input="visible",
        ),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=raw_event.timestamp,
        source_refs=raw_event.source_refs,
        outcome=_copilot_tool_result_outcome(raw_event),
        legacy_type="copilot-cli.tool.execution_complete",
        legacy_native=_copilot_event_native(raw_event),
        extra={"call_id": call_id},
    )
    _copilot_attach_tool_invocation_ref_to_event(
        event,
        raw_event=raw_event,
        call_id=call_id,
        tool_invocation_refs_by_call_id=tool_invocation_refs_by_call_id,
        warnings=warnings,
    )

def _copilot_append_session_end_event(
    *,
    event_builder: _SemanticEventBuilder,
    raw_event: _CopilotRawEvent,
    interaction_ref: str,
) -> None:
    payload = _copilot_session_end_payload(raw_event)
    event_builder.append(
        kind="session.end",
        producer=_semantic_event_producer("provider"),
        surfaces=_semantic_event_surfaces(transcript="hidden"),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=raw_event.timestamp,
        source_refs=raw_event.source_refs,
        outcome="ok",
        legacy_type="copilot-cli.session.shutdown",
        legacy_native=_copilot_event_native(raw_event),
    )

def _copilot_append_usage_event(
    *,
    event_builder: _SemanticEventBuilder,
    raw_event: _CopilotRawEvent,
    interaction_ref: str,
) -> None:
    event_builder.append(
        kind="usage",
        producer=_semantic_event_producer("provider"),
        surfaces=_semantic_event_surfaces(transcript="hidden"),
        interaction_ref=interaction_ref,
        payload=_copilot_usage_event_payload(raw_event),
        timestamp=raw_event.timestamp,
        source_refs=raw_event.source_refs,
        legacy_type="copilot-cli.usage",
        legacy_native=_copilot_usage_event_native(raw_event),
    )

def _copilot_append_session_update_event(
    *,
    event_builder: _SemanticEventBuilder,
    raw_event: _CopilotRawEvent,
    interaction_ref: str,
) -> None:
    payload: dict[str, object] = {
        "event_type": raw_event.event_type or "unknown",
    }
    event_builder.append(
        kind="session.update",
        producer=_semantic_event_producer("provider"),
        surfaces=_semantic_event_surfaces(transcript="hidden"),
        interaction_ref=interaction_ref,
        payload=payload,
        timestamp=raw_event.timestamp,
        source_refs=raw_event.source_refs,
        legacy_type=f"copilot-cli.{raw_event.event_type or 'unknown'}",
        legacy_native=_copilot_event_native(raw_event),
    )

def _copilot_attach_tool_invocation_ref_to_event(
    event: dict[str, object],
    *,
    raw_event: _CopilotRawEvent,
    call_id: str | None,
    tool_invocation_refs_by_call_id: dict[str, str],
    warnings: list[str],
) -> None:
    if call_id is None:
        warnings.append(
            f"copilot tool event {raw_event.event_index} has no toolCallId"
        )
        return
    tool_invocation_ref = tool_invocation_refs_by_call_id.get(call_id)
    if tool_invocation_ref is not None:
        event["tool_invocation_ref"] = tool_invocation_ref

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

def _copilot_message_event_native(
    raw_event: _CopilotRawEvent,
    *,
    content_types: list[str],
) -> dict[str, object]:
    native = _copilot_event_native(raw_event)
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

def _copilot_reasoning_event_native(
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

def _copilot_tool_call_payload(
    *,
    call_id: str,
    request: dict[str, Any],
) -> dict[str, object]:
    payload: dict[str, object] = {"call_id": call_id}
    tool_name = _string_or_none(request.get("name")) or _string_or_none(
        request.get("toolName")
    )
    if tool_name is not None:
        payload["tool_name"] = tool_name
    arguments = request.get("arguments")
    if arguments is not None:
        payload["input"] = {"arguments": arguments}
    return payload

def _copilot_tool_request_source_refs(
    raw_event: _CopilotRawEvent,
    *,
    request_index: int,
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for source_ref in raw_event.source_refs:
        ref = dict(source_ref)
        ref["request_index"] = request_index
        refs.append(ref)
    return refs

def _copilot_tool_call_event_native(
    raw_event: _CopilotRawEvent,
    *,
    request_index: int,
    request: dict[str, Any],
) -> dict[str, object]:
    native = _copilot_event_native(raw_event)
    native["request_index"] = request_index
    native["tool_request"] = request
    _copy_present_fields(
        native,
        raw_event.data,
        _COPILOT_REASONING_NATIVE_FIELDS,
    )
    return native

def _copilot_tool_progress_payload(raw_event: _CopilotRawEvent) -> dict[str, object]:
    payload: dict[str, object] = {"phase": "start"}
    tool_name = _string_or_none(raw_event.data.get("toolName"))
    if tool_name is not None:
        payload["tool_name"] = tool_name
    arguments = raw_event.data.get("arguments")
    if arguments is not None:
        payload["input"] = {"arguments": arguments}
    interaction_id = _string_or_none(raw_event.data.get("interactionId"))
    if interaction_id is not None:
        payload["interaction_id"] = interaction_id
    return payload

def _copilot_tool_result_payload(raw_event: _CopilotRawEvent) -> dict[str, object]:
    payload: dict[str, object] = {}
    success = raw_event.data.get("success")
    if isinstance(success, bool):
        payload["success"] = success
    model = _string_or_none(raw_event.data.get("model"))
    if model is not None:
        payload["model"] = model
    interaction_id = _string_or_none(raw_event.data.get("interactionId"))
    if interaction_id is not None:
        payload["interaction_id"] = interaction_id
    output = _copilot_tool_output_from_payload(raw_event.data)
    if output:
        payload["output"] = output
    return payload

def _copilot_tool_output_from_payload(payload: dict[str, Any]) -> dict[str, object]:
    output: dict[str, object] = {}
    result = payload.get("result")
    if result is None:
        result = payload.get("output")
    if isinstance(result, dict):
        content = result.get("content")
        if content is None:
            content = result.get("text")
        if content is not None:
            output["content"] = content
        detailed_content = result.get("detailedContent")
        if detailed_content is None:
            detailed_content = result.get("detailed_content")
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

def _copilot_tool_result_outcome(raw_event: _CopilotRawEvent) -> str | None:
    success = raw_event.data.get("success")
    if success is True:
        return "ok"
    if success is False:
        return "error"
    return None

def _copilot_session_end_payload(raw_event: _CopilotRawEvent) -> dict[str, object]:
    payload: dict[str, object] = {"shutdown_type": "shutdown"}
    shutdown_type = _string_or_none(raw_event.data.get("shutdownType"))
    if shutdown_type is not None:
        payload["shutdown_type"] = shutdown_type
    current_model = _string_or_none(raw_event.data.get("currentModel"))
    if current_model is not None:
        payload["current_model"] = current_model
    return payload

def _copilot_shutdown_has_usage_payload(raw_event: _CopilotRawEvent) -> bool:
    if isinstance(raw_event.data.get("modelMetrics"), dict):
        return True
    return any(
        _int_or_none(raw_event.data.get(key)) is not None
        for key in (
            "currentTokens",
            "systemTokens",
            "conversationTokens",
            "toolDefinitionsTokens",
            "totalPremiumRequests",
        )
    )

def _copilot_usage_event_payload(raw_event: _CopilotRawEvent) -> dict[str, object]:
    payload: dict[str, object] = {
        "scope": "session",
        "provider": "copilot-cli",
    }
    model_metrics = raw_event.data.get("modelMetrics")
    if isinstance(model_metrics, dict):
        payload["model_metrics"] = model_metrics
    current_model = _string_or_none(raw_event.data.get("currentModel"))
    if current_model is not None:
        payload["current_model"] = current_model
    for source_key, target_key in (
        ("totalPremiumRequests", "total_premium_requests"),
        ("totalApiDurationMs", "total_api_duration_ms"),
        ("currentTokens", "current_tokens"),
        ("systemTokens", "system_tokens"),
        ("conversationTokens", "conversation_tokens"),
        ("toolDefinitionsTokens", "tool_definitions_tokens"),
    ):
        value = _int_or_none(raw_event.data.get(source_key))
        if value is not None:
            payload[target_key] = value
    code_changes = raw_event.data.get("codeChanges")
    if isinstance(code_changes, dict) and code_changes:
        payload["code_changes"] = code_changes
    return payload

def _copilot_usage_event_native(raw_event: _CopilotRawEvent) -> dict[str, object]:
    native = _copilot_event_native(raw_event)
    native["source_event_type"] = raw_event.event_type or "unknown"
    model_metrics = raw_event.data.get("modelMetrics")
    if isinstance(model_metrics, dict):
        native["model_metrics"] = model_metrics
    return native

def _copilot_event_turn_id(raw_event: _CopilotRawEvent) -> str | None:
    return _string_or_none(raw_event.data.get("turnId"))

def _copilot_event_call_id(raw_event: _CopilotRawEvent) -> str | None:
    return _string_or_none(raw_event.data.get("toolCallId"))

def _copilot_record_event_index(record: dict[str, object]) -> int | None:
    event_index = _record_native_int_field(record, "event_index")
    if event_index is not None:
        return event_index
    return _source_ref_first_event_index(record.get("source_refs"))

def _copilot_record_event_id(record: dict[str, object]) -> str | None:
    return _record_native_string_field(record, "event_id")

def _copilot_messages_from_events(
    events: list[dict[str, object]],
) -> dict[str, object]:
    return _project_messages_from_events(
        events,
        project_event=_copilot_message_from_event,
    )

def _copilot_message_from_event(
    event: dict[str, object],
    index: int,
) -> tuple[dict[str, object] | None, list[str]]:
    event_type = _copilot_projected_event_type(event)
    if event_type not in {
        "system.message",
        "user.message",
        "assistant.message",
    }:
        return None, []

    payload = _copilot_event_payload(event)
    role = _copilot_message_role_from_event_type(event_type, payload)
    content, content_types, warnings = _copilot_message_content_blocks_from_event(
        event,
    )

    if not content:
        if _copilot_is_tool_request_only_event(event):
            return None, warnings
        warnings.append(
            f"copilot message event {_copilot_projected_event_index(event)} has no readable content"
        )
        return None, warnings

    message: dict[str, object] = {
        "message_id": f"message-{index}",
        "role": role,
        "visibility": _copilot_message_visibility_from_event_type(event_type),
        "content": content,
        "native": _copilot_message_native_from_event(
            event,
            role=role,
            content_types=content_types,
        ),
    }
    _copy_event_provenance(message, event)
    return message, warnings

def _copilot_projected_event_type(event: dict[str, object]) -> str:
    event_type = _string_or_none(event.get("type")) or ""
    prefix = "copilot-cli."
    if event_type.startswith(prefix):
        return event_type[len(prefix):]
    return event_type or "unknown"

def _copilot_event_payload(event: dict[str, object]) -> dict[str, Any]:
    payload = event.get("payload")
    if isinstance(payload, dict):
        return dict(payload)
    return {}

def _copilot_projected_event_index(event: dict[str, object]) -> int:
    return (
        _record_native_int_field(event, "event_index")
        or _source_ref_first_event_index(event.get("source_refs"))
        or _int_or_none(event.get("sequence"))
        or 0
    )

def _copilot_message_role_from_event_type(
    event_type: str,
    payload: dict[str, Any],
) -> str:
    if event_type == "system.message":
        return _string_or_none(payload.get("role")) or "system"
    if event_type == "user.message":
        return "user"
    if event_type == "assistant.message":
        return "assistant"
    return "unknown"

def _copilot_message_visibility_from_event_type(event_type: str) -> str:
    if event_type == "system.message":
        return "context"
    if event_type in {"user.message", "assistant.message"}:
        return "conversation"
    return "unknown"

def _copilot_message_content_blocks_from_event(
    event: dict[str, object],
) -> tuple[list[dict[str, object]], list[str], list[str]]:
    payload = _copilot_event_payload(event)
    event_index = _copilot_projected_event_index(event)
    content_value = payload.get("content")
    if content_value is None:
        blocks, content_types, warnings = [], [], []
    else:
        blocks, content_types, warnings = _copilot_text_content_blocks(
            content_value,
            context=f"copilot message event {event_index} content",
        )
    tool_request_blocks, tool_request_types, tool_request_warnings = (
        _copilot_tool_request_content_blocks(
            payload.get("toolRequests"),
            context=f"copilot message event {event_index} toolRequests",
        )
    )
    attachment_blocks, attachment_types, attachment_warnings = (
        _copilot_attachment_content_blocks(
            payload.get("attachments"),
            context=f"copilot message event {event_index} attachments",
        )
    )
    return (
        [*blocks, *tool_request_blocks, *attachment_blocks],
        [*content_types, *tool_request_types, *attachment_types],
        [*warnings, *tool_request_warnings, *attachment_warnings],
    )

def _copilot_is_tool_request_only_event(event: dict[str, object]) -> bool:
    if _copilot_projected_event_type(event) != "assistant.message":
        return False
    tool_requests = _copilot_event_payload(event).get("toolRequests")
    return isinstance(tool_requests, list) and bool(tool_requests)

def _copilot_message_native_from_event(
    event: dict[str, object],
    *,
    role: str,
    content_types: list[str],
) -> dict[str, object]:
    payload = _copilot_event_payload(event)
    native = dict(_record_native_dict(event))
    native["role"] = role
    if content_types:
        native["content_types"] = content_types

    transformed_content = _string_or_none(payload.get("transformedContent"))
    if transformed_content is not None:
        native["transformed_content"] = transformed_content

    _copy_present_fields(
        native,
        payload,
        _COPILOT_MESSAGE_NATIVE_FIELDS,
    )

    attachments = payload.get("attachments")
    if isinstance(attachments, list) and attachments:
        native["attachments"] = attachments

    supported_mime_types = payload.get("supportedNativeDocumentMimeTypes")
    if isinstance(supported_mime_types, list) and supported_mime_types:
        native["supported_native_document_mime_types"] = supported_mime_types

    return native

def _copy_event_provenance(
    payload: dict[str, object],
    event: dict[str, object],
) -> None:
    timestamp = _string_or_none(event.get("timestamp"))
    if timestamp is not None:
        payload["timestamp"] = timestamp
    source_refs = _dict_list(event.get("source_refs"))
    if source_refs:
        payload["source_refs"] = source_refs

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

_COPILOT_TOOL_GROUP_LABEL = "copilot toolCallId"

def _copilot_tool_invocations_from_events(
    events: list[dict[str, object]],
) -> dict[str, object]:
    warnings: list[str] = []
    groups: dict[
        str,
        dict[str, list[_CopilotToolRequestEvent | dict[str, object]]],
    ] = {}

    for event in events:
        event_kind = _string_or_none(event.get("kind"))
        event_type = _copilot_projected_event_type(event)
        if event_kind == "tool.call":
            request = _copilot_tool_request_event_from_tool_call_event(
                event,
                warnings=warnings,
            )
            if request is None:
                continue
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

        if event_type == "assistant.message":
            for request in _copilot_tool_request_events(
                event,
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

        is_tool_progress = event_kind == "tool.progress" or (
            event_type == "tool.execution_start"
        )
        is_tool_result = event_kind == "tool.result" or (
            event_type == "tool.execution_complete"
        )
        if not is_tool_progress and not is_tool_result:
            continue

        call_id = _string_or_none(event.get("call_id")) or _string_or_none(
            _copilot_event_payload(event).get("call_id")
        ) or _string_or_none(
            _copilot_event_payload(event).get("toolCallId")
        )
        if call_id is None:
            warnings.append(
                f"copilot tool event {_copilot_projected_event_index(event)} has no toolCallId"
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
        if is_tool_progress:
            group["execution_start"].append(event)
        else:
            group["execution_complete"].append(event)

    tool_invocations: list[dict[str, object]] = []
    for call_id, group in sorted(groups.items(), key=_copilot_tool_event_group_order):
        invocation, group_warnings = _copilot_tool_invocation_from_event_group(
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

def _copilot_tool_request_event_from_tool_call_event(
    event: dict[str, object],
    *,
    warnings: list[str],
) -> _CopilotToolRequestEvent | None:
    payload = _copilot_event_payload(event)
    call_id = _string_or_none(event.get("call_id")) or _string_or_none(
        payload.get("call_id")
    )
    if call_id is None:
        warnings.append(
            f"copilot tool.call event {_copilot_projected_event_index(event)} has no call_id"
        )
        return None
    request_index = (
        _record_native_int_field(event, "request_index")
        or _int_or_none(event.get("request_index"))
        or 1
    )
    return _CopilotToolRequestEvent(
        event=event,
        request_index=request_index,
        call_id=call_id,
        payload=payload,
        source_refs=_dict_list(event.get("source_refs")),
    )

def _copilot_tool_request_events(
    event: dict[str, object],
    *,
    warnings: list[str],
) -> list[_CopilotToolRequestEvent]:
    payload = _copilot_event_payload(event)
    tool_requests = payload.get("toolRequests")
    if tool_requests is None:
        return []
    event_index = _copilot_projected_event_index(event)
    if not isinstance(tool_requests, list):
        warnings.append(
            f"copilot assistant message event {event_index} has non-list toolRequests"
        )
        return []

    records: list[_CopilotToolRequestEvent] = []
    for request_index, item in enumerate(tool_requests, start=1):
        if not isinstance(item, dict):
            warnings.append(
                f"copilot assistant message event {event_index} toolRequest {request_index} is not an object"
            )
            continue
        call_id = _copilot_tool_request_call_id(item)
        if call_id is None:
            warnings.append(
                f"copilot assistant message event {event_index} toolRequest {request_index} has no toolCallId"
            )
            continue
        records.append(
            _CopilotToolRequestEvent(
                event=event,
                request_index=request_index,
                call_id=call_id,
                payload=item,
                source_refs=_dict_list(event.get("source_refs")),
            )
        )
    return records

def _copilot_tool_event_group_order(
    item: tuple[
        str,
        dict[str, list[_CopilotToolRequestEvent | dict[str, object]]],
    ],
) -> tuple[int, int]:
    _call_id, group = item
    positions = [
        _copilot_tool_event_evidence_position(evidence)
        for records in group.values()
        for evidence in records
    ]
    return min(positions) if positions else (0, 0)

def _copilot_tool_event_evidence_position(
    evidence: _CopilotToolRequestEvent | dict[str, object],
) -> tuple[int, int]:
    if isinstance(evidence, _CopilotToolRequestEvent):
        return (_copilot_projected_event_index(evidence.event), evidence.request_index)
    return (_copilot_projected_event_index(evidence), 0)

def _copilot_tool_invocation_from_event_group(
    *,
    call_id: str,
    group: dict[str, list[_CopilotToolRequestEvent | dict[str, object]]],
    index: int,
) -> tuple[dict[str, object], list[str]]:
    warnings: list[str] = []
    requests = [
        item
        for item in group["tool_request"]
        if isinstance(item, _CopilotToolRequestEvent)
    ]
    starts = [
        item
        for item in group["execution_start"]
        if isinstance(item, dict)
    ]
    completes = [
        item
        for item in group["execution_complete"]
        if isinstance(item, dict)
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
        "tool_name": _copilot_tool_name_from_events(
            first_request,
            first_start,
            first_complete,
        ),
        "status": _copilot_tool_status_from_events(first_start, first_complete),
        "native": _copilot_tool_native_from_events(
            requests=requests,
            starts=starts,
            completes=completes,
        ),
    }

    started_at = _copilot_tool_started_at_from_events(
        first_request,
        first_start,
        first_complete,
    )
    if started_at is not None:
        invocation["started_at"] = started_at
    ended_at = _string_or_none(
        first_complete.get("timestamp") if first_complete is not None else None
    )
    if ended_at is not None:
        invocation["ended_at"] = ended_at

    tool_input = _copilot_tool_input_from_events(first_request, first_start)
    if tool_input:
        invocation["input"] = tool_input
    if first_complete is not None:
        output = _copilot_tool_output_from_event(first_complete)
        if output:
            invocation["output"] = output

    model = _copilot_tool_model_from_events(
        first_request,
        first_start,
        first_complete,
    )
    if model is not None:
        invocation["model"] = model
    interaction_id = _copilot_tool_interaction_id_from_events(
        first_request,
        first_start,
        first_complete,
    )
    if interaction_id is not None:
        invocation["native"]["interaction_id"] = interaction_id
    turn_id = _copilot_tool_turn_id_from_events(first_request, first_start, first_complete)
    if turn_id is not None:
        invocation["turn_id"] = turn_id

    source_refs = _copilot_tool_source_refs_from_events(requests, starts, completes)
    if source_refs:
        invocation["source_refs"] = source_refs

    return invocation, warnings

def _copilot_tool_name_from_events(
    request: _CopilotToolRequestEvent | None,
    start: dict[str, object] | None,
    complete: dict[str, object] | None,
) -> str:
    start_payload = _copilot_event_payload(start or {})
    complete_payload = _copilot_event_payload(complete or {})
    for value in (
        request.payload.get("tool_name") if request is not None else None,
        request.payload.get("name") if request is not None else None,
        request.payload.get("toolName") if request is not None else None,
        start_payload.get("tool_name"),
        start_payload.get("toolName"),
        complete_payload.get("tool_name"),
        complete_payload.get("toolName"),
    ):
        name = _string_or_none(value)
        if name is not None:
            return name
    return "unknown"

def _copilot_tool_status_from_events(
    start: dict[str, object] | None,
    complete: dict[str, object] | None,
) -> str:
    if complete is None:
        return "requested"
    outcome = _string_or_none(complete.get("outcome"))
    if outcome == "error":
        return "failed"
    if outcome == "ok":
        return "completed"
    success = _copilot_event_payload(complete).get("success")
    if success is False:
        return "failed"
    return "completed"

def _copilot_tool_native_from_events(
    *,
    requests: list[_CopilotToolRequestEvent],
    starts: list[dict[str, object]],
    completes: list[dict[str, object]],
) -> dict[str, object]:
    native: dict[str, object] = {
        "request_present": bool(requests),
        "execution_start_present": bool(starts),
        "execution_complete_present": bool(completes),
        "event_indices": {
            "tool_request": [
                {
                    "event_index": _copilot_projected_event_index(request.event),
                    "request_index": request.request_index,
                }
                for request in requests
            ],
            "tool.execution_start": [
                _copilot_projected_event_index(event) for event in starts
            ],
            "tool.execution_complete": [
                _copilot_projected_event_index(event) for event in completes
            ],
        },
    }
    if requests:
        native["request"] = requests[0].payload
    if starts:
        native["execution_start"] = _copilot_event_payload(starts[0])
    if completes:
        native["execution_complete"] = _copilot_event_payload(completes[0])
    return native

def _copilot_tool_started_at_from_events(
    request: _CopilotToolRequestEvent | None,
    start: dict[str, object] | None,
    complete: dict[str, object] | None,
) -> str | None:
    for value in (
        start.get("timestamp") if start is not None else None,
        request.event.get("timestamp") if request is not None else None,
        complete.get("timestamp") if complete is not None else None,
    ):
        timestamp = _string_or_none(value)
        if timestamp is not None:
            return timestamp
    return None

def _copilot_tool_input_from_events(
    request: _CopilotToolRequestEvent | None,
    start: dict[str, object] | None,
) -> dict[str, object]:
    tool_input: dict[str, object] = {}
    start_payload = _copilot_event_payload(start or {})
    arguments = None
    if request is not None:
        request_input = request.payload.get("input")
        if isinstance(request_input, dict):
            arguments = request_input.get("arguments")
        if arguments is None:
            arguments = request.payload.get("arguments")
    if arguments is None:
        start_input = start_payload.get("input")
        if isinstance(start_input, dict):
            arguments = start_input.get("arguments")
    if arguments is None:
        arguments = start_payload.get("arguments")
    if arguments is None:
        command = _string_or_none(start_payload.get("command"))
        if command is not None:
            arguments = {"command": command}
    if arguments is not None:
        tool_input["arguments"] = arguments
    return tool_input

def _copilot_tool_output_from_event(event: dict[str, object]) -> dict[str, object]:
    output: dict[str, object] = {}
    payload = _copilot_event_payload(event)
    result = payload.get("result")
    if result is None:
        result = payload.get("output")
    if isinstance(result, dict):
        content = result.get("content")
        if content is None:
            content = result.get("text")
        if content is not None:
            output["content"] = content
        detailed_content = result.get("detailedContent")
        if detailed_content is None:
            detailed_content = result.get("detailed_content")
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

def _copilot_tool_model_from_events(
    request: _CopilotToolRequestEvent | None,
    start: dict[str, object] | None,
    complete: dict[str, object] | None,
) -> str | None:
    start_payload = _copilot_event_payload(start or {})
    complete_payload = _copilot_event_payload(complete or {})
    for value in (
        complete_payload.get("model"),
        start_payload.get("model"),
        request.payload.get("model") if request is not None else None,
    ):
        model = _string_or_none(value)
        if model is not None:
            return model
    return None

def _copilot_tool_interaction_id_from_events(
    request: _CopilotToolRequestEvent | None,
    start: dict[str, object] | None,
    complete: dict[str, object] | None,
) -> str | None:
    start_payload = _copilot_event_payload(start or {})
    complete_payload = _copilot_event_payload(complete or {})
    request_payload = _copilot_event_payload(request.event) if request is not None else {}
    for value in (
        complete_payload.get("interaction_id"),
        complete_payload.get("interactionId"),
        start_payload.get("interaction_id"),
        start_payload.get("interactionId"),
        request_payload.get("interaction_id"),
        request_payload.get("interactionId"),
        request.payload.get("interaction_id") if request is not None else None,
        request.payload.get("interactionId") if request is not None else None,
    ):
        interaction_id = _string_or_none(value)
        if interaction_id is not None:
            return interaction_id
    return None

def _copilot_tool_turn_id_from_events(
    request: _CopilotToolRequestEvent | None,
    start: dict[str, object] | None,
    complete: dict[str, object] | None,
) -> str | None:
    for event in (
        start,
        complete,
        request.event if request is not None else None,
    ):
        if event is None:
            continue
        turn_id = _string_or_none(event.get("turn_id")) or _string_or_none(
            _copilot_event_payload(event).get("turn_id")
        ) or _string_or_none(
            _copilot_event_payload(event).get("turnId")
        )
        if turn_id is not None:
            return turn_id
    return None

def _copilot_tool_source_refs_from_events(
    requests: list[_CopilotToolRequestEvent],
    starts: list[dict[str, object]],
    completes: list[dict[str, object]],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for request in requests:
        refs.extend(request.source_refs)
    for event in [*starts, *completes]:
        refs.extend(_dict_list(event.get("source_refs")))
    return _dedupe_dicts(refs)

def _copilot_tool_request_call_id(payload: dict[str, Any]) -> str | None:
    for key in ("call_id", "toolCallId", "callId", "id"):
        call_id = _string_or_none(payload.get(key))
        if call_id is not None:
            return call_id
    return None
def _copilot_model_runs_from_events(
    events: list[dict[str, object]],
    *,
    messages: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
) -> dict[str, object]:
    warnings: list[str] = []
    start_groups: dict[str, list[dict[str, object]]] = {}
    end_groups: dict[str, list[dict[str, object]]] = {}
    event_by_native_id = {
        native_event_id: event
        for event in events
        if (native_event_id := _copilot_record_event_id(event)) is not None
    }

    for event in events:
        event_kind = _string_or_none(event.get("kind"))
        event_type = _copilot_projected_event_type(event)
        is_turn_start = event_kind == "run.start" or event_type == "assistant.turn_start"
        is_turn_end = event_kind == "run.end" or event_type == "assistant.turn_end"
        if not is_turn_start and not is_turn_end:
            continue
        if _copilot_event_turn_id_from_event(event) is None:
            warnings.append(
                f"copilot {event_type} event {_copilot_projected_event_index(event)} has no turnId"
            )
        group_key = _copilot_turn_group_key_from_event(event)
        if is_turn_start:
            start_groups.setdefault(group_key, []).append(event)
        else:
            end_groups.setdefault(group_key, []).append(event)

    shutdown_event = _copilot_shutdown_event_from_events(events)
    ordered_starts = sorted(
        start_groups.items(),
        key=lambda item: _copilot_projected_event_index(item[1][0])
        if item[1]
        else 0,
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
        start_index = _copilot_projected_event_index(start_event)
        end_events = [
            event
            for event in end_groups.get(group_key, [])
            if _copilot_projected_event_index(event) >= start_index
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
        model_run = _copilot_model_run_from_event_turn(
            events=events,
            start_event=start_event,
            end_event=end_event,
            next_start_event=next_start_event,
            shutdown_event=shutdown_event,
            messages=messages,
            tool_invocations=tool_invocations,
            event_by_native_id=event_by_native_id,
            index=len(model_runs) + 1,
        )
        model_runs.append(model_run)

    for group_key, ends in sorted(
        end_groups.items(),
        key=lambda item: _copilot_projected_event_index(item[1][0])
        if item[1]
        else 0,
    ):
        if group_key not in start_groups and ends:
            warnings.append(
                f"copilot turn group {group_key} has assistant.turn_end without assistant.turn_start"
            )

    return {
        "model_runs": model_runs,
        "warnings": warnings,
    }

def _copilot_turn_group_key_from_event(event: dict[str, object]) -> str:
    return _copilot_event_turn_id_from_event(event) or (
        f"event-index-{_copilot_projected_event_index(event)}"
    )

def _copilot_event_turn_id_from_event(event: dict[str, object]) -> str | None:
    return _string_or_none(event.get("turn_id")) or _string_or_none(
        _copilot_event_payload(event).get("turn_id")
    ) or _string_or_none(
        _copilot_event_payload(event).get("turnId")
    )

def _copilot_shutdown_event_from_events(
    events: list[dict[str, object]],
) -> dict[str, object] | None:
    for event in reversed(events):
        if event.get("kind") == "session.end":
            return event
        if _copilot_projected_event_type(event) == "session.shutdown":
            return event
    return None

def _copilot_model_run_from_event_turn(
    *,
    events: list[dict[str, object]],
    start_event: dict[str, object],
    end_event: dict[str, object] | None,
    next_start_event: dict[str, object] | None,
    shutdown_event: dict[str, object] | None,
    messages: list[dict[str, object]],
    tool_invocations: list[dict[str, object]],
    event_by_native_id: dict[str, dict[str, object]],
    index: int,
) -> dict[str, object]:
    span_end_index = _copilot_turn_span_end_index_from_events(
        events=events,
        start_event=start_event,
        end_event=end_event,
        next_start_event=next_start_event,
    )
    span_end_event = _copilot_event_at_or_before_index(events, span_end_index) or start_event
    model, model_source = _copilot_model_for_event_turn(
        events,
        turn_start_event=start_event,
    )
    start_index = _copilot_projected_event_index(start_event)
    native: dict[str, object] = {
        "turn_start_present": True,
        "turn_end_present": end_event is not None,
        "turn_start_event_index": start_index,
        "span_end_event_index": span_end_index,
    }
    if model_source is not None:
        native["model_source"] = model_source
    start_native_event_id = _copilot_record_event_id(start_event)
    if start_native_event_id is not None:
        native["turn_start_event_id"] = start_native_event_id
    if end_event is not None:
        native["turn_end_event_index"] = _copilot_projected_event_index(end_event)
        end_native_event_id = _copilot_record_event_id(end_event)
        if end_native_event_id is not None:
            native["turn_end_event_id"] = end_native_event_id

    model_run: dict[str, object] = {
        "model_run_id": f"model-run-{index}",
        "provider": "copilot-cli",
        "status": _copilot_model_run_status_from_events(
            start_event=start_event,
            end_event=end_event,
            next_start_event=next_start_event,
            shutdown_event=shutdown_event,
        ),
        "native": native,
    }
    turn_id = _copilot_event_turn_id_from_event(start_event)
    if turn_id is not None:
        model_run["turn_id"] = turn_id
    start_timestamp = _string_or_none(start_event.get("timestamp"))
    if start_timestamp is not None:
        model_run["started_at"] = start_timestamp
    end_timestamp = _string_or_none(
        end_event.get("timestamp") if end_event is not None else None
    )
    if end_timestamp is not None:
        model_run["ended_at"] = end_timestamp
    if model is not None:
        model_run["model"] = model

    interaction_id = _copilot_model_run_interaction_id_from_events(
        events,
        start_event=start_event,
        end_event=end_event,
        span_end_index=span_end_index,
    )
    if interaction_id is not None:
        native["interaction_id"] = interaction_id

    output_tokens = _copilot_model_run_output_tokens_from_events(
        events,
        start_index=start_index,
        end_index=span_end_index,
    )
    if output_tokens:
        model_run["output_tokens"] = output_tokens

    source_refs = _copilot_model_run_source_refs_from_events(
        start_event=start_event,
        end_event=end_event,
        span_end_event=span_end_event,
    )
    if source_refs:
        model_run["source_refs"] = source_refs

    message_refs = _copilot_model_run_message_refs_from_events(
        messages,
        start_event=start_event,
        span_end_index=span_end_index,
        event_by_native_id=event_by_native_id,
    )
    if message_refs:
        model_run["message_refs"] = message_refs

    tool_refs = _copilot_model_run_tool_refs(
        tool_invocations,
        start_index=start_index,
        end_index=span_end_index,
    )
    if tool_refs:
        model_run["tool_invocation_refs"] = tool_refs

    event_refs = _copilot_model_run_event_refs(
        events,
        start_index=start_index,
        end_index=span_end_index,
    )
    if event_refs:
        model_run["event_refs"] = event_refs

    reasoning_trace = _copilot_model_run_reasoning_trace_from_events(
        events,
        start_index=start_index,
        end_index=span_end_index,
        model_run_index=index,
    )
    if reasoning_trace:
        model_run["reasoning_trace"] = reasoning_trace

    return model_run

def _copilot_turn_span_end_index_from_events(
    *,
    events: list[dict[str, object]],
    start_event: dict[str, object],
    end_event: dict[str, object] | None,
    next_start_event: dict[str, object] | None,
) -> int:
    start_index = _copilot_projected_event_index(start_event)
    if end_event is not None:
        return _copilot_projected_event_index(end_event)
    if next_start_event is not None:
        return max(start_index, _copilot_projected_event_index(next_start_event) - 1)
    return max(
        start_index,
        max(
            (_copilot_projected_event_index(event) for event in events),
            default=start_index,
        ),
    )

def _copilot_event_at_or_before_index(
    events: list[dict[str, object]],
    event_index: int,
) -> dict[str, object] | None:
    candidates = [
        event
        for event in events
        if _copilot_projected_event_index(event) <= event_index
    ]
    if not candidates:
        return None
    return max(candidates, key=_copilot_projected_event_index)

def _copilot_model_run_status_from_events(
    *,
    start_event: dict[str, object],
    end_event: dict[str, object] | None,
    next_start_event: dict[str, object] | None,
    shutdown_event: dict[str, object] | None,
) -> str:
    if end_event is not None:
        return "completed"
    start_index = _copilot_projected_event_index(start_event)
    if next_start_event is not None:
        return "unknown"
    if (
        shutdown_event is not None
        and _copilot_projected_event_index(shutdown_event) > start_index
    ):
        return "unknown"
    return "running"

def _copilot_model_for_event_turn(
    events: list[dict[str, object]],
    *,
    turn_start_event: dict[str, object],
) -> tuple[str | None, str | None]:
    turn_start_index = _copilot_projected_event_index(turn_start_event)
    previous_events = [
        event
        for event in events
        if _copilot_projected_event_index(event) < turn_start_index
    ]
    for event in reversed(previous_events):
        if _copilot_projected_event_type(event) != "session.model_change":
            continue
        payload = _copilot_event_payload(event)
        model = (
            _string_or_none(payload.get("model"))
            or _string_or_none(payload.get("new_model"))
            or _string_or_none(payload.get("newModel"))
        )
        if model is not None:
            return model, "session.model_change.newModel"

    shutdown_event = _copilot_shutdown_event_from_events(events)
    if shutdown_event is None:
        return None, None
    shutdown_payload = _copilot_event_payload(shutdown_event)
    model = _string_or_none(shutdown_payload.get("current_model")) or _string_or_none(
        shutdown_payload.get("currentModel")
    )
    if model is not None:
        return model, "session.shutdown.currentModel"
    return None, None

def _copilot_model_run_interaction_id_from_events(
    events: list[dict[str, object]],
    *,
    start_event: dict[str, object],
    end_event: dict[str, object] | None,
    span_end_index: int,
) -> str | None:
    start_payload = _copilot_event_payload(start_event)
    end_payload = _copilot_event_payload(end_event or {})
    for value in (
        start_payload.get("interaction_id"),
        start_payload.get("interactionId"),
        end_payload.get("interaction_id"),
        end_payload.get("interactionId"),
    ):
        interaction_id = _string_or_none(value)
        if interaction_id is not None:
            return interaction_id

    start_index = _copilot_projected_event_index(start_event)
    for event in events:
        event_index = _copilot_projected_event_index(event)
        if not start_index <= event_index <= span_end_index:
            continue
        interaction_id = _string_or_none(
            _copilot_event_payload(event).get("interaction_id")
        ) or _string_or_none(
            _copilot_event_payload(event).get("interactionId")
        )
        if interaction_id is not None:
            return interaction_id
    return None

def _copilot_model_run_output_tokens_from_events(
    events: list[dict[str, object]],
    *,
    start_index: int,
    end_index: int,
) -> int:
    output_tokens = 0
    for event in events:
        event_index = _copilot_projected_event_index(event)
        if not start_index <= event_index <= end_index:
            continue
        if event.get("kind") != "message" and (
            _copilot_projected_event_type(event) != "assistant.message"
        ):
            continue
        payload = _copilot_event_payload(event)
        output_tokens += _int_or_zero(payload.get("output_tokens"))
        output_tokens += _int_or_zero(payload.get("outputTokens"))
    return output_tokens

def _copilot_model_run_source_refs_from_events(
    *,
    start_event: dict[str, object],
    end_event: dict[str, object] | None,
    span_end_event: dict[str, object],
) -> list[dict[str, object]]:
    refs = [*_dict_list(start_event.get("source_refs"))]
    if end_event is not None:
        refs.extend(_dict_list(end_event.get("source_refs")))
    elif _copilot_projected_event_index(span_end_event) != _copilot_projected_event_index(start_event):
        refs.extend(_dict_list(span_end_event.get("source_refs")))
    return _dedupe_dicts(refs)

def _copilot_model_run_message_refs_from_events(
    messages: list[dict[str, object]],
    *,
    start_event: dict[str, object],
    span_end_index: int,
    event_by_native_id: dict[str, dict[str, object]],
) -> list[str]:
    refs: list[str] = []
    direct_parent_id = _copilot_direct_parent_message_ref_from_events(
        messages,
        start_event=start_event,
        event_by_native_id=event_by_native_id,
    )
    if direct_parent_id is not None:
        refs.append(direct_parent_id)

    start_index = _copilot_projected_event_index(start_event)
    for message in messages:
        message_id = _string_or_none(message.get("message_id"))
        if message_id is None:
            continue
        event_index = _copilot_record_event_index(message)
        if event_index is None:
            continue
        if start_index <= event_index <= span_end_index and message_id not in refs:
            refs.append(message_id)
    return refs

def _copilot_direct_parent_message_ref_from_events(
    messages: list[dict[str, object]],
    *,
    start_event: dict[str, object],
    event_by_native_id: dict[str, dict[str, object]],
) -> str | None:
    parent_id = _record_native_string_field(start_event, "parent_id")
    if parent_id is None:
        return None
    parent_event = event_by_native_id.get(parent_id)
    if parent_event is None or _copilot_projected_event_type(parent_event) not in {
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

def _copilot_model_run_reasoning_trace_from_events(
    events: list[dict[str, object]],
    *,
    start_index: int,
    end_index: int,
    model_run_index: int,
) -> list[dict[str, object]]:
    reasoning_trace: list[dict[str, object]] = []
    for event in events:
        event_index = _copilot_projected_event_index(event)
        if not start_index <= event_index <= end_index:
            continue
        if event.get("kind") == "reasoning":
            reasoning = _copilot_reasoning_entry_from_event(
                event,
                model_run_index=model_run_index,
                index=len(reasoning_trace) + 1,
            )
            if reasoning is not None:
                reasoning_trace.append(reasoning)
            continue
        if _copilot_projected_event_type(event) != "assistant.message":
            continue
        reasoning_trace.extend(
            _copilot_reasoning_entries_from_event_projection(
                event,
                model_run_index=model_run_index,
                offset=len(reasoning_trace),
            )
        )
    return reasoning_trace

def _copilot_reasoning_entry_from_event(
    event: dict[str, object],
    *,
    model_run_index: int,
    index: int,
) -> dict[str, object] | None:
    payload = _copilot_event_payload(event)
    content = _string_or_none(payload.get("content"))
    if content is None:
        return None
    reasoning: dict[str, object] = {
        "reasoning_id": f"reasoning-{model_run_index}-{index}",
        "visibility": _string_or_none(payload.get("visibility")) or "visible",
        "content": content,
        "native": dict(_record_native_dict(event)),
    }
    _copy_event_provenance(reasoning, event)
    return reasoning

def _copilot_reasoning_entries_from_event_projection(
    event: dict[str, object],
    *,
    model_run_index: int,
    offset: int,
) -> list[dict[str, object]]:
    payload = _copilot_event_payload(event)
    reasoning_trace: list[dict[str, object]] = []
    for source_key, visibility in (
        ("reasoningText", "visible"),
        ("reasoningOpaque", "opaque"),
        ("encryptedContent", "encrypted"),
    ):
        value = _string_or_none(payload.get(source_key))
        if value is None:
            continue
        reasoning: dict[str, object] = {
            "reasoning_id": f"reasoning-{model_run_index}-{offset + len(reasoning_trace) + 1}",
            "visibility": visibility,
            "content": value,
            "native": _copilot_reasoning_native_from_event(
                event,
                reasoning_key=source_key,
            ),
        }
        _copy_event_provenance(reasoning, event)
        reasoning_trace.append(reasoning)
    return reasoning_trace

def _copilot_reasoning_native_from_event(
    event: dict[str, object],
    *,
    reasoning_key: str,
) -> dict[str, object]:
    payload = _copilot_event_payload(event)
    native = dict(_record_native_dict(event))
    native["reasoning_key"] = reasoning_key
    _copy_present_fields(
        native,
        payload,
        _COPILOT_REASONING_NATIVE_FIELDS,
    )
    return native


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
        event_index = _copilot_projected_event_index(event)
        event_id = _string_or_none(event.get("event_id"))
        if event_id is None:
            continue
        if start_index <= event_index <= end_index:
            refs.append(event_id)
    return refs

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

def _copilot_usage_from_events(
    events: list[dict[str, object]],
) -> dict[str, object]:
    return _project_usage_from_events(
        events,
        project_event=_copilot_usage_from_event,
    )

def _copilot_usage_from_event(
    event: dict[str, object],
    index: int,
) -> tuple[dict[str, object] | list[dict[str, object]] | None, list[str]]:
    if event.get("kind") != "usage" and (
        _copilot_projected_event_type(event) != "session.shutdown"
    ):
        return None, []

    payload = _copilot_event_payload(event)
    model_metrics = payload.get("model_metrics")
    if model_metrics is None:
        model_metrics = payload.get("modelMetrics")
    if not isinstance(model_metrics, dict):
        return None, []

    entry_result = _copilot_model_metric_entries(model_metrics)
    warnings = _string_list(entry_result["warnings"])
    entries = entry_result["entries"]
    if not isinstance(entries, list):
        return None, warnings
    usage_records: list[dict[str, object]] = []
    for offset, entry_pair in enumerate(entries):
        if not (
            isinstance(entry_pair, tuple)
            and len(entry_pair) == 2
            and isinstance(entry_pair[0], str)
            and isinstance(entry_pair[1], dict)
        ):
            continue
        model_name, entry = entry_pair
        usage_records.append(
            _copilot_usage_record_from_event_metrics(
                event=event,
                model_name=model_name,
                entry=entry,
                index=index + offset,
            )
        )

    if not usage_records:
        return None, warnings
    return usage_records, warnings

def _copilot_usage_record_from_event_metrics(
    *,
    event: dict[str, object],
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
        "native": _copilot_usage_native_from_event(
            event=event,
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

    source_refs = _dict_list(event.get("source_refs"))
    if source_refs:
        usage["source_refs"] = source_refs

    return usage

def _copilot_usage_native_from_event(
    *,
    event: dict[str, object],
    model_name: str,
    entry: dict[str, Any],
) -> dict[str, object]:
    payload = _copilot_event_payload(event)
    native = dict(_record_native_dict(event))
    native["model_metrics_key"] = model_name
    native["model_metrics_entry"] = entry
    for source_key, native_key in (
        ("shutdownType", "shutdown_type"),
        ("totalPremiumRequests", "total_premium_requests"),
        ("totalApiDurationMs", "total_api_duration_ms"),
        ("sessionStartTime", "session_start_time"),
        ("currentModel", "current_model"),
        ("total_premium_requests", "total_premium_requests"),
        ("total_api_duration_ms", "total_api_duration_ms"),
        ("session_start_time", "session_start_time"),
        ("current_model", "current_model"),
    ):
        value = payload.get(source_key)
        if value is not None:
            native[native_key] = value

    session_token_counters: dict[str, object] = {}
    for source_key, native_key in (
        ("currentTokens", "current_tokens"),
        ("systemTokens", "system_tokens"),
        ("conversationTokens", "conversation_tokens"),
        ("toolDefinitionsTokens", "tool_definitions_tokens"),
        ("current_tokens", "current_tokens"),
        ("system_tokens", "system_tokens"),
        ("conversation_tokens", "conversation_tokens"),
        ("tool_definitions_tokens", "tool_definitions_tokens"),
    ):
        value = _int_or_none(payload.get(source_key))
        if value is not None:
            session_token_counters[native_key] = value
    if session_token_counters:
        native["session_token_counters"] = session_token_counters

    code_changes = payload.get("codeChanges")
    if isinstance(code_changes, dict) and code_changes:
        native["code_changes"] = code_changes

    return native

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

def _copilot_raw_event_counts(raw_events: _CopilotRawEvents) -> dict[str, object]:
    event_types: dict[str, int] = {}
    reasoning_evidence_count = 0
    usage_evidence_count = 0
    cost_evidence_count = 0
    tool_request_count = 0
    shutdown_usage_event_count = 0
    semantic_event_candidate_count = 0

    for event in raw_events.events:
        if event.event_type is not None:
            event_types[event.event_type] = event_types.get(event.event_type, 0) + 1
        semantic_event_candidate_count += _copilot_raw_event_semantic_candidate_count(
            event
        )
        reasoning_evidence_count += _copilot_event_reasoning_evidence_count(event)
        if _copilot_event_has_usage_evidence(event):
            usage_evidence_count += 1
        if event.event_type == "session.shutdown" and _copilot_shutdown_has_usage_payload(event):
            shutdown_usage_event_count += 1
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
        "shutdown_usage_event_count": shutdown_usage_event_count,
        "semantic_event_candidate_count": semantic_event_candidate_count,
    }

def _copilot_raw_event_semantic_candidate_count(event: _CopilotRawEvent) -> int:
    if event.event_type == "assistant.message":
        return (
            (1 if _copilot_raw_event_has_readable_content(event) else 0)
            + _copilot_event_reasoning_evidence_count(event)
            + _copilot_event_tool_request_count(event)
        )
    if event.event_type == "session.shutdown":
        return 1 + (1 if _copilot_shutdown_has_usage_payload(event) else 0)
    return 1

def _copilot_raw_event_has_readable_content(event: _CopilotRawEvent) -> bool:
    content = event.data.get("content")
    if _string_or_none(content) is not None:
        return True
    if not isinstance(content, list):
        return False
    for item in content:
        if _string_or_none(item) is not None:
            return True
        if isinstance(item, dict) and _string_or_none(item.get("text")) is not None:
            return True
    return False

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
    raw_event_count = _int_or_zero(raw_counts.get("records"))
    raw_semantic_event_candidate_count = _int_or_zero(
        raw_counts.get("semantic_event_candidate_count")
    )
    reasoning_count = _model_run_reasoning_count(model_runs)
    cost_normalized_count = _copilot_usage_billing_count(usage)
    event_status = _coverage_status(len(events))
    if raw_semantic_event_candidate_count and len(events) >= raw_semantic_event_candidate_count:
        event_status = "normalized"
    elif raw_semantic_event_candidate_count and len(events):
        event_status = "partial"
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
            "status": event_status,
            "raw_count": raw_event_count,
            "raw_semantic_candidate_count": raw_semantic_event_candidate_count,
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
