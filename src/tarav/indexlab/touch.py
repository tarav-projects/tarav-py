# $kw: --from User.Touched --from Event.Ref
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Literal, Protocol, TypeVar

from tarav.chatlas.lossless import (
    compute_normal_model,
    list_chat_messages,
    list_chat_turns,
    resolve_chat_message_ref,
    resolve_chat_turn_ref,
)

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
        addressed = [turn for turn in turns if turn.turn_ref.address == context.horizon.address]
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
                    {"side": message.side, "text": message.text}
                    for message in messages
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


class ChatlasTouchSource:
    """Read-only adapter from Chatlas Normal Models to IndexLab touch primitives."""

    def __init__(self, *, chatlas_root: Path | None = None) -> None:
        self.chatlas_root = chatlas_root
        self._models: dict[str, dict[str, object]] = {}

    def _model(self, session: str) -> dict[str, object]:
        if session not in self._models:
            self._models[session] = compute_normal_model(
                identity_hash=session,
                chatlas_root=self.chatlas_root,
            )
        return self._models[session]

    def resolve_context(self, context: RecordContext) -> Resolution[TouchContext]:
        model = self._model(context.session)
        turns = list_chat_turns(model)
        resolution = resolve_chat_turn_ref(
            turns,
            {
                "turn_address": context.horizon.address,
                "turn_hash": context.horizon.hash,
            },
        )
        standing = resolution["standing"]
        turn = resolution["turn"]
        if standing == "MISSING":
            return Resolution(standing="MISSING", value=None)
        if not isinstance(turn, dict):
            return Resolution(
                standing="MALFORMED",
                value=None,
                detail=f"resolved horizon {context.horizon.address} is not a turn object",
            )
        horizon_ordinal = next(
            index
            for index, candidate in enumerate(turns, start=1)
            if candidate.get("turn_address") == turn.get("turn_address")
        )
        visible: list[str] = []
        for candidate in turns[:horizon_ordinal]:
            visible.extend(_turn_message_addresses(candidate))
        return Resolution(
            standing="MATCHED" if standing == "MATCHED" else "AMENDED",
            value=TouchContext(
                session=context.session,
                horizon=TurnRef(
                    address=str(turn["turn_address"]),
                    hash=str(turn["turn_hash"]),
                ),
                horizon_ordinal=horizon_ordinal,
                visible_message_addresses=tuple(visible),
            ),
        )

    def resolve_message(
        self,
        session: str,
        ref: MessageRef,
    ) -> Resolution[TouchMessage]:
        model = self._model(session)
        messages = list_chat_messages(model)
        resolution = resolve_chat_message_ref(
            messages,
            {"message_address": ref.address, "message_hash": ref.hash},
        )
        standing = resolution["standing"]
        message = resolution["message"]
        if standing == "MISSING":
            return Resolution(standing="MISSING", value=None)
        if not isinstance(message, dict):
            return Resolution(
                standing="MALFORMED",
                value=None,
                detail=f"resolved message {ref.address} is not a message object",
            )
        turns = list_chat_turns(model)
        address = message.get("message_address")
        containing = [
            (index, turn)
            for index, turn in enumerate(turns, start=1)
            if address in _turn_message_addresses(turn)
        ]
        if len(containing) != 1:
            return Resolution(
                standing="MALFORMED",
                value=None,
                detail=(
                    f"message {address} belongs to {len(containing)} turns; "
                    "exactly one containing turn is required"
                ),
            )
        turn_ordinal, turn = containing[0]
        side = message.get("side")
        text = message.get("text")
        if side not in {"user", "agent"}:
            return Resolution(
                standing="MALFORMED",
                value=None,
                detail=f"message {address} carries unusable side {side!r}",
            )
        if not isinstance(text, str):
            return Resolution(
                standing="MALFORMED",
                value=None,
                detail=f"message {address} carries non-text body",
            )
        return Resolution(
            standing="MATCHED" if standing == "MATCHED" else "AMENDED",
            value=TouchMessage(
                session=session,
                ref=MessageRef(
                    address=str(message["message_address"]),
                    hash=str(message["message_hash"]),
                ),
                turn_ref=TurnRef(
                    address=str(turn["turn_address"]),
                    hash=str(turn["turn_hash"]),
                ),
                turn_ordinal=turn_ordinal,
                side=side,
                text=text,
            ),
        )


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _turn_message_addresses(turn: dict[str, object]) -> tuple[str, ...]:
    addresses = turn.get("message_addresses")
    if isinstance(addresses, list):
        return tuple(value for value in addresses if isinstance(value, str))
    refs = turn.get("message_refs")
    if not isinstance(refs, list):
        return ()
    return tuple(
        address
        for value in refs
        if isinstance(value, dict)
        and isinstance((address := value.get("message_address")), str)
    )


__all__ = [
    "ChatlasTouchSource",
    "Resolution",
    "ResolutionStanding",
    "Side",
    "TouchContext",
    "TouchMessage",
    "UserTouchMock",
    "UserTouchSource",
]
