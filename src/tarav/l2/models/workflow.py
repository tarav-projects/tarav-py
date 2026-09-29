"""Ownership of Models, independently of project associations."""
from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip

MODELS_WORKFLOW_SHIP = WorkflowShip('97d49ed8-9a40-49d6-8857-c43d78954384')


class ModelsWorkflow(TaravWorkflow):
    workflow_name = 'models'
    constitution = 'Organize Models and their editions independently of their consumers.'

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('0a5c6053-8124-4d7f-8d70-4f4cc2fb1604'),
                          name='Tarav.Workflow.Models', workflow=MODELS_WORKFLOW_SHIP)

    @classmethod
    def _workflow_id(cls):
        return MODELS_WORKFLOW_SHIP
