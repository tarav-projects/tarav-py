"""Workflow identity for recorded interventions."""

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip


DECISIONS_WORKFLOW_SHIP = WorkflowShip("fdb58ef7-ba97-485c-afb3-14cb3b214e4b")


# tarav.breadcrumb ae26ab84d51d
class DecisionsWorkflow(TaravWorkflow):
    constitution = "Retain attributed interventions without making their effects permanent."

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("bbb7494f-396b-4b59-893f-54f2238b7a58"),
            name="Tarav.Workflow.Decisions",
            workflow=DECISIONS_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return DECISIONS_WORKFLOW_SHIP
