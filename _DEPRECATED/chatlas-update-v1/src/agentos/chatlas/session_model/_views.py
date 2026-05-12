from __future__ import annotations

from copy import deepcopy
from typing import Any

from agentos._core.errors import CliError


_CHATLAS_EXPORT_VIEW_CHOICES = (
    "full",
    "transcript",
    "user",
    "replay",
    "events",
    "zip-transcript",
)

_MINIMAL_SESSION_FIELDS = (
    "uri",
    "provider",
    "session_id",
    "display_name",
    "created_at",
    "updated_at",
    "identity_hash",
    "content_hash",
)

_ZIP_TRANSCRIPT_SESSION_FIELDS = (
    "uri",
    "provider",
    "session_id",
    "display_name",
    "created_at",
    "updated_at",
)


def _project_session_model_view(
    session_model: dict[str, Any],
    *,
    view: str,
) -> dict[str, object]:
    if view not in _CHATLAS_EXPORT_VIEW_CHOICES:
        raise CliError(f"unsupported chatlas export view: {view}")
    if view == "full":
        return session_model

    projected = deepcopy(session_model)
    projected["view"] = view

    chat = projected.get("chat")
    if not isinstance(chat, dict):
        raise CliError("chatlas export produced an invalid session model payload")

    events = _dict_list(chat.get("events"))
    model_runs = _dict_list(chat.get("model_runs"))
    tool_invocations = _dict_list(chat.get("tool_invocations"))

    if view == "transcript":
        filtered_events = _filtered_message_events(
            events,
            allowed_roles={"user", "assistant"},
            surface_name="transcript",
        )
        chat["events"] = filtered_events
        chat["messages"] = _messages_from_events(filtered_events)
        chat["model_runs"] = []
        chat["tool_invocations"] = []
        chat["usage"] = []
        return projected

    if view == "user":
        filtered_events = _filtered_message_events(
            events,
            allowed_roles={"user"},
            surface_name="transcript",
        )
        chat["events"] = filtered_events
        chat["messages"] = _messages_from_events(filtered_events)
        chat["model_runs"] = []
        chat["tool_invocations"] = []
        chat["usage"] = []
        return projected

    if view == "replay":
        filtered_events = _filtered_replay_events(events)
        filtered_event_ids = _event_ids(filtered_events)
        filtered_tool_invocations = _filtered_tool_invocations(
            tool_invocations,
            event_ids=filtered_event_ids,
        )
        filtered_tool_invocation_ids = _record_ids(
            filtered_tool_invocations,
            id_key="tool_invocation_id",
        )
        chat["events"] = _replay_events_with_filtered_tool_refs(
            filtered_events,
            tool_invocation_ids=filtered_tool_invocation_ids,
        )
        chat["messages"] = _messages_from_events(chat["events"])
        chat["model_runs"] = _filtered_model_runs(
            model_runs,
            event_ids=filtered_event_ids,
        )
        chat["tool_invocations"] = filtered_tool_invocations
        chat["usage"] = []
        return projected

    if view == "events":
        chat["messages"] = []
        chat["model_runs"] = []
        chat["tool_invocations"] = []
        chat["usage"] = []
        return projected

    if view == "zip-transcript":
        filtered_events = _filtered_message_events(
            events,
            allowed_roles={"user", "assistant"},
            surface_name="transcript",
            text_only=True,
        )
        return {
            "class": "agentos.chatlas.zip_transcript",
            "schema_version": projected.get("schema_version", 1),
            "view": view,
            "session": _minimal_session_payload(
                projected.get("session"),
                allowed_fields=_ZIP_TRANSCRIPT_SESSION_FIELDS,
            ),
            "turns": _turns_from_events(filtered_events),
        }

    raise CliError(f"unsupported chatlas export view: {view}")


def _filtered_message_events(
    events: list[dict[str, object]],
    *,
    allowed_roles: set[str],
    surface_name: str,
    text_only: bool = False,
) -> list[dict[str, object]]:
    filtered: list[dict[str, object]] = []
    for event in events:
        if event.get("kind") != "message":
            continue
        if _event_surface(event, surface_name) != "visible":
            continue
        role = _event_message_role(event)
        if role not in allowed_roles:
            continue
        cleaned = deepcopy(event)
        if text_only:
            payload = cleaned.get("payload")
            if not isinstance(payload, dict):
                continue
            text_content = _text_only_content_blocks(payload.get("content"))
            if not text_content:
                continue
            payload["content"] = text_content
        filtered.append(cleaned)
    return filtered


def _filtered_replay_events(
    events: list[dict[str, object]],
) -> list[dict[str, object]]:
    filtered: list[dict[str, object]] = []
    for event in events:
        kind = _string_or_none(event.get("kind"))
        if kind is None:
            continue
        if kind == "message":
            if _event_surface(event, "replay") != "visible":
                continue
            role = _event_message_role(event)
            if role not in {"user", "assistant"}:
                continue
            filtered.append(deepcopy(event))
            continue
        if not kind.startswith("tool."):
            continue
        if _event_surface(event, "replay") == "hidden":
            continue
        filtered.append(_filtered_tool_event(event))
    return filtered


def _filtered_tool_event(event: dict[str, object]) -> dict[str, object]:
    cleaned = deepcopy(event)
    payload = cleaned.get("payload")
    if isinstance(payload, dict):
        payload.pop("result", None)
        payload.pop("output", None)
        payload.pop("tool_use_result", None)
        if cleaned.get("kind") == "tool.result":
            payload.pop("content", None)
    return cleaned


def _messages_from_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []
    for event in events:
        if event.get("kind") != "message":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        role = _string_or_none(payload.get("role"))
        content = _dict_list(payload.get("content"))
        if role is None or not content:
            continue
        message: dict[str, object] = {
            "message_id": _string_or_none(event.get("message_id"))
            or f"message-{len(messages) + 1}",
            "role": role,
            "visibility": _message_visibility_from_event(event),
            "content": content,
            "event_refs": [_string_or_none(event.get("event_id"))]
            if _string_or_none(event.get("event_id")) is not None
            else [],
        }
        timestamp = _string_or_none(event.get("timestamp"))
        if timestamp is not None:
            message["timestamp"] = timestamp
        source_refs = _dict_list(event.get("source_refs"))
        if source_refs:
            message["source_refs"] = source_refs
        messages.append(message)
    return messages


def _turns_from_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    turns: list[dict[str, object]] = []
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        role = _string_or_none(payload.get("role"))
        if role is None:
            continue
        text = _text_from_content_blocks(payload.get("content"))
        if not text:
            continue
        turns.append(
            {
                "role": role,
                "text": text,
            }
        )
    return turns


def _minimal_session_payload(
    session: object,
    *,
    allowed_fields: tuple[str, ...] = _MINIMAL_SESSION_FIELDS,
) -> dict[str, object]:
    if not isinstance(session, dict):
        return {}
    return {
        key: deepcopy(value)
        for key, value in session.items()
        if key in allowed_fields
    }


def _text_from_content_blocks(value: object) -> str:
    return "\n".join(
        block_text
        for block in _dict_list(value)
        if (block_text := _string_or_none(block.get("text"))) is not None
    )


def _filtered_model_runs(
    model_runs: list[dict[str, object]],
    *,
    event_ids: set[str],
) -> list[dict[str, object]]:
    filtered: list[dict[str, object]] = []
    for model_run in model_runs:
        if not isinstance(model_run, dict):
            continue
        run_event_refs = _string_set(model_run.get("event_refs"))
        if not run_event_refs.intersection(event_ids):
            continue
        cleaned = deepcopy(model_run)
        cleaned.pop("reasoning_trace", None)
        cleaned["event_refs"] = [
            event_ref
            for event_ref in _string_list(cleaned.get("event_refs"))
            if event_ref in event_ids
        ]
        filtered.append(cleaned)
    return filtered


def _filtered_tool_invocations(
    tool_invocations: list[dict[str, object]],
    *,
    event_ids: set[str],
) -> list[dict[str, object]]:
    filtered: list[dict[str, object]] = []
    for tool_invocation in tool_invocations:
        if not isinstance(tool_invocation, dict):
            continue
        invocation_event_refs = _string_list(tool_invocation.get("event_refs"))
        matching_event_refs = [
            event_ref for event_ref in invocation_event_refs if event_ref in event_ids
        ]
        if not matching_event_refs:
            continue
        cleaned = deepcopy(tool_invocation)
        cleaned.pop("result", None)
        cleaned.pop("output", None)
        cleaned["event_refs"] = matching_event_refs
        filtered.append(cleaned)
    return filtered


def _replay_events_with_filtered_tool_refs(
    events: list[dict[str, object]],
    *,
    tool_invocation_ids: set[str],
) -> list[dict[str, object]]:
    filtered: list[dict[str, object]] = []
    for event in events:
        cleaned = deepcopy(event)
        tool_invocation_ref = _string_or_none(cleaned.get("tool_invocation_ref"))
        if (
            tool_invocation_ref is not None
            and tool_invocation_ref not in tool_invocation_ids
        ):
            cleaned.pop("tool_invocation_ref", None)
        filtered.append(cleaned)
    return filtered


def _message_visibility_from_event(event: dict[str, object]) -> str:
    return "conversation" if _event_surface(event, "transcript") == "visible" else "context"


def _event_message_role(event: dict[str, object]) -> str | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    return _string_or_none(payload.get("role"))


def _event_surface(event: dict[str, object], surface_name: str) -> str | None:
    surfaces = event.get("surfaces")
    if not isinstance(surfaces, dict):
        return None
    return _string_or_none(surfaces.get(surface_name))


def _event_ids(events: list[dict[str, object]]) -> set[str]:
    return {
        event_id
        for event in events
        if isinstance(event, dict)
        and (event_id := _string_or_none(event.get("event_id"))) is not None
    }


def _record_ids(records: list[dict[str, object]], *, id_key: str) -> set[str]:
    return {
        record_id
        for record in records
        if isinstance(record, dict)
        and (record_id := _string_or_none(record.get(id_key))) is not None
    }


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _string_set(value: object) -> set[str]:
    return set(_string_list(value))


def _text_only_content_blocks(value: object) -> list[dict[str, object]]:
    blocks = _dict_list(value)
    return [
        deepcopy(block)
        for block in blocks
        if _string_or_none(block.get("type")) == "text"
        and _string_or_none(block.get("text")) is not None
    ]


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None
