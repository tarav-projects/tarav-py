# $kw: ^view-event-refs --from Chatlas.View.Model --from Session.Event.Tape --note [CT] disposable projections retain Event.Ref objects whose stable address survives the selected tape subset ^c20260807-16u
from __future__ import annotations

from copy import deepcopy
from typing import Any

from tarav._core.errors import CliError
from tarav.chatlas.normalization.session_model.source_refs import record_native_dict
from tarav.chatlas._payload_helpers import (
    dict_list,
    string_or_none,
)
from tarav.chatlas.event_ref import event_ref, event_ref_list


CHATLAS_VIEW_NAMES = (
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
    "last_activity_at",
    "identity_hash",
    "content_hash",
)

_ZIP_TRANSCRIPT_SESSION_FIELDS = (
    "uri",
    "provider",
    "session_id",
    "display_name",
    "created_at",
    "last_activity_at",
)


def _project_session_model_view(
    session_model: dict[str, Any],
    *,
    view: str,
    range_spec: str | None = None,
    contains: str | None = None,
    role: str | None = None,
    around: str | None = None,
    radius: int | None = None,
) -> dict[str, object]:
    if view not in CHATLAS_VIEW_NAMES:
        raise CliError(f"unsupported Chatlas view: {view}")
    if range_spec is not None and view != "zip-transcript":
        raise CliError(
            f"chatlas views get --range is not supported for view {view!r}"
        )
    has_selection = any(value is not None for value in (contains, role, around))
    if radius is not None and around is None:
        raise CliError("chatlas views get --radius requires --around")
    if has_selection and view == "full":
        raise CliError(
            "chatlas views get selection flags are not supported for view 'full'"
        )
    if view == "full":
        return session_model

    projected = deepcopy(session_model)
    projected["view"] = view

    chat = projected.get("chat")
    if not isinstance(chat, dict):
        raise CliError("chatlas views get produced an invalid session model payload")

    from tarav.chatlas.normalization.session_model.filters import (
        build_event_selection,
    )

    events = dict_list(chat.get("events"))
    for select in build_event_selection(
        contains=contains, role=role, around=around, radius=radius
    ):
        events = select(events)
    model_runs = dict_list(chat.get("model_runs"))
    tool_invocations = dict_list(chat.get("tool_invocations"))

    if view == "transcript":
        filtered_events = _filtered_message_events(
            events,
            allowed_roles={"user", "assistant"},
            surface_name="transcript",
        )
        _set_chat_projection_payload(
            chat,
            events=filtered_events,
            messages=_messages_from_events(filtered_events),
        )
        return projected

    if view == "user":
        filtered_events = _filtered_message_events(
            events,
            allowed_roles={"user"},
            surface_name="transcript",
        )
        _set_chat_projection_payload(
            chat,
            events=filtered_events,
            messages=_messages_from_events(filtered_events),
        )
        return projected

    if view == "replay":
        filtered_events = _filtered_replay_events(events)
        filtered_addresses = _event_addresses(filtered_events)
        filtered_tool_invocations = _filtered_tool_invocations(
            tool_invocations,
            addresses=filtered_addresses,
        )
        filtered_tool_invocation_ids = _record_ids(
            filtered_tool_invocations,
            id_key="tool_invocation_id",
        )
        replay_events = _replay_events_with_filtered_tool_refs(
            filtered_events,
            tool_invocation_ids=filtered_tool_invocation_ids,
        )
        _set_chat_projection_payload(
            chat,
            events=replay_events,
            messages=_messages_from_events(replay_events),
            model_runs=_filtered_model_runs(
                model_runs,
                addresses=filtered_addresses,
            ),
            tool_invocations=filtered_tool_invocations,
        )
        return projected

    if view == "events":
        _set_chat_projection_payload(chat, events=events)
        return projected

    if view == "zip-transcript":
        filtered_events = _filtered_message_events(
            events,
            allowed_roles={"user", "assistant"},
            surface_name="transcript",
            text_only=True,
        )
        turns = _turns_from_events(filtered_events)
        if range_spec is not None:
            turns, range_payload = _range_sequence(
                turns,
                range_spec=range_spec,
                target="turns",
            )
        else:
            range_payload = None
        payload = {
            "class": "agentos_chatlas.zip_transcript",
            "schema_version": projected.get("schema_version", 1),
            "view": view,
            "session": _minimal_session_payload(
                projected.get("session"),
                allowed_fields=_ZIP_TRANSCRIPT_SESSION_FIELDS,
            ),
            "turns": turns,
        }
        if range_payload is not None:
            payload["range"] = range_payload
        return payload

    raise CliError(f"unsupported Chatlas view: {view}")


def _set_chat_projection_payload(
    chat: dict[str, object],
    *,
    events: list[dict[str, object]],
    messages: list[dict[str, object]] | None = None,
    model_runs: list[dict[str, object]] | None = None,
    tool_invocations: list[dict[str, object]] | None = None,
) -> None:
    chat["events"] = events
    chat["messages"] = messages if messages is not None else []
    chat["model_runs"] = model_runs if model_runs is not None else []
    chat["tool_invocations"] = tool_invocations if tool_invocations is not None else []
    chat["usage"] = []


def _range_sequence(
    values: list[dict[str, object]],
    *,
    range_spec: str,
    target: str,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    start, stop = _resolve_range(range_spec, total=len(values))
    return values[start:stop], {
        "target": target,
        "start": start,
        "stop": stop,
        "total": len(values),
    }


def _resolve_range(range_spec: str, *, total: int) -> tuple[int, int]:
    if range_spec == "":
        raise CliError("invalid chatlas views get --range: range must not be empty")
    if range_spec.count(":") > 1:
        raise CliError(
            "invalid chatlas views get --range: step syntax is not supported"
        )
    if ":" not in range_spec:
        index = _parse_range_bound(range_spec, range_spec=range_spec)
        if index < 0:
            index += total
        if index < 0 or index >= total:
            raise CliError(
                "invalid chatlas views get --range: index is out of range"
            )
        return index, index + 1

    raw_start, raw_stop = range_spec.split(":", maxsplit=1)
    start = _parse_range_bound(raw_start, range_spec=range_spec) if raw_start else None
    stop = _parse_range_bound(raw_stop, range_spec=range_spec) if raw_stop else None
    return slice(start, stop).indices(total)[:2]


def _parse_range_bound(value: str, *, range_spec: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise CliError(
            f"invalid chatlas views get --range {range_spec!r}: "
            "bounds must be integers"
        ) from exc


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
        kind = string_or_none(event.get("kind"))
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
        role = string_or_none(payload.get("role"))
        content = dict_list(payload.get("content"))
        if role is None or not content:
            continue
        message: dict[str, object] = {
            "message_id": string_or_none(record_native_dict(event).get("message_id"))
            or f"message-{len(messages) + 1}",
            "role": role,
            "visibility": _message_visibility_from_event(event),
            "content": content,
            "event_refs": [event_ref(event)]
            if string_or_none(event.get("event_address")) is not None
            else [],
        }
        timestamp = string_or_none(event.get("timestamp"))
        if timestamp is not None:
            message["timestamp"] = timestamp
        source_refs = dict_list(event.get("source_refs"))
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
        role = string_or_none(payload.get("role"))
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
        key: deepcopy(value) for key, value in session.items() if key in allowed_fields
    }


def _text_from_content_blocks(value: object) -> str:
    return "\n".join(
        block_text
        for block in dict_list(value)
        if (block_text := string_or_none(block.get("text"))) is not None
    )


def _refs_within(
    record: dict[str, object], addresses: set[str]
) -> list[dict[str, object]]:
    """The record's `Event.Ref`s that survive a projection's event filter.

    A projection narrows the tape, so a reference to a dropped event must go
    with it; the surviving references keep their own coordinates untouched.
    """
    return [
        ref
        for ref in event_ref_list(record.get("event_refs"))
        if string_or_none(ref.get("event_address")) in addresses
    ]


def _filtered_model_runs(
    model_runs: list[dict[str, object]],
    *,
    addresses: set[str],
) -> list[dict[str, object]]:
    filtered: list[dict[str, object]] = []
    for model_run in model_runs:
        if not isinstance(model_run, dict):
            continue
        matching_refs = _refs_within(model_run, addresses)
        if not matching_refs:
            continue
        cleaned = deepcopy(model_run)
        cleaned.pop("reasoning_trace", None)
        cleaned["event_refs"] = deepcopy(matching_refs)
        filtered.append(cleaned)
    return filtered


def _filtered_tool_invocations(
    tool_invocations: list[dict[str, object]],
    *,
    addresses: set[str],
) -> list[dict[str, object]]:
    filtered: list[dict[str, object]] = []
    for tool_invocation in tool_invocations:
        if not isinstance(tool_invocation, dict):
            continue
        matching_refs = _refs_within(tool_invocation, addresses)
        if not matching_refs:
            continue
        cleaned = deepcopy(tool_invocation)
        cleaned.pop("result", None)
        cleaned.pop("output", None)
        cleaned["event_refs"] = deepcopy(matching_refs)
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
        tool_invocation_ref = string_or_none(cleaned.get("tool_invocation_ref"))
        if (
            tool_invocation_ref is not None
            and tool_invocation_ref not in tool_invocation_ids
        ):
            cleaned.pop("tool_invocation_ref", None)
        filtered.append(cleaned)
    return filtered


def _message_visibility_from_event(event: dict[str, object]) -> str:
    return (
        "conversation"
        if _event_surface(event, "transcript") == "visible"
        else "context"
    )


def _event_message_role(event: dict[str, object]) -> str | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    return string_or_none(payload.get("role"))


def _event_surface(event: dict[str, object], surface_name: str) -> str | None:
    surfaces = event.get("surfaces")
    if not isinstance(surfaces, dict):
        return None
    return string_or_none(surfaces.get(surface_name))


def _event_addresses(events: list[dict[str, object]]) -> set[str]:
    return {
        address
        for event in events
        if isinstance(event, dict)
        and (address := string_or_none(event.get("event_address"))) is not None
    }


def _record_ids(records: list[dict[str, object]], *, id_key: str) -> set[str]:
    return {
        record_id
        for record in records
        if isinstance(record, dict)
        and (record_id := string_or_none(record.get(id_key))) is not None
    }


def _text_only_content_blocks(value: object) -> list[dict[str, object]]:
    blocks = dict_list(value)
    return [
        deepcopy(block)
        for block in blocks
        if string_or_none(block.get("type")) == "text"
        and string_or_none(block.get("text")) is not None
    ]
