"""Context workflow identity."""

from __future__ import annotations

from tarav.l1.context import CONTEXT_WORKFLOW_SHIP
from tarav.l0.kernel import TaravClass, TypeShip, TaravWorkflow


class ContextWorkflow(TaravWorkflow):
    """Own the Context graph: how objects contribute triples and how they are explored."""

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

    constitution = (
        "Collect the triples objects contribute about themselves into a graph "
        "that only grows, and explore it: list, open, follow, query."
    )
