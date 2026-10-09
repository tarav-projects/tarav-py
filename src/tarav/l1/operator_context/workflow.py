"""Identity for the Operator Context workflow."""

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip

OPERATOR_CONTEXT_WORKFLOW_SHIP = WorkflowShip("302c88fa-1ba8-43e0-837c-9ca727dd17d8")


class OperatorContextWorkflow(TaravWorkflow):
    workflow_name = "operator-context"
    constitution = (
        "Give operators a standard place for the typed objects they hand to "
        "other workflows, and let those workflows take them under their own control."
    )

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("087cd3a4-05fd-47fd-9a08-2fd3920b116c"),
            name="Tarav.Workflow.OperatorContext",
            workflow=OPERATOR_CONTEXT_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return OPERATOR_CONTEXT_WORKFLOW_SHIP
