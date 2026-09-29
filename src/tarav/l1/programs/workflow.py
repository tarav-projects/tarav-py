"""Identity for the Programs workflow."""

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip

PROGRAMS_WORKFLOW_SHIP = WorkflowShip("d19da6bb-08cb-49ba-a61f-4655ff0c7c89")


class ProgramsWorkflow(TaravWorkflow):
    workflow_name = "programs"
    constitution = "Provide extensible typed Programs for organizing chosen work."

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("1d4201d2-28f7-42bb-8c7a-02181159ab33"),
            name="Tarav.Workflow.Programs",
            workflow=PROGRAMS_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return PROGRAMS_WORKFLOW_SHIP
