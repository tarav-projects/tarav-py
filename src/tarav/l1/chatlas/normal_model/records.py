"""Registered semantic Record Types in the Chatlas Normal Model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from tarav.l0.kernel import TaravClass, entity
from tarav.l0.kernel import TaravObject, TypeShip
from tarav.l1.chatlas.identity import CHATLAS_WORKFLOW_SHIP


_DIGEST_PATTERN = r"^[0-9a-f]{64}$"


class _ClosedRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class EventRef(_ClosedRecord):
    event_address: str = Field(pattern=_DIGEST_PATTERN)
    event_hash: str = Field(pattern=_DIGEST_PATTERN)


class MessageRef(_ClosedRecord):
    message_address: str = Field(pattern=_DIGEST_PATTERN)
    message_hash: str = Field(pattern=_DIGEST_PATTERN)


class SourceRef(_ClosedRecord):
    source_id: str = Field(min_length=1)
    record_index: int = Field(ge=1)
    line: int = Field(ge=1)


class EventObservation(_ClosedRecord):
    observed_at: str = Field(min_length=1)
    source_ref: SourceRef


class EventContent(_ClosedRecord):
    text: str


class _EventRecordInterface(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid")

    event_address: str = Field(pattern=_DIGEST_PATTERN)
    event_hash: str = Field(pattern=_DIGEST_PATTERN)
    started_at: str = Field(min_length=1)
    observations: list[EventObservation] = Field(min_length=1)
    opaque_payload_hash: str = Field(pattern=_DIGEST_PATTERN)
    content: EventContent | None = None


class UserEvent(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('5bf21365-a923-404e-a0bc-6daad8a97a02'),
            name='User.Event',
            workflow=CHATLAS_WORKFLOW_SHIP,
        )

    class RecordInterface(_EventRecordInterface):
        type: Literal["User.Event"]
        origin: Literal["user"]

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return _event_example(entity(cls).name, "user")


class AgentEvent(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('21e8a9ca-4eea-4a30-b010-218eb7f07eb1'),
            name='Agent.Event',
            workflow=CHATLAS_WORKFLOW_SHIP,
        )

    class RecordInterface(_EventRecordInterface):
        type: Literal["Agent.Event"]
        origin: Literal["agent"]

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return _event_example(entity(cls).name, "agent")


class UnresolvedEvent(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('ce6bdc18-f53d-4627-9a1a-b767581e396a'),
            name='Unresolved.Event',
            workflow=CHATLAS_WORKFLOW_SHIP,
        )

    class RecordInterface(_EventRecordInterface):
        type: Literal["Unresolved.Event"]
        origin: Literal["unresolved"]

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return _event_example(entity(cls).name, "unresolved")


class ChatMessage(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('53fbe2e4-6c51-4918-8f40-c7c14b70ba5f'),
            name='Chat.Message',
            workflow=CHATLAS_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal["Chat.Message"]
        message_address: str = Field(pattern=_DIGEST_PATTERN)
        message_hash: str = Field(pattern=_DIGEST_PATTERN)
        side: Literal["user", "agent"]
        text: str
        event_refs: list[EventRef] = Field(min_length=1)

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {
            "type": entity(cls).name,
            "message_address": "3" * 64,
            "message_hash": "4" * 64,
            "side": "user",
            "text": "Example Chatlas message.",
            "event_refs": [_event_ref_example()],
        }


class ChatTurn(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('6e7b53d7-590d-4423-bb16-5ec264cfb16d'),
            name='Chat.Turn',
            workflow=CHATLAS_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal["Chat.Turn"]
        turn_address: str = Field(pattern=_DIGEST_PATTERN)
        turn_hash: str = Field(pattern=_DIGEST_PATTERN)
        side: Literal["user", "agent"]
        event_refs: list[EventRef] = Field(min_length=1)
        message_refs: list[MessageRef]

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {
            "type": entity(cls).name,
            "turn_address": "5" * 64,
            "turn_hash": "6" * 64,
            "side": "user",
            "event_refs": [_event_ref_example()],
            "message_refs": [
                {"message_address": "3" * 64, "message_hash": "4" * 64}
            ],
        }


class AgentLoadedContext(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('67fee5e3-92ba-48cd-a561-bb3c82c99e20'),
            name='Agent.Loaded.Context',
            workflow=CHATLAS_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal["Agent.Loaded.Context"]
        agent_event_ref: EventRef
        event_refs: list[EventRef] = Field(min_length=1)

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {
            "type": entity(cls).name,
            "agent_event_ref": _event_ref_example(),
            "event_refs": [_event_ref_example()],
        }


def _event_ref_example() -> dict[str, str]:
    return {"event_address": "1" * 64, "event_hash": "2" * 64}


def _event_example(label: str, origin: str) -> dict[str, object]:
    return {
        "type": label,
        **_event_ref_example(),
        "started_at": "2026-01-01T00:00:00Z",
        "origin": origin,
        "observations": [
            {
                "observed_at": "2026-01-01T00:00:00Z",
                "source_ref": {
                    "source_id": "source-example",
                    "record_index": 1,
                    "line": 1,
                },
            }
        ],
        "opaque_payload_hash": "0" * 64,
    }


EVENT_RECORD_TYPES = {
    entity(record_type).name: record_type
    for record_type in (UserEvent, AgentEvent, UnresolvedEvent)
}

CHATLAS_SEMANTIC_RECORD_TYPES = (
    UserEvent,
    AgentEvent,
    UnresolvedEvent,
    ChatMessage,
    ChatTurn,
    AgentLoadedContext,
)


def event_record(value: object) -> TaravObject:
    if not isinstance(value, dict):
        raise ValueError("Chatlas Event Record must be an object")
    label = value.get("type")
    record_type = EVENT_RECORD_TYPES.get(label) if isinstance(label, str) else None
    if record_type is None:
        raise ValueError(f"unknown Chatlas Event Type: {label!r}")
    return record_type.from_record(value)


__all__ = [
    "AgentEvent",
    "AgentLoadedContext",
    "CHATLAS_SEMANTIC_RECORD_TYPES",
    "ChatMessage",
    "ChatTurn",
    "EVENT_RECORD_TYPES",
    "UnresolvedEvent",
    "UserEvent",
    "event_record",
]
