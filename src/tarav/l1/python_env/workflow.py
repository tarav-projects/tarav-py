"""Identity for the Python execution workflow."""

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip


PYTHON_WORKFLOW_SHIP = WorkflowShip("d0e3b953-4526-4ea4-b404-19a67ce5638c")


class PythonWorkflow(TaravWorkflow):
    constitution = "Configure and execute explicit Python operations."

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("32d91dd7-3410-4747-9596-3d19ebe6f075"),
            name="Tarav.Workflow.Python",
            workflow=PYTHON_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return PYTHON_WORKFLOW_SHIP


__all__ = ["PYTHON_WORKFLOW_SHIP", "PythonWorkflow"]
