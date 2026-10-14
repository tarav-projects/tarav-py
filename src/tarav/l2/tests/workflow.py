"""Shallow parent of Tarav's explicit test workflows."""

from tarav.l0.kernel.identity import TypeShip, WorkflowShip
from tarav.l0.kernel.records import TaravClass
from tarav.l0.kernel.workflows import TaravWorkflow


TESTS_WORKFLOW_SHIP = WorkflowShip("84b6d49c-8bba-4af4-a880-c5fa453f80e5")


class TestsWorkflow(TaravWorkflow):
    """Group disposable test workflows without prescribing one test method."""

    __test__ = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("6a444dda-d175-4b9b-b9b3-0db0addc137a"),
            name="Tarav.Workflow.Tests",
            workflow=TESTS_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return TESTS_WORKFLOW_SHIP

    constitution = "Group disposable test workflows without prescribing one test method."
