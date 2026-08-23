# $kw: --from User.Touched --note [DC] the kernel declares the touch port and Chatlas provides the adapter, so the Index kernel does not depend on the chat store it happens to resolve through
"""Chatlas-backed `UserTouchSource` for the IndexLab recording kernel."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .message_ref import resolve_chat_message_ref
from .messages import list_chat_messages
from .normal_model import compute_normal_model
from .turn_ref import resolve_chat_turn_ref
from .turns import list_chat_turns
from tarav.indexlab.model import MessageRef, RecordContext, TurnRef
from tarav.indexlab.touch import Resolution, TouchContext, TouchMessage


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


__all__ = ["ChatlasTouchSource"]
