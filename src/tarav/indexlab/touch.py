# $kw: --from User.Touched --from Event.Ref
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Generic, Literal, Protocol, TypeVar

from .model import MessageRef, RecordContext, TurnRef


Side = Literal["user", "agent"]
ResolutionStanding = Literal["MATCHED", "AMENDED", "MISSING", "MALFORMED"]
T = TypeVar("T")


# $kw: --note [DC] absence and corruption are separate standings: missing means the reference does not resolve, malformed means it resolves but the stored material cannot be read as a touch primitive --note [CT] collapsing corruption into absence reports a dangling reference for material that is present, which sends maintenance after the wrong problem
@dataclass(frozen=True, slots=True)
class Resolution(Generic[T]):
    """One touch lookup outcome; `detail` carries why a malformed lookup failed."""

    standing: ResolutionStanding
    value: T | None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class TouchMessage:
    session: str
    ref: MessageRef
    turn_ref: TurnRef
    turn_ordinal: int
    side: Side
    text: str


@dataclass(frozen=True, slots=True)
class TouchContext:
    session: str
    horizon: TurnRef
    horizon_ordinal: int
    visible_message_addresses: tuple[str, ...]


class UserTouchSource(Protocol):
    def resolve_context(
        self,
        context: RecordContext,
    ) -> Resolution[TouchContext]: ...

    def resolve_message(
        self,
        session: str,
        ref: MessageRef,
    ) -> Resolution[TouchMessage]: ...


class UserTouchMock:
    """Deterministic in-memory Chat.Surface for recording-kernel tests."""

    def __init__(self) -> None:
        self._turns: dict[str, list[TouchMessage]] = {}

    def add_turn(self, session: str, side: Side, text: str) -> TouchMessage:
        if side not in {"user", "agent"}:
            raise ValueError("User.Touch.Mock side must be 'user' or 'agent'")
        turns = self._turns.setdefault(session, [])
        ordinal = len(turns) + 1
        turn_ref = TurnRef(
            address=_digest(["turn", session, ordinal]),
            hash=_digest(["turn-state", session, ordinal, side, text]),
        )
        message = TouchMessage(
            session=session,
            ref=MessageRef(
                address=_digest(["message", session, ordinal]),
                hash=_digest(["message-state", session, ordinal, side, text]),
            ),
            turn_ref=turn_ref,
            turn_ordinal=ordinal,
            side=side,
            text=text,
        )
        turns.append(message)
        return message

    def record_context(self, session: str, horizon: TurnRef) -> RecordContext:
        return RecordContext(session=session, horizon=horizon)

    def resolve_context(self, context: RecordContext) -> Resolution[TouchContext]:
        turns = self._turns.get(context.session, [])
        addressed = [
            turn for turn in turns if turn.turn_ref.address == context.horizon.address
        ]
        if not addressed:
            return Resolution(standing="MISSING", value=None)
        horizon = addressed[0]
        visible = tuple(
            turn.ref.address
            for turn in turns
            if turn.turn_ordinal <= horizon.turn_ordinal
        )
        standing: ResolutionStanding = (
            "MATCHED" if horizon.turn_ref.hash == context.horizon.hash else "AMENDED"
        )
        return Resolution(
            standing=standing,
            value=TouchContext(
                session=context.session,
                horizon=horizon.turn_ref,
                horizon_ordinal=horizon.turn_ordinal,
                visible_message_addresses=visible,
            ),
        )

    def resolve_message(
        self,
        session: str,
        ref: MessageRef,
    ) -> Resolution[TouchMessage]:
        addressed = [
            message
            for message in self._turns.get(session, [])
            if message.ref.address == ref.address
        ]
        if not addressed:
            return Resolution(standing="MISSING", value=None)
        message = addressed[0]
        standing: ResolutionStanding = (
            "MATCHED" if message.ref.hash == ref.hash else "AMENDED"
        )
        return Resolution(standing=standing, value=message)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "tarav.indexlab-user-touch-mock.v1",
            "sessions": {
                session: [
                    {"side": message.side, "text": message.text} for message in messages
                ]
                for session, messages in sorted(self._turns.items())
            },
        }

    @classmethod
    def from_dict(cls, value: object) -> UserTouchMock:
        if not isinstance(value, dict) or value.get("schema") != (
            "tarav.indexlab-user-touch-mock.v1"
        ):
            raise ValueError("unsupported User.Touch.Mock document")
        sessions = value.get("sessions")
        if not isinstance(sessions, dict):
            raise ValueError("User.Touch.Mock sessions must be an object")
        source = cls()
        for session, raw_messages in sessions.items():
            if not isinstance(session, str) or not isinstance(raw_messages, list):
                raise ValueError("invalid User.Touch.Mock session")
            for raw in raw_messages:
                if not isinstance(raw, dict):
                    raise ValueError("invalid User.Touch.Mock turn")
                side = raw.get("side")
                text = raw.get("text")
                if side not in {"user", "agent"} or not isinstance(text, str):
                    raise ValueError("invalid User.Touch.Mock turn")
                source.add_turn(session, side, text)
        return source


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "Resolution",
    "ResolutionStanding",
    "Side",
    "TouchContext",
    "TouchMessage",
    "UserTouchMock",
    "UserTouchSource",
]
