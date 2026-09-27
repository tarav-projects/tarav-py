"""Exact Chatlas Turn references; no Diagram or Skillware semantics."""
import re

from pydantic import ConfigDict, Field

from tarav.l0.kernel import TaravClass, entity
from tarav.l0.kernel import TaravObject, TypeShip
from tarav.l1.references import Reference
from tarav.l1.chatlas.identity import CHATLAS_WORKFLOW_SHIP
from tarav.l1.chatlas.normal_model import (
    provide_normal_model, resolve_chat_turn_ref, resolve_chat_message_ref,
)


class ChatlasTurnLocator(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid")

    session_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    turn_address: str = Field(pattern=r"^[0-9a-f]{64}$")
    turn_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class EmptyReferenceCheck(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid")


class ChatlasTurnReference(Reference):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('aa3a6dc3-3c17-409f-a151-041ff0a05a74'),
            name='Tarav.Chatlas.Reference.Turn',
            workflow=CHATLAS_WORKFLOW_SHIP,
        )

    class RecordInterface(Reference.RecordInterface):
        locator: ChatlasTurnLocator
        check: EmptyReferenceCheck | None = None

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {
            "type": entity(cls).name,
            "locator": {
                "session_identity": "0" * 64,
                "turn_address": "0" * 64,
                "turn_hash": "0" * 64,
            },
        }

    def address(self):
        locator = self.locator
        if not isinstance(locator, dict) or set(locator) != {"session_identity", "turn_address", "turn_hash"}:
            raise ValueError("Turn locator requires session_identity, turn_address, turn_hash")
        if any(not isinstance(v, str) or re.fullmatch('[0-9a-f]{64}', v) is None
               for v in locator.values()):
            raise ValueError("Turn coordinates must be full lowercase SHA-256 digests")
        return dict(locator)

    def locate(self, locator):
        coordinates = self.address()
        model = provide_normal_model(identity_hash=coordinates['session_identity'])
        result = resolve_chat_turn_ref(model['turns'], coordinates)
        if result['standing'] != 'MATCHED':
            raise ValueError(f"Chatlas Turn is {result['standing']}")
        turn = result['turn']
        messages = []
        for ref in turn['message_refs']:
            message = resolve_chat_message_ref(model['messages'], ref)
            if message['standing'] != 'MATCHED':
                raise ValueError(f"Chatlas Message is {message['standing']}")
            messages.append(message['message'])
        return {
            "type": entity(type(self)).name,
            "locator": coordinates,
            "turn": turn,
            "messages": messages,
        }

    def check_target(self, target, check):
        if check not in (None, {}):
            raise ValueError("Turn identity is pinned by locator; extra checks are unsupported")
        return True
