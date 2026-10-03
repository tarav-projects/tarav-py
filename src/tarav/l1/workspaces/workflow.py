"""Workspace workflow identity."""

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip


WORKSPACES_WORKFLOW_SHIP = WorkflowShip("76a50a33-030e-4808-b27a-a723e306888e")


# tarav.breadcrumb 258422634094ec693997084e1065f514c092bd4d8da15e25b583e8949c54de8f
class WorkspacesWorkflow(TaravWorkflow):
    workflow_name = "workspaces"
    constitution = "Create and inspect isolated, identified working folders."

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("43784ddb-e37d-4df8-a82b-cbd69c7786a9"),
                          name="Tarav.Workflow.Workspaces",
                          workflow=WORKSPACES_WORKFLOW_SHIP)

    @classmethod
    def _workflow_id(cls):
        return WORKSPACES_WORKFLOW_SHIP


__all__ = ["WORKSPACES_WORKFLOW_SHIP", "WorkspacesWorkflow"]
