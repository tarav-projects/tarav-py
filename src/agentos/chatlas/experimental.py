from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.chat.extractors.codex import is_codex_rollout_path
from agentos.chat.extractors.copilot_cli import is_copilot_cli_session_path
from agentos.chat.extractors import extract_chat_session
from agentos.chatlas.core import chatlas_query


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


def chatlas_experimental_export_session_model(
    *,
    query: str,
    providers: tuple[str, ...] | None = None,
    output_format: str = "json",
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    if output_format != "json":
        raise CliError(f"unsupported experimental export format: {output_format}")

    normalized_query = query.strip()
    if not normalized_query:
        raise CliError("query must not be empty")

    payload = chatlas_query(
        query=normalized_query,
        providers=providers,
        chatlas_root=chatlas_root,
        include_artifacts=True,
    )
    sessions = payload.get("sessions")
    if not isinstance(sessions, list):
        raise CliError("Chatlas query returned an invalid sessions payload")
    if not sessions:
        raise CliError(f"no normalized Chatlas session matched query {query}")
    if len(sessions) > 1:
        choices = ", ".join(
            str(session.get("uri"))
            for session in sessions[:5]
            if isinstance(session, dict)
        )
        raise CliError(f"multiple Chatlas sessions matched query {query}: {choices}")

    session = sessions[0]
    if not isinstance(session, dict):
        raise CliError("Chatlas query returned an invalid session payload")

    return _build_experimental_session_model(session)


def _build_experimental_session_model(session: dict[str, Any]) -> dict[str, object]:
    provider = _string_or_none(session.get("provider"))
    sources = _experimental_source_payloads(session)
    normalization_result = _experimental_normalize_provider_raw(
        session,
        sources=sources,
    )
    normalization: dict[str, object] = {
        "provider": provider,
        "normalizer": normalization_result.normalizer,
        "version": 1,
        "source_mode": normalization_result.source_mode,
        "warnings": normalization_result.warnings,
        "unsupported_concepts": normalization_result.unsupported_concepts,
    }
    normalization.update(normalization_result.metadata)

    return {
        "class": "agentos.chatlas.experimental.session_model",
        "schema_version": 1,
        "experimental": True,
        "session": _experimental_session_payload(session),
        "agent_instance": _experimental_agent_instance_payload(session),
        "sources": sources,
        "chat": {
            "messages": normalization_result.messages,
            "model_runs": normalization_result.model_runs,
            "tool_invocations": normalization_result.tool_invocations,
            "events": normalization_result.events,
            "usage": normalization_result.usage,
        },
        "normalization": normalization,
    }


def _experimental_normalize_provider_raw(
    session: dict[str, Any],
    *,
    sources: list[dict[str, object]],
) -> _ExperimentalNormalizationResult:
    provider = _string_or_none(session.get("provider"))
    if provider is None:
        raise CliError(
            "experimental session model export requires a provider-specific raw normalizer; "
            "session provider is missing"
        )
    if provider == "codex":
        codex_result = _experimental_normalize_codex_raw_rollout(
            session,
            sources=sources,
        )
        if codex_result is not None:
            return codex_result
        raise CliError(
            "experimental session model export could not normalize codex raw artifacts"
        )
    if provider == "copilot-cli":
        copilot_result = _experimental_normalize_copilot_cli_raw_events(
            session,
            sources=sources,
        )
        if copilot_result is not None:
            return copilot_result
        raise CliError(
            "experimental session model export could not normalize copilot-cli raw artifacts"
        )

    raise CliError(
        "experimental session model export has no provider-specific raw normalizer "
        f"for provider {provider}"
    )


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
    usage: list[dict[str, object]] = []
    residual_unsupported_concepts = _copilot_residual_unsupported_concepts(
        raw_counts=raw_counts,
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
    warnings.extend(_string_list(message_result["warnings"]))
    warnings.extend(_string_list(tool_result["warnings"]))
    warnings.extend(_string_list(event_result["warnings"]))
    warnings.extend(_string_list(model_run_result["warnings"]))

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
    events: list[dict[str, object]] = []
    warnings: list[str] = []

    for raw_event in raw_events.events:
        event_type = raw_event.event_type or "unknown"
        if raw_event.event_type is None:
            warnings.append(
                f"copilot event record {raw_event.event_index} has no event type"
            )

        event: dict[str, object] = {
            "event_id": f"event-{len(events) + 1}",
            "type": f"copilot-cli.{event_type}",
            "data": dict(raw_event.data),
            "native": _copilot_event_native(raw_event),
        }
        if raw_event.timestamp is not None:
            event["timestamp"] = raw_event.timestamp
        if raw_event.source_refs:
            event["source_refs"] = raw_event.source_refs

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

        interaction_id = _string_or_none(raw_event.data.get("interactionId"))
        if interaction_id is not None:
            event["interaction_id"] = interaction_id

        events.append(event)

    return {
        "events": events,
        "warnings": warnings,
    }


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
    return native


def _copilot_event_turn_id(raw_event: _CopilotRawEvent) -> str | None:
    return _string_or_none(raw_event.data.get("turnId"))


def _copilot_event_call_id(raw_event: _CopilotRawEvent) -> str | None:
    return _string_or_none(raw_event.data.get("toolCallId"))


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
        if raw_event.timestamp is not None:
            message["timestamp"] = raw_event.timestamp
        if raw_event.source_refs:
            message["source_refs"] = raw_event.source_refs

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
    value = raw_event.data.get("content")
    return _copilot_text_content_blocks(
        value,
        context=f"copilot message event {raw_event.event_index} content",
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

    for source_key, native_key in (
        ("messageId", "message_id"),
        ("requestId", "request_id"),
        ("phase", "phase"),
        ("outputTokens", "output_tokens"),
        ("toolRequests", "tool_requests"),
        ("reasoningText", "reasoning_text"),
        ("reasoningOpaque", "reasoning_opaque"),
        ("encryptedContent", "encrypted_content"),
        ("interactionId", "interaction_id"),
    ):
        value = raw_event.data.get(source_key)
        if value is not None:
            native[native_key] = value

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

    _copilot_warn_about_tool_group_records(
        warnings=warnings,
        call_id=call_id,
        kind="assistant toolRequest",
        records=requests,
    )
    _copilot_warn_about_tool_group_records(
        warnings=warnings,
        call_id=call_id,
        kind="tool.execution_start",
        records=starts,
    )
    _copilot_warn_about_tool_group_records(
        warnings=warnings,
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
        invocation["interaction_id"] = interaction_id
    turn_id = _copilot_tool_turn_id(first_request, first_start, first_complete)
    if turn_id is not None:
        invocation["turn_id"] = turn_id

    source_refs = _copilot_tool_source_refs(requests, starts, completes)
    if source_refs:
        invocation["source_refs"] = source_refs

    return invocation, warnings


def _copilot_warn_about_tool_group_records(
    *,
    warnings: list[str],
    call_id: str,
    kind: str,
    records: list[object],
) -> None:
    if not records:
        warnings.append(f"copilot toolCallId {call_id} missing {kind} record")
    elif len(records) > 1:
        warnings.append(
            f"copilot toolCallId {call_id} has {len(records)} {kind} records; using first"
        )


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
    model_run: dict[str, object] = {
        "model_run_id": f"model-run-{index}",
        "provider": "copilot-cli",
        "status": _copilot_model_run_status(
            start_event=start_event,
            end_event=end_event,
            next_start_event=next_start_event,
            shutdown_event=shutdown_event,
        ),
        "native": {
            "turn_start_present": True,
            "turn_end_present": end_event is not None,
            "turn_start_event_index": start_event.event_index,
            "span_end_event_index": span_end_index,
        },
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
        native = model_run.get("native")
        if isinstance(native, dict) and model_source is not None:
            native["model_source"] = model_source

    interaction_id = _copilot_model_run_interaction_id(
        raw_events,
        start_event=start_event,
        end_event=end_event,
        span_end_index=span_end_index,
    )
    if interaction_id is not None:
        model_run["interaction_id"] = interaction_id

    output_tokens = _copilot_model_run_output_tokens(
        raw_events,
        start_index=start_event.event_index,
        end_index=span_end_index,
    )
    if output_tokens:
        model_run["output_tokens"] = output_tokens

    if start_event.event_id is not None:
        native = model_run.get("native")
        if isinstance(native, dict):
            native["turn_start_event_id"] = start_event.event_id
    if end_event is not None:
        native = model_run.get("native")
        if isinstance(native, dict):
            native["turn_end_event_index"] = end_event.event_index
            if end_event.event_id is not None:
                native["turn_end_event_id"] = end_event.event_id

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
        event_index = _copilot_message_event_index(message)
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
        raw_event_id = _copilot_message_raw_event_id(message)
        if message_id is not None and raw_event_id == parent_id:
            return message_id
    return None


def _copilot_message_event_index(message: dict[str, object]) -> int | None:
    native = message.get("native")
    if isinstance(native, dict):
        event_index = _int_or_none(native.get("event_index"))
        if event_index is not None:
            return event_index
    return _source_ref_first_event_index(message.get("source_refs"))


def _copilot_message_raw_event_id(message: dict[str, object]) -> str | None:
    native = message.get("native")
    if not isinstance(native, dict):
        return None
    return _string_or_none(native.get("event_id"))


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
        event_index = _copilot_normalized_event_index(event)
        if event_index is None:
            continue
        if start_index <= event_index <= end_index:
            refs.append(event_id)
    return refs


def _copilot_normalized_event_index(event: dict[str, object]) -> int | None:
    native = event.get("native")
    if isinstance(native, dict):
        event_index = _int_or_none(native.get("event_index"))
        if event_index is not None:
            return event_index
    return _source_ref_first_event_index(event.get("source_refs"))


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
        reasoning_text = _string_or_none(raw_event.data.get("reasoningText"))
        if reasoning_text is None:
            continue
        reasoning: dict[str, object] = {
            "reasoning_id": f"reasoning-{model_run_index}-{len(reasoning_trace) + 1}",
            "visibility": "visible",
            "text": reasoning_text,
            "native": _copilot_reasoning_native(raw_event),
        }
        if raw_event.timestamp is not None:
            reasoning["timestamp"] = raw_event.timestamp
        if raw_event.source_refs:
            reasoning["source_refs"] = raw_event.source_refs
        reasoning_trace.append(reasoning)
    return reasoning_trace


def _copilot_reasoning_native(raw_event: _CopilotRawEvent) -> dict[str, object]:
    native = _copilot_event_native(raw_event)
    for source_key, native_key in (
        ("messageId", "message_id"),
        ("requestId", "request_id"),
        ("phase", "phase"),
        ("interactionId", "interaction_id"),
        ("outputTokens", "output_tokens"),
    ):
        value = raw_event.data.get(source_key)
        if value is not None:
            native[native_key] = value
    return native


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


def _copilot_raw_event_counts(raw_events: _CopilotRawEvents) -> dict[str, object]:
    event_types: dict[str, int] = {}
    reasoning_evidence_count = 0
    usage_evidence_count = 0
    cost_evidence_count = 0
    tool_request_count = 0

    for event in raw_events.events:
        if event.event_type is not None:
            event_types[event.event_type] = event_types.get(event.event_type, 0) + 1
        if _copilot_event_has_reasoning_evidence(event):
            reasoning_evidence_count += 1
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
    if event.event_type != "assistant.message":
        return False
    return any(
        key in event.data
        for key in ("reasoningText", "reasoningOpaque", "encryptedContent")
    )


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
            "status": "event_only" if cost_evidence_count else "no_raw_evidence",
            "raw_evidence_count": cost_evidence_count,
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


def _copilot_residual_unsupported_concepts(
    *,
    raw_counts: dict[str, object],
) -> list[str]:
    unsupported: list[str] = []
    if _int_or_zero(raw_counts.get("usage_evidence_count")):
        unsupported.append("usage")
    if _int_or_zero(raw_counts.get("cost_evidence_count")):
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


def _experimental_session_payload(session: dict[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key in (
        "uri",
        "provider",
        "instance",
        "provider_instance_fingerprint",
        "session_id",
        "display_name",
        "display_name_field",
        "created_at",
        "updated_at",
        "native",
    ):
        value = session.get(key)
        if value is not None:
            payload[key] = value
    return payload


def _experimental_agent_instance_payload(session: dict[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {}
    provider = _string_or_none(session.get("provider"))
    instance = _string_or_none(session.get("instance"))
    fingerprint = _string_or_none(session.get("provider_instance_fingerprint"))
    if provider is not None:
        payload["provider_family"] = provider
    if instance is not None:
        payload["instance"] = instance
    if fingerprint is not None:
        payload["provider_instance_fingerprint"] = fingerprint
    return payload


def _experimental_source_payloads(session: dict[str, Any]) -> list[dict[str, object]]:
    artifacts = session.get("backing_artifacts")
    if not isinstance(artifacts, list):
        primary = session.get("primary_backing_artifact")
        artifacts = [primary] if isinstance(primary, dict) else []

    sources: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for index, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, dict):
            continue
        source = _experimental_source_payload(index=index, artifact=artifact)
        identity = (
            source.get("role"),
            source.get("storage_kind"),
            source.get("path"),
            _jsonable_identity(source.get("locator")),
        )
        if identity in seen:
            continue
        seen.add(identity)
        sources.append(source)
    return sources


def _experimental_source_payload(*, index: int, artifact: dict[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_ref_id": f"source-{index}",
    }
    for key in (
        "role",
        "storage_kind",
        "path",
        "locator",
        "extractable",
    ):
        value = artifact.get(key)
        if value is not None:
            payload[key] = value
    return payload


def _experimental_clean_transcript_result(
    session: dict[str, Any],
    *,
    sources: list[dict[str, object]],
    normalizer: str,
) -> _ExperimentalNormalizationResult:
    warnings = [
        "chat messages were normalized from the clean transcript fallback",
        "raw replay events, tool execution structure, model-run boundaries, and reasoning details may be missing",
    ]
    unsupported_concepts = [
        "model_runs",
        "tool_invocations",
        "events",
    ]
    primary_artifact = _primary_backing_artifact(session)
    if primary_artifact is None:
        return _ExperimentalNormalizationResult(
            messages=[],
            model_runs=[],
            tool_invocations=[],
            events=[],
            usage=[],
            normalizer=normalizer,
            source_mode="session_metadata_only",
            warnings=[
                "no primary backing artifact is available for clean transcript fallback",
            ],
            unsupported_concepts=[
                "messages",
                *unsupported_concepts,
            ],
            metadata=_experimental_normalization_metadata(
                messages=[],
                model_runs=[],
                tool_invocations=[],
                events=[],
                usage=[],
                deferred_concepts=[],
            ),
        )

    primary_path = _string_or_none(primary_artifact.get("path"))
    if primary_path is None:
        return _ExperimentalNormalizationResult(
            messages=[],
            model_runs=[],
            tool_invocations=[],
            events=[],
            usage=[],
            normalizer=normalizer,
            source_mode="session_metadata_only",
            warnings=[
                "primary backing artifact has no path for clean transcript fallback",
            ],
            unsupported_concepts=[
                "messages",
                *unsupported_concepts,
            ],
            metadata=_experimental_normalization_metadata(
                messages=[],
                model_runs=[],
                tool_invocations=[],
                events=[],
                usage=[],
                deferred_concepts=[],
            ),
        )

    session_id = _string_or_none(session.get("session_id"))
    try:
        rendered = extract_chat_session(
            session_query=session_id,
            file_path=primary_path,
            output_format="jsonl",
            raw=False,
        )
    except (CliError, OSError, ValueError) as exc:
        return _ExperimentalNormalizationResult(
            messages=[],
            model_runs=[],
            tool_invocations=[],
            events=[],
            usage=[],
            normalizer=normalizer,
            source_mode="session_metadata_only",
            warnings=[
                f"clean transcript fallback failed: {exc}",
            ],
            unsupported_concepts=[
                "messages",
                *unsupported_concepts,
            ],
            metadata=_experimental_normalization_metadata(
                messages=[],
                model_runs=[],
                tool_invocations=[],
                events=[],
                usage=[],
                deferred_concepts=[],
            ),
        )

    source_ref_id = _source_ref_id_for_artifact(primary_artifact, sources=sources)
    try:
        messages = _messages_from_clean_transcript_jsonl(
            rendered,
            source_ref_id=source_ref_id,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        return _ExperimentalNormalizationResult(
            messages=[],
            model_runs=[],
            tool_invocations=[],
            events=[],
            usage=[],
            normalizer=normalizer,
            source_mode="session_metadata_only",
            warnings=[
                f"clean transcript fallback produced invalid jsonl: {exc}",
            ],
            unsupported_concepts=[
                "messages",
                *unsupported_concepts,
            ],
            metadata=_experimental_normalization_metadata(
                messages=[],
                model_runs=[],
                tool_invocations=[],
                events=[],
                usage=[],
                deferred_concepts=[],
            ),
        )
    if not messages:
        return _ExperimentalNormalizationResult(
            messages=[],
            model_runs=[],
            tool_invocations=[],
            events=[],
            usage=[],
            normalizer=normalizer,
            source_mode="clean_transcript_fallback",
            warnings=[
                "clean transcript fallback produced no messages",
                *warnings[1:],
            ],
            unsupported_concepts=unsupported_concepts,
            metadata=_experimental_normalization_metadata(
                messages=[],
                model_runs=[],
                tool_invocations=[],
                events=[],
                usage=[],
                deferred_concepts=[],
            ),
        )

    return _ExperimentalNormalizationResult(
        messages=messages,
        model_runs=[],
        tool_invocations=[],
        events=[],
        usage=[],
        normalizer=normalizer,
        source_mode="clean_transcript_fallback",
        warnings=warnings,
        unsupported_concepts=unsupported_concepts,
        metadata=_experimental_normalization_metadata(
            messages=messages,
            model_runs=[],
            tool_invocations=[],
            events=[],
            usage=[],
            deferred_concepts=[],
        ),
    )


def _messages_from_clean_transcript_jsonl(
    rendered: str,
    *,
    source_ref_id: str | None,
) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []
    for index, line in enumerate(rendered.splitlines(), start=1):
        if not line.strip():
            continue
        turn = json.loads(line)
        if not isinstance(turn, dict):
            continue
        role = _string_or_none(turn.get("role"))
        text = _string_or_none(turn.get("text"))
        timestamp = _string_or_none(turn.get("timestamp"))
        if role is None or text is None:
            continue
        message: dict[str, object] = {
            "message_id": f"message-{index}",
            "role": role,
            "content": [
                {
                    "type": "text",
                    "text": text,
                }
            ],
        }
        if timestamp is not None:
            message["timestamp"] = timestamp
        if source_ref_id is not None:
            message["source_refs"] = [{"source_ref_id": source_ref_id}]
        messages.append(message)
    return messages


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


__all__ = ["chatlas_experimental_export_session_model"]
