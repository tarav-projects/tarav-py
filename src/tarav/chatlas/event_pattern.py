# $kw: ^event-pattern --from Chatlas.Query.Surface --from Chatlas.Session.Model --from Session.Event.Tape --note [DF] backend-neutral relational matching is evaluated authoritatively over normal-model message events ^c20260725-38u --supp Event.Ref replaces event_id at every query boundary ^c20260728-16u --supp alphanumeric and event-time turn discovery ^c20260731-12u --supp implementation authorized ^c20260731-14u
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal
import unicodedata

from tarav.chatlas._payload_helpers import (
    dict_list,
    int_or_none,
    parse_event_timestamp,
    string_or_none,
)
from tarav.chatlas.event_ref import (
    EventRefOutcome,
    event_ref,
    format_event_ref,
    resolve_event_ref,
)
from tarav.chatlas.normalization.session_model.messages import content_text
from tarav.chatlas.normalization.session_model.events import normal_turn_kind


Relation = Literal["next_turn"]
Selection = Literal["all", "first", "latest"]
Projection = Literal["match", "first", "last"]
Cardinality = Literal["many", "one", "zero-or-one"]

_PATTERN_KEYS = frozenset({"steps", "relation", "select", "project", "cardinality"})
_PREDICATE_KEYS = frozenset(
    {
        "role",
        "kind",
        "turn_kind",
        "producer_type",
        "event_ref",
        "text_exact",
        "text_contains",
        "text_regex",
        "text_alphanumeric_contains",
        "timestamp_after",
        "timestamp_before",
    }
)


class EventPatternError(ValueError):
    pass


@dataclass(frozen=True)
class EventPredicate:
    role: str | None = None
    kind: str | None = None
    turn_kind: str | None = None
    producer_type: str | None = None
    event_ref: dict[str, Any] | None = None
    text_exact: str | None = None
    text_contains: str | None = None
    text_regex: str | None = None
    text_alphanumeric_contains: str | None = None
    timestamp_after: str | None = None
    timestamp_before: str | None = None

    @classmethod
    def from_dict(cls, payload: object) -> EventPredicate:
        if not isinstance(payload, dict):
            raise EventPatternError("each event pattern step must be an object")
        unknown = set(payload) - _PREDICATE_KEYS
        if unknown:
            raise EventPatternError(
                f"unknown event predicate fields: {sorted(unknown)}"
            )
        if not payload:
            raise EventPatternError("event pattern steps cannot be empty")
        values: dict[str, Any] = {}
        for key, value in payload.items():
            if key == "event_ref":
                if not isinstance(value, dict):
                    raise EventPatternError(
                        "event predicate 'event_ref' must be an Event.Ref object"
                    )
                try:
                    format_event_ref(value)
                except ValueError as error:
                    raise EventPatternError(
                        f"event predicate 'event_ref' is invalid: {error}"
                    ) from error
                values[key] = dict(value)
                continue
            if not isinstance(value, str) or not value:
                raise EventPatternError(
                    f"event predicate {key!r} must be a non-empty string"
                )
            if key == "text_regex":
                try:
                    re.compile(value)
                except re.error as error:
                    raise EventPatternError(
                        f"event predicate 'text_regex' is invalid: {error}"
                    ) from error
            if key == "text_alphanumeric_contains" and not alphanumeric_material(
                value
            ):
                raise EventPatternError(
                    "event predicate 'text_alphanumeric_contains' must contain "
                    "at least one alphanumeric character"
                )
            if key in {"timestamp_after", "timestamp_before"}:
                if parse_event_timestamp(value) is None:
                    raise EventPatternError(
                        f"event predicate {key!r} must be an ISO 8601 timestamp"
                    )
            values[key] = value
        return cls(**values)


@dataclass(frozen=True)
class EventPattern:
    steps: tuple[EventPredicate, ...]
    relation: Relation = "next_turn"
    select: Selection = "all"
    project: Projection = "match"
    cardinality: Cardinality = "many"

    @classmethod
    def from_dict(cls, payload: object) -> EventPattern:
        if not isinstance(payload, dict):
            raise EventPatternError("event pattern must be an object")
        unknown = set(payload) - _PATTERN_KEYS
        if unknown:
            raise EventPatternError(f"unknown event pattern fields: {sorted(unknown)}")
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise EventPatternError("event pattern steps must be a non-empty array")

        relation = _choice(payload, "relation", "next_turn", {"next_turn"})
        select = _choice(payload, "select", "all", {"all", "first", "latest"})
        project = _choice(payload, "project", "match", {"match", "first", "last"})
        cardinality = _choice(
            payload,
            "cardinality",
            "many",
            {"many", "one", "zero-or-one"},
        )
        return cls(
            steps=tuple(EventPredicate.from_dict(step) for step in raw_steps),
            relation=relation,  # type: ignore[arg-type]
            select=select,  # type: ignore[arg-type]
            project=project,  # type: ignore[arg-type]
            cardinality=cardinality,  # type: ignore[arg-type]
        )


def evaluate_event_pattern(
    session_model: dict[str, Any],
    pattern: EventPattern,
) -> tuple[tuple[dict[str, Any], ...], ...]:
    matches = match_event_sequences(session_model, pattern)
    if pattern.select == "first":
        matches = matches[:1]
    elif pattern.select == "latest":
        matches = matches[-1:]

    _validate_cardinality(matches, pattern.cardinality)
    return tuple(_project_event_refs(match, pattern.project) for match in matches)


def match_event_sequences(
    session_model: dict[str, Any],
    pattern: EventPattern,
) -> tuple[tuple[dict[str, Any], ...], ...]:
    turns = visible_turn_events(session_model)
    width = len(pattern.steps)
    matches: list[tuple[dict[str, Any], ...]] = []
    for start in range(0, len(turns) - width + 1):
        candidate = tuple(turns[start : start + width])
        if all(
            _event_matches(event, predicate)
            for event, predicate in zip(candidate, pattern.steps, strict=True)
        ):
            matches.append(candidate)
    return tuple(matches)


def _choice(
    payload: dict[str, object],
    key: str,
    default: str,
    allowed: set[str],
) -> str:
    value = payload.get(key, default)
    if not isinstance(value, str) or value not in allowed:
        raise EventPatternError(
            f"event pattern {key!r} must be one of {sorted(allowed)}"
        )
    return value


def visible_turn_events(session_model: dict[str, Any]) -> list[dict[str, Any]]:
    chat = session_model.get("chat")
    if not isinstance(chat, dict):
        return []
    return [
        event
        for event in dict_list(chat.get("events"))
        if string_or_none(event.get("kind")) == "message"
        and int_or_none(event.get("sequence")) is not None
        and string_or_none(event.get("event_address")) is not None
        and normal_turn_kind(event) is not None
    ]


def _event_matches(event: dict[str, Any], predicate: EventPredicate) -> bool:
    if predicate.kind is not None and event.get("kind") != predicate.kind:
        return False
    if (
        predicate.turn_kind is not None
        and normal_turn_kind(event) != predicate.turn_kind
    ):
        return False
    if predicate.event_ref is not None:
        resolution = resolve_event_ref([event], predicate.event_ref)
        if resolution.outcome is not EventRefOutcome.MATCHED:
            return False
    payload = event.get("payload")
    role = string_or_none(payload.get("role")) if isinstance(payload, dict) else None
    if predicate.role is not None and role != predicate.role:
        return False
    producer = event.get("producer")
    producer_type = (
        string_or_none(producer.get("type")) if isinstance(producer, dict) else None
    )
    if (
        predicate.producer_type is not None
        and producer_type != predicate.producer_type
    ):
        return False
    text = event_text(event)
    if predicate.text_exact is not None and text != predicate.text_exact:
        return False
    if (
        predicate.text_contains is not None
        and predicate.text_contains.casefold() not in text.casefold()
    ):
        return False
    if predicate.text_regex is not None and re.search(predicate.text_regex, text) is None:
        return False
    if predicate.text_alphanumeric_contains is not None:
        needle = alphanumeric_material(predicate.text_alphanumeric_contains)
        if needle not in alphanumeric_material(text):
            return False
    event_at = None
    timestamp = string_or_none(event.get("timestamp"))
    if timestamp is not None:
        event_at = parse_event_timestamp(timestamp)
    if predicate.timestamp_after is not None:
        after = parse_event_timestamp(predicate.timestamp_after)
        if event_at is None or after is None or event_at < after:
            return False
    if predicate.timestamp_before is not None:
        before = parse_event_timestamp(predicate.timestamp_before)
        if event_at is None or before is None or event_at > before:
            return False
    return True


def alphanumeric_material(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in normalized if character.isalnum())


def event_text(event: dict[str, Any]) -> str:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return ""
    content = payload.get("content")
    if isinstance(content, list):
        return content_text(content)
    for key in ("text", "message"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def _project_event_refs(
    match: tuple[dict[str, Any], ...],
    projection: Projection,
) -> tuple[dict[str, Any], ...]:
    selected = match
    if projection == "first":
        selected = match[:1]
    elif projection == "last":
        selected = match[-1:]
    return tuple(event_ref(event) for event in selected)


def _validate_cardinality(
    matches: tuple[tuple[dict[str, Any], ...], ...],
    cardinality: Cardinality,
) -> None:
    if cardinality == "one" and len(matches) != 1:
        raise EventPatternError(
            f"event pattern expected exactly one match, found {len(matches)}"
        )
    if cardinality == "zero-or-one" and len(matches) > 1:
        raise EventPatternError(
            f"event pattern expected at most one match, found {len(matches)}"
        )


__all__ = [
    "EventPattern",
    "EventPatternError",
    "EventPredicate",
    "alphanumeric_material",
    "event_text",
    "evaluate_event_pattern",
    "match_event_sequences",
    "visible_turn_events",
]
