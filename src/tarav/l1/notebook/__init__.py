"""Python-first persistence for the Lines primitives."""

from pathlib import Path

from tarav.l0.kernel import LoadedRecord, Ship, TaravClass, TaravObject, TypeShip
from tarav.l1.lines import Block, Line
from tarav.l1.records.registry import RecordMap, RecordRegistry

from .workflow import NOTEBOOK_WORKFLOW_SHIP, NotebookWorkflow


# tarav.breadcrumb 3c097c77d655
class Notebook(TaravObject):
    """A Record Registry partition; choosing it never creates storage."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls, id=TypeShip("a572eb12-f132-474c-b6ea-26db972530fe"),
            name="Tarav.Notebook", workflow=NOTEBOOK_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        root: str

    class Records(TaravObject.Records):
        def record_example(self):
            return {**super().record_example(), "root": "/example/notebook"}

    def __init__(self, root: Path | str | None = None, *, records=None):
        super().__init__()
        self.store = (
            RecordMap(Path(root), NOTEBOOK_WORKFLOW_SHIP, records)
            if root is not None else
            RecordRegistry(records=records).for_workflow(NotebookWorkflow)
        )

    @property
    def root(self) -> Path:
        return self.store.root

    def create(self) -> "Notebook":
        self.store.create()
        return self

    def ids(self) -> tuple[Ship, ...]:
        if not self.store.marker.exists():
            return ()
        return tuple(Ship(name) for name in self.store.names())

    def save(self, obj: Line | Block) -> None:
        """Write one Record, retaining its identity and exact registered Type."""
        if not isinstance(obj, (Line, Block)):
            raise TypeError("Notebook stores Lines and Blocks")
        name = str(obj.id)
        if self.store.path(name).exists():
            previous = self.store.load(name)
            if previous.id != obj.id or type(previous) is not type(obj):
                raise ValueError("A stored Ship cannot be rebound to another Type")
            self.store.replace(name, obj)
        else:
            self.store.insert(name, obj)

    def save_tree(self, root: Block) -> None:
        """Save a Block and its contained objects; ancestors are not rewritten."""
        if not isinstance(root, Block):
            raise TypeError("save_tree requires a Block")
        objects = {}

        def visit(obj):
            if obj.id in objects:
                raise ValueError("Repeated Ship in a Block tree")
            objects[obj.id] = obj
            if isinstance(obj, Block):
                for member in obj.contents:
                    visit(member)

        visit(root)
        for obj in objects.values():
            self.save(obj)

    def load(self, identity: Ship | str) -> Line | Block:
        """Resolve the selected connected context, sharing objects by Ship."""
        cache = {}

        def resolve(value):
            ship = Ship(str(value))
            if ship in cache:
                return cache[ship]
            obj = self.store.load(str(ship))
            if not isinstance(obj, (Line, Block)) or obj.id != ship:
                raise ValueError("Notebook filename and Line/Block identity disagree")
            cache[ship] = obj
            if isinstance(obj, Line):
                obj.bind_scope(resolve(obj.scope_ship))
            else:
                if obj.parent_ship is not None:
                    obj.bind_parent(resolve(obj.parent_ship))
                obj.bind_contents(resolve(member) for member in obj.content_ships)
            return obj

        result = resolve(identity)
        for obj in cache.values():
            if isinstance(obj, Block):
                obj.ancestors()
        return result

    def commit(self, message: str) -> str:
        """Explicitly commit stored Records through the existing Git mechanics."""
        return self.store.commit(tuple(str(ship) for ship in self.ids()), message)

    def _to_record(self):
        return {**super()._to_record(), "root": str(self.root)}

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        return cls(loaded.data.root)


__all__ = ["Notebook", "NotebookWorkflow"]
