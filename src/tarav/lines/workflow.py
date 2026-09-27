"""Ownership of Lines, Blocks, Collections, and their editions."""
from tarav.kernel import TaravClass, TaravWorkflow, TypeShip
from .identity import LINES_WORKFLOW_SHIP


class LinesWorkflow(TaravWorkflow):
    workflow_name = "lines"
    constitution = "Organize evidence-linked Lines, Blocks, Collections, and their editions."

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("25a55b5b-6aa3-485e-a4cd-3c309a2a67fa"),
                          name="Tarav.Workflow.Lines", workflow=LINES_WORKFLOW_SHIP)

    @classmethod
    def _workflow_id(cls):
        return LINES_WORKFLOW_SHIP
