"""Shallow typed notebook contexts; their Lines express instance meaning."""

from tarav.l0.kernel import LoadedRecord, Ship, TaravClass, TypeShip
from tarav.l1.lines import Block

from .workflow import NOTEBOOK_WORKFLOW_SHIP


# tarav.context 0f5bad01:62c5e3e4c77f1cf3
class ProjectBlock(Block):
    """The notebook entry point associated with one Project Ship."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls, id=TypeShip("e906fa91-9f5b-4665-bd52-375258428ae4"),
            name="Tarav.Notebook.ProjectBlock", workflow=NOTEBOOK_WORKFLOW_SHIP,
        )

    class RecordInterface(Block.RecordInterface):
        project_ship: Ship

    class Records(Block.Records):
        def record_example(self):
            return {**super().record_example(),
                    "project_ship": "85c304e9-a3f9-4093-abc3-ee10a32743bf"}

    def __init__(self, *, id: Ship, project_ship: Ship, parent=None, contents=()):
        super().__init__(id=id, parent=parent, contents=contents)
        self.project_ship = Ship(str(project_ship))

    def _to_record(self):
        return {**super()._to_record(), "project_ship": str(self.project_ship)}

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        obj = super()._from_record(loaded)
        obj.project_ship = loaded.data.project_ship
        return obj

    def ships(self):
        return (*super().ships(), self.project_ship)


class DiscussionBlock(Block):
    """Reasoning without an obligation to implement its content."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls, id=TypeShip("55f01920-344d-4d90-b2f0-75ff3addfdc8"),
            name="Tarav.Notebook.DiscussionBlock", workflow=NOTEBOOK_WORKFLOW_SHIP,
        )


class ModelBlock(Block):
    """A context intended to express current design."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls, id=TypeShip("5f93c667-c08e-408f-8962-c4af74a9a565"),
            name="Tarav.Notebook.ModelBlock", workflow=NOTEBOOK_WORKFLOW_SHIP,
        )


class ArchiveBlock(Block):
    """Historical material retained for reference."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls, id=TypeShip("995b7644-eea9-4f35-a189-c195ff8ccb43"),
            name="Tarav.Notebook.ArchiveBlock", workflow=NOTEBOOK_WORKFLOW_SHIP,
        )


NOTEBOOK_BLOCK_TYPES = (ProjectBlock, DiscussionBlock, ModelBlock, ArchiveBlock)
