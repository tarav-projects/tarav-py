"""Blessings workflow identity."""

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip

BLESSINGS_WORKFLOW_SHIP = WorkflowShip("36a15db8-2e54-485b-a255-fd0e4daf9c12")


class BlessingsWorkflow(TaravWorkflow):
    constitution = "Retain attributed acceptance and assessment of explicitly blessable POIs."

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("bc0a2cbe-63e1-4a3d-9d1a-745c8ed489ae"),
            name="Tarav.Workflow.Blessings",
            workflow=BLESSINGS_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return BLESSINGS_WORKFLOW_SHIP
