"""Assertions Workflow identity."""

from tarav.l0.kernel import TaravClass, TypeShip, WorkflowShip
from tarav.l0.kernel.workflows import TaravWorkflow


ASSERTIONS_WORKFLOW_SHIP = WorkflowShip('129a985a-3215-46d9-9e04-4c1525566a96')


class AssertionsWorkflow(TaravWorkflow):
    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip('9c4cfa97-72f7-4e80-84dd-3ab30945e6cf'),
            name='Tarav.Workflow.Assertions',
            workflow=ASSERTIONS_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return ASSERTIONS_WORKFLOW_SHIP

    constitution = 'Represent typed assertions without requiring a scoring method.'
