"""Structured queries over one Chatlas Normal Model."""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any, Protocol

JsonObject = dict[str, Any]
_HASH_PREFIX = re.compile(r"[0-9a-f]{1,64}")
_FULL_HASH = re.compile(r"[0-9a-f]{64}")


class ChatlasQueryError(ValueError):
    pass


class ChatlasQueryReader(Protocol):
    def model_header(self) -> JsonObject: ...

    def iter_turns(self) -> Iterator[JsonObject]: ...

    def iter_messages(self) -> Iterator[JsonObject]: ...


@dataclass(frozen=True, slots=True)
class ChatlasQuery:
    turn_hash_prefixes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.turn_hash_prefixes:
            raise ChatlasQueryError("Chatlas Query requires a Turn-hash prefix")
        for prefix in self.turn_hash_prefixes:
            if _HASH_PREFIX.fullmatch(prefix) is None:
                raise ChatlasQueryError(
                    "Turn-hash prefix must be 1 to 64 lowercase hexadecimal characters"
                )

    def to_dict(self) -> JsonObject:
        return {
            "class": "Chatlas.Query",
            "turn_hash_prefixes": list(self.turn_hash_prefixes),
        }


@dataclass(frozen=True, slots=True)
class ChatlasTurnFinding:
    prefix: str
    turn: JsonObject
    messages: tuple[JsonObject, ...]

    def to_dict(self) -> JsonObject:
        return {
            "class": "Chatlas.Query.Turn.Finding",
            "prefix": self.prefix,
            "turn": deepcopy(self.turn),
            "messages": deepcopy(list(self.messages)),
        }


@dataclass(frozen=True, slots=True)
class ChatlasQueryResult:
    query: ChatlasQuery
    session: JsonObject
    findings: tuple[ChatlasTurnFinding, ...]

    def to_dict(self) -> JsonObject:
        return {
            "class": "Chatlas.Query.Result",
            "query": self.query.to_dict(),
            "session": deepcopy(self.session),
            "findings": [item.to_dict() for item in self.findings],
        }


@dataclass(frozen=True, slots=True)
class ChatlasQueryEngine:
    reader: ChatlasQueryReader

    def run(self, query: ChatlasQuery) -> ChatlasQueryResult:
        matched: list[list[JsonObject]] = [
            [] for _prefix in query.turn_hash_prefixes
        ]
        for turn in self.reader.iter_turns():
            digest = _full_hash(turn.get("turn_hash"), field="Chat.Turn.turn_hash")
            for index, prefix in enumerate(query.turn_hash_prefixes):
                if digest.startswith(prefix):
                    matched[index].append(turn)

        selected: list[JsonObject] = []
        for prefix, matches in zip(query.turn_hash_prefixes, matched, strict=True):
            if not matches:
                raise ChatlasQueryError(
                    f"Turn-hash prefix does not match a Turn: {prefix}"
                )
            if len(matches) != 1:
                raise ChatlasQueryError(
                    f"Turn-hash prefix {prefix} matches {len(matches)} Turns"
                )
            selected.append(matches[0])

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

        findings = tuple(
            ChatlasTurnFinding(
                prefix,
                turn,
                _messages_for_turn(turn, messages),
            )
            for prefix, turn in zip(query.turn_hash_prefixes, selected, strict=True)
        )
        header = self.reader.model_header()
        session = header.get("session")
        if not isinstance(session, dict):
            raise ChatlasQueryError("Normal Model header has no Session")
        return ChatlasQueryResult(query, deepcopy(session), findings)


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
    "ChatlasTurnFinding",
]
