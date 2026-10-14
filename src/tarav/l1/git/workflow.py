"""Identity for Tarav's general Git workflow."""

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip


GIT_WORKFLOW_SHIP = WorkflowShip("b84036a3-830b-44bb-939b-c1f18f163ad1")


class GitWorkflow(TaravWorkflow):
    constitution = "Inspect and mutate explicitly selected Git repositories."

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("c54bcd7d-25f0-4619-9000-ee611d3d8f6b"),
            name="Tarav.Workflow.Git",
            workflow=GIT_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return GIT_WORKFLOW_SHIP


__all__ = ["GIT_WORKFLOW_SHIP", "GitWorkflow"]
