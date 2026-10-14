"""Identity for the Actions workflow."""

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip

ACTIONS_WORKFLOW_SHIP = WorkflowShip("8f3394a6-7670-4568-a71e-5120f687affd")


class ActionsWorkflow(TaravWorkflow):
    constitution = (
        "Provide typed Actions that harness a piece of an operator's work, "
        "and record each run of them."
    )

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("555d5edc-dd94-4766-8501-c6197a38a42e"),
            name="Tarav.Workflow.Actions",
            workflow=ACTIONS_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return ACTIONS_WORKFLOW_SHIP
