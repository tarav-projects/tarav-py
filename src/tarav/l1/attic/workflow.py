"""Cheap conservation, separate from Archive Artifact registration."""

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip
from tarav.l1.archive.workflow import ArchiveWorkflow

ATTIC_WORKFLOW_SHIP = WorkflowShip("8f4969ab-5f7b-45ac-9aeb-98a7e1b6541a")


# tarav.breadcrumb bc9a0ea60f9b
class AtticWorkflow(TaravWorkflow):
    constitution = (
        "Conserve displaced opaque material with self-declared deposit metadata; "
        "check metadata format without inspecting contents or certifying claims."
    )

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("192d1207-1394-4db9-bc66-9c2c45939a7c"),
                          name="Tarav.Workflow.Attic", workflow=ATTIC_WORKFLOW_SHIP)

    @classmethod
    def _workflow_id(cls):
        return ATTIC_WORKFLOW_SHIP

    @property
    def workflow(self):
        return ArchiveWorkflow()

    @staticmethod
    def open(root=None):
        from .model import Attic

        return Attic(root)

    @classmethod
    def help(cls):
        return {**super().help(), "skill": "tarav-pkg --attic",
                "instructions": "references/attic.md"}
