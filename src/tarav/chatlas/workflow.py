"""Chatlas Record registration for runtime composition."""

from tarav.kernel import TaravClass
from tarav.kernel import TypeShip
from tarav.kernel.workflows import TaravWorkflow
from tarav.chatlas.identity import CHATLAS_WORKFLOW_SHIP

from .normal_model import CHATLAS_SEMANTIC_RECORD_TYPES, ChatlasNormalModel
from .references import ChatlasTurnReference


CHATLAS_RECORD_TYPES = (
    ChatlasTurnReference,
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
    workflow_name = "chatlas"
    constitution = (
        "Retain provider-native chats and expose a provider-neutral Normal Model "
        "for conversation queries."
    )


__all__ = ["ChatlasWorkflow"]
