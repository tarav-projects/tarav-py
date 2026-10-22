"""Retain exact cited Turns independently of replaceable Normal Model projections."""
# tarav.breadcrumb fa4091790df4

from hashlib import sha256
import json
from pathlib import Path
from typing import Literal

from pydantic import ConfigDict

from tarav.l0.kernel import FileRecord, TaravClass, TypeShip, TypedState, entity
from tarav.l1.records import RecordRegistry

from .identity import CHATLAS_WORKFLOW_SHIP
from .normal_model import (
    ChatMessage, ChatTurn, NormalModelSession, NormalModelSource,
    compute_event_hash, compute_chat_message_hash, compute_chat_turn_hash,
    event_record, resolve_event_ref, resolve_chat_message_ref,
)


class TurnSnapshot(TypedState, FileRecord):
    """The exact cited Turn and hash-checked supporting data, not a new current Turn."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("2790908d-39a0-46a4-8425-b870e7f4dd91"),
                          name="Tarav.Chatlas.TurnSnapshot", workflow=CHATLAS_WORKFLOW_SHIP)

    class RecordInterface(FileRecord.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal["Tarav.Chatlas.TurnSnapshot"]
        session: NormalModelSession
        sources: list[NormalModelSource]
        producer: str | None
        turn: ChatTurn.RecordInterface
        messages: list[ChatMessage.RecordInterface]
        events: list[dict]

    class Records(FileRecord.Records):
        def record_example(self):
            event = {"type": "User.Event", "origin": "user",
                     "event_address": "1" * 64, "started_at": "2026-01-01T00:00:00Z",
                     "opaque_payload_hash": "2" * 64, "content": {"text": "Example"},
                     "observations": [{"observed_at": "2026-01-01T00:00:00Z",
                                       "source_ref": {"source_id": "example", "record_index": 1, "line": 1}}]}
            event["event_hash"] = compute_event_hash(event)
            ref = {k: event[k] for k in ("event_address", "event_hash")}
            message = {"type": "Chat.Message", "side": "user", "text": "Example",
                       "message_address": "3" * 64, "event_refs": [ref]}
            message["message_hash"] = compute_chat_message_hash(message)
            turn = {"type": "Chat.Turn", "side": "user", "turn_address": "4" * 64,
                    "event_refs": [ref], "message_refs": [{k: message[k] for k in ("message_address", "message_hash")}]}
            turn["turn_hash"] = compute_chat_turn_hash(turn, opaque_payload_hashes=[event["opaque_payload_hash"]])
            return {"type": "Tarav.Chatlas.TurnSnapshot", "producer": None,
                    "session": {"provider": "codex", "session_id": "example", "identity_hash": "0" * 64},
                    "sources": [{"source_id": "example", "path": "/example.jsonl", "role": "transcript",
                                 "raw_model_version": None, "status": "recognized"}],
                    "turn": turn, "messages": [message], "events": [event]}

    @classmethod
    def _from_record(cls, loaded):
        result = super()._from_record(loaded)
        result.validate()
        return result

    def validate(self):
        data = self.records.to_record()
        events = [event_record(e).records.to_record() for e in data["events"]]
        turn, messages = data["turn"], data["messages"]
        if len({e["event_address"] for e in events}) != len(events):
            raise ValueError("Snapshot has duplicate Events")
        if len({m["message_address"] for m in messages}) != len(messages):
            raise ValueError("Snapshot has duplicate Messages")
        source_ids = {s["source_id"] for s in data["sources"]}
        for event in events:
            if compute_event_hash(event) != event["event_hash"]:
                raise ValueError("Snapshot Event hash disagrees with its content")
            if any(o["source_ref"]["source_id"] not in source_ids for o in event["observations"]):
                raise ValueError("Snapshot Event has an unknown raw source")
        for message in messages:
            targets = [resolve_event_ref(events, ref) for ref in message["event_refs"]]
            if any(t["standing"] != "MATCHED" for t in targets):
                raise ValueError("Snapshot Message Event is not exact")
            if compute_chat_message_hash(message) != message["message_hash"]:
                raise ValueError("Snapshot Message hash disagrees")
            if message["text"] != "\n".join(t["event"]["content"]["text"] for t in targets):
                raise ValueError("Snapshot Message text disagrees with Events")
            if message["side"] != turn["side"]:
                raise ValueError("Snapshot Message side disagrees with Turn")
        addressed = [resolve_event_ref(events, ref) for ref in turn["event_refs"]]
        if any(t["standing"] != "MATCHED" for t in addressed):
            raise ValueError("Snapshot Turn Event is not exact")
        if ({r["event_address"] for r in turn["event_refs"]}
                != {e["event_address"] for e in events}
                or len(events) != len(addressed)
                or any(e["origin"] != turn["side"] for e in events)):
            raise ValueError("Snapshot Event membership disagrees with Turn")
        if ({r["message_address"] for r in turn["message_refs"]}
                != {m["message_address"] for m in messages}
                or len(messages) != len(turn["message_refs"]) or any(
                resolve_chat_message_ref(messages, ref)["standing"] != "MATCHED"
                for ref in turn["message_refs"])):
            raise ValueError("Snapshot Turn Message is not exact")
        digest = compute_chat_turn_hash(turn, opaque_payload_hashes=[
            t["event"]["opaque_payload_hash"] for t in addressed])
        if digest != turn["turn_hash"]:
            raise ValueError("Snapshot Turn hash disagrees with its members")


class TurnSnapshotStore:
    """Insert-only cited evidence in the Chatlas Record Registry partition."""

    def __init__(self, *, chatlas_root: Path | None = None, registry=None):
        from .workflow import ChatlasWorkflow

        self.map = (registry or RecordRegistry(
            Path(chatlas_root) / "records" if chatlas_root else None)).for_workflow(ChatlasWorkflow)

    @staticmethod
    def key(locator):
        from .references import ChatlasTurnReference

        exact = ChatlasTurnReference.records.from_record({
            "type": "Tarav.Chatlas.Reference.Turn", "locator": locator}).address()
        encoded = json.dumps(exact, sort_keys=True, separators=(",", ":")).encode()
        return "turn-" + sha256(encoded).hexdigest()

    def find(self, locator):
        key = self.key(locator)
        if not self.map.path(key).is_file():
            return None
        snapshot = self.map.load(key)
        if not isinstance(snapshot, TurnSnapshot):
            raise ValueError("Expected retained TurnSnapshot")
        data = snapshot.records.to_record()
        if (data["session"]["identity_hash"] != locator["session_identity"]
                or data["turn"]["turn_address"] != locator["turn_address"]
                or data["turn"]["turn_hash"] != locator["turn_hash"]):
            raise ValueError("Snapshot does not match the requested coordinates")
        return snapshot

    def retain(self, model, turn):
        locator = {"session_identity": model["session"]["identity_hash"],
                   "turn_address": turn["turn_address"], "turn_hash": turn["turn_hash"]}
        event_addresses = {r["event_address"] for r in turn["event_refs"]}
        message_addresses = {r["message_address"] for r in turn["message_refs"]}
        snapshot = TurnSnapshot.records.from_record({
            "type": entity(TurnSnapshot).name, "session": model["session"],
            "sources": model["sources"], "producer": model["metadata"]["commit"],
            "turn": turn,
            "events": [e for e in model["events"] if e["event_address"] in event_addresses],
            "messages": [m for m in model["messages"] if m["message_address"] in message_addresses],
        })
        existing = self.find(locator)
        if existing is not None:
            return existing
        self.map.create()
        key = self.key(locator)
        try:
            self.map.insert(key, snapshot)
        except FileExistsError:
            return self.find(locator)
        self.map.commit((key,), "Retain exact cited Chatlas Turn")
        return snapshot


def retained_turn(locator, *, chatlas_root=None):
    snapshot = TurnSnapshotStore(chatlas_root=chatlas_root).find(locator)
    if snapshot is None:
        return None
    data = snapshot.records.to_record()
    return {"standing": "MATCHED", "representation": "retained-snapshot",
            "turn": data["turn"], "messages": data["messages"], "events": data["events"],
            "session": data["session"], "sources": data["sources"]}
