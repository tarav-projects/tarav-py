"""The persistent home for Lines and Blocks."""

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip

NOTEBOOK_WORKFLOW_SHIP = WorkflowShip("92338514-6f87-4dad-8a41-3148020f90d4")


# tarav.breadcrumb 801c640e30da
class NotebookWorkflow(TaravWorkflow):
    constitution = "Retain identified Blocks and Lines in a shared notebook."

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls, id=TypeShip("b25ff45a-a664-41b7-a6b8-98ad7db74a0f"),
            name="Tarav.Workflow.Notebook", workflow=NOTEBOOK_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return NOTEBOOK_WORKFLOW_SHIP
