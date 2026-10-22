"""Identified Workflow owning the dependency-free LabelFormats vocabulary."""
# tarav.breadcrumb e13b2e8325f3

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip

LABEL_FORMATS_WORKFLOW_SHIP = WorkflowShip("85d5ff70-5d3c-4ed4-b859-9d5868421c92")


class LabelFormatsWorkflow(TaravWorkflow):
    constitution = "Define explicit extensible label formats independently of their consumers."

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("aa137d6d-db68-4bdd-8897-4eb52438e761"),
                          name="Tarav.Workflow.LabelFormats", workflow=LABEL_FORMATS_WORKFLOW_SHIP)

    @classmethod
    def _workflow_id(cls):
        return LABEL_FORMATS_WORKFLOW_SHIP
