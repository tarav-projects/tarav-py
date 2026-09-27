"""Ownership of native surface models and parsing operations."""

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip

SURFACES_WORKFLOW_SHIP = WorkflowShip("6a85e98f-20ca-43b6-8bf4-38f5c07227a9")


class SurfacesWorkflow(TaravWorkflow):
    workflow_name = "surfaces"
    constitution = (
        "Represent native source structure and positions for consuming workflows."
    )

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("1d21b5a4-6d33-4238-ae25-c99d074f586d"),
            name="Tarav.Workflow.Surfaces",
            workflow=SURFACES_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return SURFACES_WORKFLOW_SHIP
