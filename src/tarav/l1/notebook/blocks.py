"""Storage binding for Notebook Blocks, without integration dependencies."""
from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.lines import Block
from .workflow import NOTEBOOK_WORKFLOW_SHIP


# tarav.breadcrumb c685e614b37b
class NotebookBlock(Block):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("27f990bc-8f4e-416d-be3e-2cc99286c089"),
                          name="Tarav.Notebook.BlockBase", workflow=NOTEBOOK_WORKFLOW_SHIP)

    def bind_storage(self, storage):
        self._storage = storage
        return self

    @property
    def storage(self):
        if getattr(self, "_storage", None) is None:
            raise LookupError("Notebook has not been bound to storage")
        return self._storage
