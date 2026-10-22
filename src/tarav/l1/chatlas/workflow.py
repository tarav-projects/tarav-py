"""Chatlas Record registration for runtime composition."""

from tarav.l0.kernel import TaravClass
from tarav.l0.kernel import TypeShip
from tarav.l0.kernel.workflows import TaravWorkflow
from tarav.l1.chatlas.identity import CHATLAS_WORKFLOW_SHIP

from .normal_model import CHATLAS_SEMANTIC_RECORD_TYPES, ChatlasNormalModel
from .references import ChatlasTurnReference
from .sessions import ChatSession
from .turn_snapshots import TurnSnapshot


CHATLAS_RECORD_TYPES = (
    ChatSession,
    ChatlasTurnReference,
    TurnSnapshot,
    ChatlasNormalModel,
    *CHATLAS_SEMANTIC_RECORD_TYPES,
)


class ChatlasWorkflow(TaravWorkflow):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('13a826b1-713e-411c-9393-222ffc6a348b'),
            name='Tarav.Workflow.Chatlas',
            workflow=CHATLAS_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return CHATLAS_WORKFLOW_SHIP
    constitution = (
        "Retain provider-native chats and expose a provider-neutral Normal Model "
        "for conversation queries."
    )


__all__ = ["ChatlasWorkflow"]
