"""Context workflow identity."""

from __future__ import annotations

from tarav.l1.context import ContextType, CONTEXT_WORKFLOW_SHIP
from tarav.l0.kernel import TaravClass, TypeShip, TaravWorkflow


class ContextWorkflow(TaravWorkflow, ContextType):
    """Compose runtime Context with Archive-backed subject directories."""

    @classmethod
    def _workflow_id(cls):
        return CONTEXT_WORKFLOW_SHIP

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("31e50d71-3ffd-44b0-8d91-aee36f82968a"),
            name="Tarav.Workflow.Context",
            workflow=CONTEXT_WORKFLOW_SHIP,
        )

    workflow_name = "context"
    constitution = (
        "Provide read-only progressive Context navigation and retain identified "
        "subjects' Context entries through Record Archive."
    )
