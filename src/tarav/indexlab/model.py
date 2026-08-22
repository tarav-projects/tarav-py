# $kw: --from User.Touched --from Event.Ref
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping


RECORD_SCHEMA = "tarav.indexlab-record.v1"
JsonObject = dict[str, Any]


class RecordModelError(ValueError):
    """An IndexLab record does not conform to the recording-kernel shape."""


def _text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecordModelError(f"{field_name} must be a non-empty string")
    return value


def _object(value: object, *, field_name: str) -> JsonObject:
    if not isinstance(value, Mapping):
        raise RecordModelError(f"{field_name} must be an object")
    try:
        normalized = json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise RecordModelError(f"{field_name} must be JSON serializable: {exc}") from exc
    if not isinstance(normalized, dict):
        raise RecordModelError(f"{field_name} must be an object")
    return normalized


def _list(value: object, *, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise RecordModelError(f"{field_name} must be a list")
    return value


@dataclass(frozen=True, slots=True)
class MessageRef:
    address: str
    hash: str

    def __post_init__(self) -> None:
        _text(self.address, field_name="Message.Ref.address")
        _text(self.hash, field_name="Message.Ref.hash")

    def to_dict(self) -> JsonObject:
        return {"address": self.address, "hash": self.hash}

    @classmethod
    def from_dict(cls, value: object) -> MessageRef:
        data = _object(value, field_name="Message.Ref")
        return cls(
            address=_text(data.get("address"), field_name="Message.Ref.address"),
            hash=_text(data.get("hash"), field_name="Message.Ref.hash"),
        )


@dataclass(frozen=True, slots=True)
class TurnRef:
    address: str
    hash: str

    def __post_init__(self) -> None:
        _text(self.address, field_name="Turn.Ref.address")
        _text(self.hash, field_name="Turn.Ref.hash")

    def to_dict(self) -> JsonObject:
        return {"address": self.address, "hash": self.hash}

    @classmethod
    def from_dict(cls, value: object) -> TurnRef:
        data = _object(value, field_name="Turn.Ref")
        return cls(
            address=_text(data.get("address"), field_name="Turn.Ref.address"),
            hash=_text(data.get("hash"), field_name="Turn.Ref.hash"),
        )


@dataclass(frozen=True, slots=True)
class RecordContext:
    session: str
    horizon: TurnRef
    agent_sources: tuple[JsonObject, ...] = ()

    def __post_init__(self) -> None:
        _text(self.session, field_name="Record.Context.session")
        object.__setattr__(
            self,
            "agent_sources",
            tuple(
                _object(value, field_name="Record.Context.agent_sources member")
                for value in self.agent_sources
            ),
        )

    def to_dict(self) -> JsonObject:
        result: JsonObject = {
            "session": self.session,
            "horizon": self.horizon.to_dict(),
        }
        if self.agent_sources:
            result["agent_sources"] = list(self.agent_sources)
        return result

    @classmethod
    def from_dict(cls, value: object) -> RecordContext:
        data = _object(value, field_name="Record.Context")
        raw_sources = data.get("agent_sources", [])
        return cls(
            session=_text(data.get("session"), field_name="Record.Context.session"),
            horizon=TurnRef.from_dict(data.get("horizon")),
            agent_sources=tuple(
                _object(item, field_name="Record.Context.agent_sources member")
                for item in _list(
                    raw_sources,
                    field_name="Record.Context.agent_sources",
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class EvidenceNeighborhood:
    session: str
    grounding: tuple[MessageRef, ...]
    context: tuple[MessageRef, ...] = ()

    def __post_init__(self) -> None:
        _text(self.session, field_name="Evidence.Neighborhood.session")

    def to_dict(self) -> JsonObject:
        result: JsonObject = {
            "session": self.session,
            "grounding": [ref.to_dict() for ref in self.grounding],
        }
        if self.context:
            result["context"] = [ref.to_dict() for ref in self.context]
        return result

    @classmethod
    def from_dict(cls, value: object) -> EvidenceNeighborhood:
        data = _object(value, field_name="Evidence.Neighborhood")
        return cls(
            session=_text(
                data.get("session"), field_name="Evidence.Neighborhood.session"
            ),
            grounding=tuple(
                MessageRef.from_dict(item)
                for item in _list(
                    data.get("grounding", []),
                    field_name="Evidence.Neighborhood.grounding",
                )
            ),
            context=tuple(
                MessageRef.from_dict(item)
                for item in _list(
                    data.get("context", []),
                    field_name="Evidence.Neighborhood.context",
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class SupportSet:
    neighborhoods: tuple[EvidenceNeighborhood, ...]

    def to_dict(self) -> JsonObject:
        return {
            "neighborhoods": [item.to_dict() for item in self.neighborhoods]
        }

    @classmethod
    def from_dict(cls, value: object) -> SupportSet:
        data = _object(value, field_name="Support.Set")
        return cls(
            neighborhoods=tuple(
                EvidenceNeighborhood.from_dict(item)
                for item in _list(
                    data.get("neighborhoods", []),
                    field_name="Support.Set.neighborhoods",
                )
            )
        )


@dataclass(frozen=True, slots=True)
class Operation:
    type: str
    parameters: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text(self.type, field_name="Record.Operation.type")
        object.__setattr__(
            self,
            "parameters",
            _object(self.parameters, field_name="Record.Operation.parameters"),
        )

    def to_dict(self) -> JsonObject:
        return {"type": self.type, "parameters": self.parameters}

    @classmethod
    def from_dict(cls, value: object) -> Operation:
        data = _object(value, field_name="Record.Operation")
        return cls(
            type=_text(data.get("type"), field_name="Record.Operation.type"),
            parameters=_object(
                data.get("parameters", {}),
                field_name="Record.Operation.parameters",
            ),
        )


@dataclass(frozen=True, slots=True)
class IndexRecord:
    id: str
    ordinal: int
    context: RecordContext
    operation: Operation
    support: SupportSet
    assertions: tuple[JsonObject, ...] = ()

    def __post_init__(self) -> None:
        _text(self.id, field_name="Index.Record.id")
        if not isinstance(self.ordinal, int) or isinstance(self.ordinal, bool):
            raise RecordModelError("Index.Record.ordinal must be an integer")
        if self.ordinal < 0:
            raise RecordModelError("Index.Record.ordinal must not be negative")
        object.__setattr__(
            self,
            "assertions",
            tuple(
                _object(value, field_name="Index.Record.assertions member")
                for value in self.assertions
            ),
        )

    def to_dict(self) -> JsonObject:
        return {
            "schema": RECORD_SCHEMA,
            "id": self.id,
            "ordinal": self.ordinal,
            "context": self.context.to_dict(),
            "operation": self.operation.to_dict(),
            "support": self.support.to_dict(),
            "assertions": list(self.assertions),
        }

    @classmethod
    def from_dict(cls, value: object) -> IndexRecord:
        data = _object(value, field_name="Index.Record")
        schema = data.get("schema", RECORD_SCHEMA)
        if schema != RECORD_SCHEMA:
            raise RecordModelError(f"unsupported Index.Record schema: {schema!r}")
        ordinal = data.get("ordinal", 0)
        if not isinstance(ordinal, int) or isinstance(ordinal, bool):
            raise RecordModelError("Index.Record.ordinal must be an integer")
        return cls(
            id=_text(data.get("id"), field_name="Index.Record.id"),
            ordinal=ordinal,
            context=RecordContext.from_dict(data.get("context")),
            operation=Operation.from_dict(data.get("operation")),
            support=SupportSet.from_dict(data.get("support")),
            assertions=tuple(
                _object(item, field_name="Index.Record.assertions member")
                for item in _list(
                    data.get("assertions", []),
                    field_name="Index.Record.assertions",
                )
            ),
        )


__all__ = [
    "RECORD_SCHEMA",
    "EvidenceNeighborhood",
    "IndexRecord",
    "MessageRef",
    "Operation",
    "RecordContext",
    "RecordModelError",
    "SupportSet",
    "TurnRef",
]
