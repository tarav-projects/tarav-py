# $kw: ^chatlas2-turns --from Event.Annotation --from Event.Ref --note [CT] resolved-origin event runs form shallow conservative Chat.Turn envelopes; unresolved events remain ungrouped --supp ^d20260816-22u ^d20260816-23u ^d20260816-24u ^d20260816-25u ^d20260816-26u ^d20260816-28u
from __future__ import annotations

from copy import deepcopy
from typing import Literal

from tarav._core.errors import CliError

from .model import JsonObject
from .turn_ref import compute_chat_turn_address


TurnSide = Literal["user", "agent"]


def build_chat_turn_candidates(
    *,
    provider: str,
    scope: str,
    events: list[JsonObject],
    chat_messages: list[JsonObject],
) -> tuple[JsonObject, ...]:
    message_by_event: dict[str, list[JsonObject]] = {}
    for message in chat_messages:
        addresses = message.get("event_addresses")
        if not isinstance(addresses, list) or not addresses:
            raise CliError("Chatlas2 Chat.Message has no event-address membership")
        for address in addresses:
            if not isinstance(address, str):
                raise CliError("Chatlas2 Chat.Message has an invalid event place")
            message_by_event.setdefault(address, []).append(message)

    turns: list[JsonObject] = []
    run: list[JsonObject] = []
    run_side: TurnSide | None = None

    def flush() -> None:
        nonlocal run, run_side
        if not run or run_side is None:
            run = []
            run_side = None
            return
        event_addresses = [str(event["event_address"]) for event in run]
        event_address_set = set(event_addresses)
        messages: list[JsonObject] = []
        seen_messages: set[str] = set()
        for address in event_addresses:
            for message in message_by_event.get(address, []):
                message_address = str(message["message_address"])
                if message_address in seen_messages:
                    continue
                member_addresses = message.get("event_addresses")
                if not isinstance(member_addresses, list) or not set(
                    str(value) for value in member_addresses
                ).issubset(event_address_set):
                    raise CliError("Chatlas2 Chat.Message crosses Chat.Turn boundaries")
                if message.get("side") != run_side:
                    raise CliError(
                        "Chatlas2 Chat.Message side disagrees with Chat.Turn"
                    )
                seen_messages.add(message_address)
                messages.append(message)
        turns.append(
            {
                "class": "Chat.Turn",
                "turn_address": compute_chat_turn_address(
                    provider=provider,
                    scope=scope,
                    place={"first_event_address": event_addresses[0]},
                ),
                "side": run_side,
                "event_addresses": event_addresses,
                "message_addresses": [
                    str(message["message_address"]) for message in messages
                ],
            }
        )
        run = []
        run_side = None

    for event in events:
        origin = event.get("origin")
        if origin not in {"user", "agent"}:
            flush()
            continue
        if run_side is not None and origin != run_side:
            flush()
        run_side = origin
        run.append(event)
    flush()
    return tuple(deepcopy(turns))


def list_chat_turns(
    model: JsonObject,
    *,
    side: TurnSide | None = None,
) -> list[JsonObject]:
    if side not in {None, "user", "agent"}:
        raise ValueError("Chat.Turn side must be 'user' or 'agent'")
    annotations = model.get("annotations")
    raw = annotations.get("chat_turns") if isinstance(annotations, dict) else None
    if not isinstance(raw, list):
        return []
    turns = [turn for turn in raw if isinstance(turn, dict)]
    if side is not None:
        turns = [turn for turn in turns if turn.get("side") == side]
    return deepcopy(turns)


__all__ = ["TurnSide", "build_chat_turn_candidates", "list_chat_turns"]
