"""Workflow identity for configurable Record entry discovery."""

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip

LOADING_WORKFLOW_SHIP = WorkflowShip("c075d42a-1a8f-4f7d-ad40-7ec3a7e03648")


class LoadingWorkflow(TaravWorkflow):
    workflow_name = "loading"
    constitution = "Select Record entry files before trusted Type dispatch."

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("85893b81-f4b4-45f9-9d7b-ccbc455bfab4"),
            name="Tarav.Workflow.Loading",
            workflow=LOADING_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return LOADING_WORKFLOW_SHIP
