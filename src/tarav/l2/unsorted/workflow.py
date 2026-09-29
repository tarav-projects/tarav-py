"""Explicit provisional ownership, without claiming final domain boundaries."""
from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip
from .identity import UNSORTED_WORKFLOW_SHIP


class UnsortedWorkflow(TaravWorkflow):
    workflow_name = "unsorted"
    constitution = "Keep unresolved legacy responsibilities operational while their ownership is clarified."

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("bcfa72a9-5750-4da0-8b04-2ce6c7ee73a5"),
                          name="Tarav.Workflow.Unsorted", workflow=UNSORTED_WORKFLOW_SHIP)

    @classmethod
    def _workflow_id(cls):
        return UNSORTED_WORKFLOW_SHIP
