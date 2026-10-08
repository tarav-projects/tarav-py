"""Structured queries over one Chatlas Normal Model."""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Protocol

JsonObject = dict[str, Any]
_HASH_PREFIX = re.compile(r"[0-9a-f]{1,64}")
_FULL_HASH = re.compile(r"[0-9a-f]{64}")


class ChatlasQueryError(ValueError):
    pass


class ChatlasQueryReader(Protocol):
    def model_header(self) -> JsonObject: ...

    def iter_events(self) -> Iterator[JsonObject]: ...

    def iter_turns(self) -> Iterator[JsonObject]: ...

    def iter_messages(self) -> Iterator[JsonObject]: ...


@dataclass(frozen=True, slots=True)
class ChatlasQuery:
    turn_hash_prefixes: tuple[str, ...] = ()
    side: str | None = None
    text_contains: str | None = None
    order: str = "oldest"
    limit: int = 50

    def __post_init__(self) -> None:
        for prefix in self.turn_hash_prefixes:
            if _HASH_PREFIX.fullmatch(prefix) is None:
                raise ChatlasQueryError(
                    "Turn-hash prefix must be 1 to 64 lowercase hexadecimal characters"
                )
        if self.side not in {None, "user", "agent"}:
            raise ChatlasQueryError("Chatlas Query side must be user or agent")
        if self.text_contains is not None and not self.text_contains:
            raise ChatlasQueryError("Chatlas Query text must not be empty")
        if self.order not in {"oldest", "newest"}:
            raise ChatlasQueryError("Chatlas Query order must be oldest or newest")
        if self.limit < 1:
            raise ChatlasQueryError("Chatlas Query limit must be positive")
        if self.turn_hash_prefixes and (
            self.side is not None
            or self.text_contains is not None
            or self.order != "oldest"
            or self.limit != 50
        ):
            raise ChatlasQueryError(
                "Turn-hash prefixes cannot be combined with discovery options"
            )

    def to_dict(self) -> JsonObject:
        return {
            "turn_hash_prefixes": list(self.turn_hash_prefixes),
            "side": self.side,
            "text_contains": self.text_contains,
            "order": self.order,
            "limit": self.limit,
        }


@dataclass(frozen=True, slots=True)
# tarav.breadcrumb 2dc9224fb6c140d75772053bcc581dd0794f9157464ad4eaef81b7d74f94f2a8
class ChatlasTurnMatch:
    prefix: str
    turn: JsonObject
    messages: tuple[JsonObject, ...]
    started_at: str | None = None

    def to_dict(self) -> JsonObject:
        return {
            "prefix": self.prefix,
            "turn": deepcopy(self.turn),
            "messages": deepcopy(list(self.messages)),
            "started_at": self.started_at,
        }


@dataclass(frozen=True, slots=True)
class ChatlasQueryResult:
    query: ChatlasQuery
    session: JsonObject
    matches: tuple[ChatlasTurnMatch, ...]

    def to_dict(self) -> JsonObject:
        return {
            "query": self.query.to_dict(),
            "session": deepcopy(self.session),
            "matches": [item.to_dict() for item in self.matches],
        }


@dataclass(frozen=True, slots=True)
class ChatlasQueryEngine:
    reader: ChatlasQueryReader

    def run(self, query: ChatlasQuery) -> ChatlasQueryResult:
        turns: list[JsonObject] = []
        for turn in self.reader.iter_turns():
            _full_hash(turn.get("turn_hash"), field="Chat.Turn.turn_hash")
            turns.append(turn)

        if query.turn_hash_prefixes:
            selected = _select_exact_turns(turns, query.turn_hash_prefixes)
        else:
            selected = _select_discovery_turns(turns, query)

        requested_addresses = {
            _message_ref(ref)[0]
            for turn in selected
            for ref in _array(turn.get("message_refs"), field="Chat.Turn.message_refs")
        }
        messages: dict[str, JsonObject] = {}
        for message in self.reader.iter_messages():
            address = _full_hash(
                message.get("message_address"), field="Chat.Message.message_address"
            )
            if address not in requested_addresses:
                continue
            if address in messages:
                raise ChatlasQueryError(
                    f"Normal Model contains duplicate Chat.Message address: {address}"
                )
            messages[address] = message

        requested_event_addresses = {
            _event_ref(ref)[0]
            for turn in selected
            for ref in _array(turn.get("event_refs"), field="Chat.Turn.event_refs")
        }
        events: dict[str, JsonObject] = {}
        if requested_event_addresses:
            for event in self.reader.iter_events():
                address = _full_hash(
                    event.get("event_address"), field="Chat.Event.event_address"
                )
                if address not in requested_event_addresses:
                    continue
                if address in events:
                    raise ChatlasQueryError(
                        f"Normal Model contains duplicate Chat.Event address: {address}"
                    )
                events[address] = event

        matches = [
            ChatlasTurnMatch(
                prefix,
                turn,
                _messages_for_turn(turn, messages),
                _started_at_for_turn(turn, events),
            )
            for prefix, turn in _match_inputs(query, selected)
        ]
        if not query.turn_hash_prefixes:
            matches = _filter_discovery_text(matches, query)
        header = self.reader.model_header()
        session = header.get("session")
        if not isinstance(session, dict):
            raise ChatlasQueryError("Normal Model header has no Session")
        return ChatlasQueryResult(query, deepcopy(session), tuple(matches))


def _select_exact_turns(
    turns: list[JsonObject], prefixes: tuple[str, ...]
) -> list[JsonObject]:
    matched: list[list[JsonObject]] = [[] for _prefix in prefixes]
    for turn in turns:
        digest = _full_hash(turn.get("turn_hash"), field="Chat.Turn.turn_hash")
        for index, prefix in enumerate(prefixes):
            if digest.startswith(prefix):
                matched[index].append(turn)

    selected: list[JsonObject] = []
    for prefix, matches in zip(prefixes, matched, strict=True):
        if not matches:
            raise ChatlasQueryError(f"Turn-hash prefix does not match a Turn: {prefix}")
        if len(matches) != 1:
            raise ChatlasQueryError(
                f"Turn-hash prefix {prefix} matches {len(matches)} Turns"
            )
        selected.append(matches[0])
    return selected


def _match_inputs(
    query: ChatlasQuery, selected: list[JsonObject]
) -> Iterator[tuple[str, JsonObject]]:
    if query.turn_hash_prefixes:
        yield from zip(query.turn_hash_prefixes, selected, strict=True)
        return
    for turn in selected:
        digest = _full_hash(turn.get("turn_hash"), field="Chat.Turn.turn_hash")
        yield digest[:16], turn


def _select_discovery_turns(
    turns: list[JsonObject], query: ChatlasQuery
) -> list[JsonObject]:
    selected = turns
    if query.side is not None:
        selected = [item for item in selected if item.get("side") == query.side]
    if query.order == "newest":
        selected = list(reversed(selected))
    if query.text_contains is None:
        return selected[: query.limit]
    return selected


def _filter_discovery_text(
    matches: list[ChatlasTurnMatch], query: ChatlasQuery
) -> list[ChatlasTurnMatch]:
    if query.text_contains is None:
        return matches
    needle = query.text_contains.casefold()
    selected = [
        item
        for item in matches
        if needle
        in "\n".join(
            text
            for message in item.messages
            if isinstance((text := message.get("text")), str)
        ).casefold()
    ]
    return selected[: query.limit]


def _messages_for_turn(
    turn: JsonObject, messages: dict[str, JsonObject]
) -> tuple[JsonObject, ...]:
    resolved: list[JsonObject] = []
    for value in _array(turn.get("message_refs"), field="Chat.Turn.message_refs"):
        address, expected_hash = _message_ref(value)
        message = messages.get(address)
        if message is None:
            raise ChatlasQueryError(f"Chat.Message does not resolve: {address}")
        current_hash = _full_hash(
            message.get("message_hash"), field="Chat.Message.message_hash"
        )
        if current_hash != expected_hash:
            raise ChatlasQueryError(f"Chat.Message was amended: {address}")
        if message.get("side") != turn.get("side"):
            raise ChatlasQueryError(
                f"Chat.Message side disagrees with Chat.Turn: {address}"
            )
        resolved.append(message)
    return tuple(resolved)


def _message_ref(value: object) -> tuple[str, str]:
    if not isinstance(value, dict):
        raise ChatlasQueryError("Chat.Turn Message.Ref must be an object")
    return (
        _full_hash(value.get("message_address"), field="Message.Ref.message_address"),
        _full_hash(value.get("message_hash"), field="Message.Ref.message_hash"),
    )


def _started_at_for_turn(
    turn: JsonObject, events: dict[str, JsonObject]
) -> str | None:
    candidates: list[tuple[datetime, str]] = []
    for value in _array(turn.get("event_refs"), field="Chat.Turn.event_refs"):
        address, expected_hash = _event_ref(value)
        event = events.get(address)
        if event is None:
            raise ChatlasQueryError(f"Chat.Event does not resolve: {address}")
        current_hash = _full_hash(event.get("event_hash"), field="Chat.Event.event_hash")
        if current_hash != expected_hash:
            raise ChatlasQueryError(f"Chat.Event was amended: {address}")
        started_at = event.get("started_at")
        parsed = _parse_timestamp(started_at)
        if parsed is not None:
            candidates.append((parsed, started_at))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def _event_ref(value: object) -> tuple[str, str]:
    if not isinstance(value, dict):
        raise ChatlasQueryError("Chat.Turn Event.Ref must be an object")
    return (
        _full_hash(value.get("event_address"), field="Event.Ref.event_address"),
        _full_hash(value.get("event_hash"), field="Event.Ref.event_hash"),
    )


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _array(value: object, *, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ChatlasQueryError(f"{field} must be an array")
    return value


def _full_hash(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _FULL_HASH.fullmatch(value) is None:
        raise ChatlasQueryError(f"{field} must be a full lowercase SHA-256 digest")
    return value


__all__ = [
    "ChatlasQuery",
    "ChatlasQueryEngine",
    "ChatlasQueryError",
    "ChatlasQueryResult",
    "ChatlasTurnMatch",
]
