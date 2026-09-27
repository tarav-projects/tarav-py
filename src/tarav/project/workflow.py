"""Project ownership, independently of attached consumer workflows."""

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip

PROJECT_WORKFLOW_SHIP = WorkflowShip("1ad784dd-17b4-48fc-a989-68b12c261326")


class ProjectWorkflow(TaravWorkflow):
    workflow_name = "project"
    constitution = "Represent projects through their portable .tarav/project.json identity."

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("80a660af-fb72-4eb2-8394-5433b978861e"),
            name="Tarav.Workflow.Project",
            workflow=PROJECT_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return PROJECT_WORKFLOW_SHIP
