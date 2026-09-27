"""tarav.unsorted.evidence: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

from tarav.unsorted.primitives import DiagramError
from tarav.unsorted.contracts import Finding
from tarav.l1.chatlas.normal_model import provide_normal_model
from tarav.l1.chatlas.normal_model import resolve_chat_message_ref
from tarav.l1.chatlas.normal_model import resolve_chat_turn_ref
from tarav.l1.chatlas.normal_model import resolve_event_ref
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from tarav.unsorted.contracts import ChatlasTurnReferenceInterface
    from tarav.unsorted.constants import JsonObject
    from tarav.lines.records import LineAnnotationRecord
    from pathlib import Path
    from tarav.unsorted.contracts import SupportMemberInterface
    from tarav.unsorted.records import UserTouchedAnnotation

class ChatlasEvidence:
    def __init__(
        self,
        *,
        model_loader: Callable[[str], JsonObject] | None = None,
        chatlas_root: Path | None = None,
    ) -> None:
        self.model_loader = model_loader or (
            lambda identity: provide_normal_model(
                identity_hash=identity, chatlas_root=chatlas_root
            )
        )
        self._models: dict[str, JsonObject] = {}

    def model(self, identity: str) -> JsonObject:
        if identity not in self._models:
            model = self.model_loader(identity)
            if not isinstance(model, dict):
                raise DiagramError("Chatlas Normal Model loader returned no object")
            self._models[identity] = model
        return self._models[identity]

    def resolve(self, ref: ChatlasTurnReferenceInterface) -> JsonObject:
        turns = self.model(ref.session_identity).get("turns")
        if not isinstance(turns, list):
            raise DiagramError("Chatlas Normal Model has no turns collection")
        return resolve_chat_turn_ref(
            turns, {"turn_address": ref.turn_address, "turn_hash": ref.turn_hash}
        )

    def check(
        self,
        annotation: UserTouchedAnnotation | LineAnnotationRecord,
        *,
        path: str,
    ) -> list[Finding]:
        findings: list[Finding] = []
        producer = self._matched(
            annotation.producer,
            f"{path}.producer",
            "producer-turn-unresolved",
            findings,
        )
        if producer is not None and producer.get("side") != "agent":
            findings.append(
                Finding(
                    "producer-turn-not-agent",
                    f"{path}.producer",
                    "Annotation producer is not an Agent turn.",
                )
            )
        for index, member in enumerate(annotation.support):
            member_path = f"{path}.support[{index}]"
            root_path = f"{member_path}.root"
            root = self._matched(
                member.root, root_path, "support-root-unresolved", findings
            )
            if root is not None and root.get("side") != "user":
                findings.append(
                    Finding(
                        "support-root-not-user",
                        root_path,
                        "Support.Member root is not a User turn.",
                    )
                )
            for neighbor_index, reference in enumerate(member.neighborhood):
                self._matched(
                    reference,
                    f"{member_path}.neighborhood[{neighbor_index}]",
                    "support-neighborhood-turn-unresolved",
                    findings,
                )
            for reference in (member.root, *member.neighborhood):
                if producer is None:
                    continue
                try:
                    available = self.was_available(annotation.producer, reference)
                except (DiagramError, ValueError) as exc:
                    findings.append(
                        Finding(
                            "support-context-unassessable",
                            member_path,
                            str(exc),
                        )
                    )
                    continue
                if not available:
                    findings.append(
                        Finding(
                            "support-not-in-producer-context",
                            member_path,
                            "Selected support content was not present before the Annotation producer turn.",
                        )
                    )
        return findings

    def was_available(
        self,
        producer: ChatlasTurnReferenceInterface,
        support: ChatlasTurnReferenceInterface,
    ) -> bool:
        producer_position = self._position(producer)
        if producer.session_identity == support.session_identity:
            return self._position(support) < producer_position
        support_text = self.turn_text(support)
        if not support_text:
            return False
        preceding_text = "\n".join(
            self._turn_text(producer.session_identity, turn)
            for turn in self._turns(producer.session_identity)[:producer_position]
        )
        return support_text in preceding_text

    def render_member(self, member: SupportMemberInterface) -> JsonObject:
        refs = list((member.root, *member.neighborhood))
        if all(ref.session_identity == member.root.session_identity for ref in refs):
            refs.sort(key=self._position)
        return {
            "root": member.root.model_dump(mode="json"),
            "turns": [
                {
                    "reference": ref.model_dump(mode="json"),
                    "side": self._turn(ref).get("side"),
                    "text": self.turn_text(ref),
                    "root": ref == member.root,
                }
                for ref in refs
            ],
        }

    def turn_text(self, ref: ChatlasTurnReferenceInterface) -> str:
        return self._turn_text(ref.session_identity, self._turn(ref))

    def turn(self, ref: ChatlasTurnReferenceInterface) -> JsonObject:
        return self._turn(ref)

    def position(self, ref: ChatlasTurnReferenceInterface) -> int:
        return self._position(ref)

    def _turn_text(self, identity: str, turn: JsonObject) -> str:
        model = self.model(identity)
        messages = model.get("messages")
        chunks: list[str] = []
        if isinstance(messages, list):
            for message_ref in turn.get("message_refs", []):
                if isinstance(message_ref, dict):
                    resolved = resolve_chat_message_ref(messages, message_ref)
                    message = resolved.get("message")
                    if (
                        resolved.get("standing") == "MATCHED"
                        and isinstance(message, dict)
                        and isinstance(message.get("text"), str)
                    ):
                        chunks.append(message["text"])
        events = model.get("events")
        if not chunks and isinstance(events, list):
            for event_ref in turn.get("event_refs", []):
                if not isinstance(event_ref, dict):
                    continue
                resolved = resolve_event_ref(events, event_ref)
                event = resolved.get("event")
                content = event.get("content") if isinstance(event, dict) else None
                text = content.get("text") if isinstance(content, dict) else None
                if resolved.get("standing") == "MATCHED" and isinstance(text, str):
                    chunks.append(text)
        return "\n".join(chunks)

    def _turns(self, identity: str) -> list[JsonObject]:
        turns = self.model(identity).get("turns")
        if not isinstance(turns, list) or not all(
            isinstance(turn, dict) for turn in turns
        ):
            raise DiagramError("Chatlas Normal Model has no valid turns collection")
        return turns

    def _position(self, ref: ChatlasTurnReferenceInterface) -> int:
        for index, turn in enumerate(self._turns(ref.session_identity)):
            if turn.get("turn_address") == ref.turn_address:
                if turn.get("turn_hash") != ref.turn_hash:
                    raise DiagramError(
                        "Chatlas Turn reference resolves to an amended turn"
                    )
                return index
        raise DiagramError("Chatlas Turn reference is missing")

    def _matched(
        self,
        ref: ChatlasTurnReferenceInterface,
        path: str,
        code: str,
        findings: list[Finding],
    ) -> JsonObject | None:
        try:
            resolved = self.resolve(ref)
        except Exception as exc:
            findings.append(Finding(code, path, str(exc)))
            return None
        turn = resolved.get("turn")
        if resolved.get("standing") != "MATCHED" or not isinstance(turn, dict):
            findings.append(
                Finding(
                    code,
                    path,
                    f"Chatlas Turn reference standing is {resolved.get('standing')}.",
                )
            )
            return None
        return turn

    def _turn(self, ref: ChatlasTurnReferenceInterface) -> JsonObject:
        findings: list[Finding] = []
        turn = self._matched(ref, "reference", "turn-unresolved", findings)
        if turn is None:
            raise DiagramError(findings[0].message)
        return turn
