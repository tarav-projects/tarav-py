"""Shared POI ownership; detection and response remain consumer-owned."""

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip

POI_WORKFLOW_SHIP = WorkflowShip("a24f9397-a95a-41a8-83e2-6007ac6e3e90")


class POIWorkflow(TaravWorkflow):
    constitution = "Expose typed points of interest without prescribing responses."

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip("fa8aa676-22bb-4a81-b79e-e73655fed748"),
                          name="Tarav.Workflow.POI", workflow=POI_WORKFLOW_SHIP)

    @classmethod
    def _workflow_id(cls):
        return POI_WORKFLOW_SHIP
