# $kw: --from Chatlas.Filter
"""Chatlas.Filter: shape-preserving named operations on normal model objects.

A filter is `(model_object) -> model_object`: same class/shape out, content
reduced. Filters never mutate their input and never add or rename fields.

Coupling note: the `slim` key lists are a contract against the session-model
event envelope (schema v3); revisit them when the envelope gains keys.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from tarav._core.errors import CliError

from tarav.chatlas._payload_helpers import dict_list, string_or_none


_SLIM_EVENT_DROP = (
    "native",
    "source_refs",
    "lineage",
    "producer",
    "surfaces",
    "model_run_ref",
    "extras",
)

_SLIM_TOP_LEVEL_DROP = ("normalization", "sources")


def _slim(model: dict[str, Any]) -> dict[str, Any]:
    slimmed = {key: value for key, value in model.items() if key not in _SLIM_TOP_LEVEL_DROP}
    chat = slimmed.get("chat")
    if isinstance(chat, dict):
        chat = dict(chat)
        chat["events"] = [
            {key: value for key, value in event.items() if key not in _SLIM_EVENT_DROP}
            for event in dict_list(chat.get("events"))
        ]
        slimmed["chat"] = chat
    return slimmed


def _messages(model: dict[str, Any]) -> dict[str, Any]:
    from tarav.chatlas.normalization.session_model._views import _messages_from_events

    filtered = dict(model)
    chat = filtered.get("chat")
    if not isinstance(chat, dict):
        return filtered
    chat = dict(chat)
    events = [
        event
        for event in dict_list(chat.get("events"))
        if string_or_none(event.get("kind")) == "message"
    ]
    referenced_runs = {
        run_ref
        for event in events
        if (run_ref := string_or_none(event.get("model_run_ref"))) is not None
    }
    chat["events"] = events
    chat["messages"] = _messages_from_events(events)
    chat["model_runs"] = [
        run
        for run in dict_list(chat.get("model_runs"))
        if string_or_none(run.get("model_run_id")) in referenced_runs
    ]
    chat["tool_invocations"] = []
    chat["usage"] = [
        row
        for row in dict_list(chat.get("usage"))
        if string_or_none(row.get("model_run_ref")) in referenced_runs
    ]
    filtered["chat"] = chat
    return filtered


def _turns(model: dict[str, Any]) -> dict[str, Any]:
    return _slim(_messages(model))


def contains_filter(text: str) -> Callable[[list[dict[str, Any]]], list[dict[str, Any]]]:
    needle = text.casefold()

    def apply(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            event
            for event in events
            if needle in _event_text_blob(event).casefold()
        ]

    return apply


def role_filter(role: str) -> Callable[[list[dict[str, Any]]], list[dict[str, Any]]]:
    def apply(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [event for event in events if _event_message_role(event) == role]

    return apply


def around_filter(
    around: str,
    radius: int | None,
) -> Callable[[list[dict[str, Any]]], list[dict[str, Any]]]:
    from tarav.chatlas._payload_helpers import parse_event_timestamp

    target = parse_event_timestamp(around)
    if target is None:
        raise CliError(f"invalid chatlas views get --around timestamp: {around!r}")

    def apply(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        timestamped: list[tuple[float, int, dict[str, Any]]] = []
        for index, event in enumerate(events):
            timestamp_value = string_or_none(event.get("timestamp"))
            parsed = parse_event_timestamp(timestamp_value) if timestamp_value else None
            if parsed is None:
                continue
            timestamped.append((abs((parsed - target).total_seconds()), index, event))
        timestamped.sort(key=lambda item: (item[0], item[1]))
        if radius is not None:
            timestamped = timestamped[: 2 * radius + 1]

        timestamped.sort(key=lambda item: item[1])
        return [event for _, _, event in timestamped]

    return apply


def build_event_selection(
    *,
    contains: str | None,
    role: str | None,
    around: str | None,
    radius: int | None,
) -> tuple[Callable[[list[dict[str, Any]]], list[dict[str, Any]]], ...]:
    selection: list[Callable[[list[dict[str, Any]]], list[dict[str, Any]]]] = []
    if contains is not None:
        selection.append(contains_filter(contains))
    if role is not None:
        selection.append(role_filter(role))
    if around is not None:
        selection.append(around_filter(around, radius))
    return tuple(selection)


def _event_text_blob(event: dict[str, Any]) -> str:
    collected: list[str] = []
    _collect_event_texts(event.get("payload"), collected)
    return " ".join(collected)


def _collect_event_texts(value: object, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_event_texts(item, out)
    elif isinstance(value, list):
        for item in value:
            _collect_event_texts(item, out)


def _event_message_role(event: dict[str, Any]) -> str | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    return string_or_none(payload.get("role"))


CHATLAS_FILTERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "slim": _slim,
    "messages": _messages,
    "turns": _turns,
}


def apply_chatlas_filters(
    model: dict[str, Any],
    filter_names: tuple[str, ...],
) -> dict[str, Any]:
    if not filter_names:
        return model
    result = deepcopy(model)
    for name in filter_names:
        filter_fn = CHATLAS_FILTERS.get(name)
        if filter_fn is None:
            registered = ", ".join(sorted(CHATLAS_FILTERS))
            raise CliError(
                f"unknown chatlas filter: {name!r} (registered filters: {registered})"
            )
        result = filter_fn(result)
    return result


__all__ = ["CHATLAS_FILTERS", "apply_chatlas_filters"]
