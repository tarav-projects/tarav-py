"""Notebook-owned schema/path note links, independent from registry mechanics."""
# tarav.breadcrumb 42fc73818c48

from tarav.l0.kernel import Ship, TaravClass, TypeShip
from tarav.l1.lines import Block, Line
from .workflow import NOTEBOOK_WORKFLOW_SHIP


class SchemaBlock(Block):
    """The general context for notes on one registered schema."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("2036baf4-3849-49a1-89a9-15ea63c6393c"),
                          name="Tarav.Notebook.Path.SchemaBlock", workflow=NOTEBOOK_WORKFLOW_SHIP)

    class RecordInterface(Block.RecordInterface):
        schema_ship: Ship

    def __init__(self, *, id, schema_ship, parent=None, contents=()):
        super().__init__(id=id, parent=parent, contents=contents)
        self.schema_ship = Ship(str(schema_ship))

    def _validated_contents(self, contents):
        values = super()._validated_contents(contents)
        if any(not isinstance(item, (Line, PathBlock)) for item in values):
            raise TypeError("Schema notes contain Lines and PathBlocks")
        return values

    def _to_record(self):
        return {**super()._to_record(), "schema_ship": str(self.schema_ship)}

    @classmethod
    def _from_record(cls, loaded):
        obj = super()._from_record(loaded)
        obj.schema_ship = loaded.data.schema_ship
        return obj

    def ships(self):
        return (*super().ships(), self.schema_ship)

    class Records(Block.Records):
        def record_example(self):
            return {**super().record_example(), "schema_ship": "8d674985-7c11-4559-853e-afb3328b8a7a"}


class PathBlock(Block):
    """Notes about a registered position; the path text remains in PathRegistry."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("90d3d4bc-851c-4dc5-bc82-f039ba5887eb"),
                          name="Tarav.Notebook.Path.PathBlock", workflow=NOTEBOOK_WORKFLOW_SHIP)

    class RecordInterface(Block.RecordInterface):
        path_ship: Ship

    def __init__(self, *, id, path_ship, parent=None, contents=()):
        super().__init__(id=id, parent=parent, contents=contents)
        self.path_ship = Ship(str(path_ship))

    def _validated_contents(self, contents):
        values = super()._validated_contents(contents)
        if any(not isinstance(item, (Line, PathBlock)) for item in values):
            raise TypeError("Path notes contain Lines and PathBlocks")
        return values

    def _to_record(self):
        return {**super()._to_record(), "path_ship": str(self.path_ship)}

    @classmethod
    def _from_record(cls, loaded):
        obj = super()._from_record(loaded)
        obj.path_ship = loaded.data.path_ship
        return obj

    def ships(self):
        return (*super().ships(), self.path_ship)

    class Records(Block.Records):
        def record_example(self):
            return {**super().record_example(), "path_ship": "3b7497b2-dad5-4d4b-9e52-c9c4c5053288"}
