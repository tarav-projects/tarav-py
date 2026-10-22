"""Typed Notebook Blocks integrate capture, evidence, and recursive checks."""
from uuid import uuid5

from tarav.l0.kernel import LoadedRecord, Ship, TaravClass, TypeShip
from tarav.l1.checks import CheckProvider, CheckSuite
from tarav.l1.grounding import SupportMember
from tarav.l1.lines import Block, Line
from tarav.l1.notebook import Notebook as NotebookStorage
from tarav.l1.notebook.blocks import NotebookBlock
from tarav.l1.notebook.paths import SchemaBlock, PathBlock
from tarav.l0.label_formats import Label
from tarav.l1.notebook.workflow import NOTEBOOK_WORKFLOW_SHIP
from tarav.l2.notebook_capture import NotebookCapture
from tarav.l2.notebook_checks import NotebookEvidenceSuite


# tarav.breadcrumb d09ba7b1f95d
# tarav.breadcrumb 966b135bf7ba
class Notebook(NotebookBlock, CheckProvider):
    """A semantic context and the bounded interface for operating on its contents."""
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("633e33c5-dac7-4cc4-9156-2aa91c8f67a8"),
                          name="Tarav.Notebook.Block", workflow=NOTEBOOK_WORKFLOW_SHIP)

    def __init__(self, *, id, parent=None, contents=(), storage=None):
        super().__init__(id=id, parent=parent, contents=contents)
        if storage is None:
            owner = next((p for p in self.ancestors() if isinstance(p, NotebookBlock)), None)
            storage = owner.storage if owner is not None else NotebookStorage()
        self.bind_storage(storage)

    @property
    def exists(self):
        return self.storage.store.path(str(self.id)).is_file()

    def create(self):
        """Persist a new context; preserve an existing context and its ancestry."""
        if self.exists:
            loaded = self.storage.load(self.id)
            if not isinstance(loaded, type(self)):
                raise ValueError("Stored Ship identifies a different Notebook Type")
            return loaded
        self.storage.create()
        if self.parent is not None and self.id not in self.parent.content_ships:
            self.parent.append(self)
        self.storage.save_tree(self)
        for ancestor in self.ancestors():
            self.storage.save(ancestor)
        return self.storage.load(self.id)

    def save(self):
        self.storage.save_tree(self)

    # tarav.breadcrumb 1e3843684f31
    def draft(self, *, block=None):
        """Stage reviewed capture without writing candidate content."""
        from tarav.l2.notebook_draft import NotebookDraft

        target = self if block is None else self._owned(block)
        if not isinstance(target, Block):
            raise TypeError("Draft destination must be a Block")
        return NotebookDraft(self, target)

    def notebooks(self):
        """Nearest nested notebooks; each owns the recursion below it."""
        def visit(block):
            for item in block.contents:
                if isinstance(item, Notebook):
                    yield item
                elif isinstance(item, Block):
                    yield from visit(item)
        yield from visit(self)

    def local_lines(self):
        def visit(block):
            for item in block.contents:
                if isinstance(item, Line):
                    yield item
                elif not isinstance(item, Notebook):
                    yield from visit(item)
        yield from visit(self)

    class Checks(CheckProvider.Checks):
        def suite(self):
            return CheckSuite([NotebookEvidenceSuite(self.obj),
                               *(child.checks.suite() for child in self.obj.notebooks())],
                              name="Notebook", key=str(self.obj.id))

    @property
    def evidence(self):
        """Subtypes may specialize evidence policy without changing storage."""
        return NotebookCapture(self.storage)

    def _owned(self, obj):
        if not any(item.id == obj.id for item in self.walk()):
            raise ValueError("Operation target is outside this Notebook's loaded subtree")
        return obj

    def _owner(self, obj):
        self._owned(obj)
        block = obj.scope if isinstance(obj, Line) else obj
        return next(p for p in (block, *block.ancestors()) if isinstance(p, Notebook))

    def capture(self, text, *, block=None, root=None, neighborhood=(), producer=None,
                reviewed=False, id=None):
        target = self if block is None else self._owned(block)
        if not isinstance(target, Block):
            raise TypeError("Capture target must be a Block")
        service = self._owner(target).evidence
        members = () if root is None else (SupportMember(root, neighborhood=neighborhood),)
        if members or producer is not None:
            service.create()
        return service.capture(target, text, members=members, producer=producer,
                               reviewed=reviewed, id=id)

    def support(self, line, *, root, neighborhood=(), producer=None):
        service = self._owner(line).evidence.create()
        return service.attach_support(line, (SupportMember(root, neighborhood=neighborhood),),
                                      producer=producer)

    def inspect(self, line):
        return self._owner(line).evidence.inspect(line)

    def _review_target(self, destination):
        target = self if destination is None else self._owned(destination)
        if not isinstance(target, Block):
            raise TypeError("Review destination must be a Block")
        return target

    def propose_review(self, lines, *, destination=None, **proposal):
        lines = tuple(lines)
        for line in lines:
            self._owned(line)
        target = self._review_target(destination)
        return self._owner(target).evidence.propose_review(lines, destination=target, **proposal)

    def record_review(self, lines, *, destination=None, **review):
        lines = tuple(lines)
        for line in lines:
            self._owned(line)
        target = self._review_target(destination)
        return self._owner(target).evidence.create().record_review(lines, destination=target, **review)

    def complete_review(self, review):
        target = next((item for item in self.walk()
                       if isinstance(item, Block) and item.id == review.typed.destination), None)
        if target is None:
            raise ValueError("Review destination is outside this Notebook")
        return self._owner(target).evidence.complete_review(review)


class TaravNotebook(Notebook):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("33f03d4d-d8fc-49c3-8421-649349a90a5e"),
                          name="Tarav.Notebook.Tarav", workflow=NOTEBOOK_WORKFLOW_SHIP)

    @classmethod
    def open(cls, storage=None):
        storage = storage if storage is not None else NotebookStorage()
        identity = Ship(uuid5(NOTEBOOK_WORKFLOW_SHIP.uuid, "Tarav.Notebook.Root"))
        if storage.store.path(str(identity)).exists():
            result = storage.load(identity)
            if not isinstance(result, cls):
                raise ValueError("Tarav Notebook Ship identifies a different Type")
            return result
        return cls(id=identity, storage=storage)


# tarav.breadcrumb d3b81e3ccf45
class ProjectBlock(Notebook):
    """The Notebook associated with one Project Ship."""
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("e906fa91-9f5b-4665-bd52-375258428ae4"),
                          name="Tarav.Notebook.ProjectBlock", workflow=NOTEBOOK_WORKFLOW_SHIP)

    class RecordInterface(Notebook.RecordInterface):
        project_ship: Ship

    class Records(Notebook.Records):
        def record_example(self):
            return {**super().record_example(),
                    "project_ship": "85c304e9-a3f9-4093-abc3-ee10a32743bf"}

    def __init__(self, *, id, project_ship, parent=None, contents=(), storage=None):
        super().__init__(id=id, parent=parent, contents=contents, storage=storage)
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

    def _branch(self, cls):
        matches = [item for item in self.contents if isinstance(item, cls)]
        if len(matches) != 1:
            raise LookupError(f"Expected one direct {cls.__name__}")
        return matches[0]

    @property
    def discussion(self):
        return self._branch(DiscussionBlock)

    @property
    def model(self):
        return self._branch(ModelBlock)

    @property
    def archive(self):
        return self._branch(ArchiveBlock)

    @property
    def paths(self):
        """The nested notes on this Project's registered Type schemas."""
        # tarav.breadcrumb ecfedb264030
        from tarav.l1.path_registry import PathRegistry

        return PathNotebook.open(PathRegistry(self.project_ship), parent=self, storage=self.storage)

    def create(self):
        root = super().create()
        if not root.paths.exists:
            root.paths.create()
        return self.storage.load(root.id)


class DiscussionBlock(Notebook):
    """Reasoning without an obligation to implement its content."""
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("55f01920-344d-4d90-b2f0-75ff3addfdc8"),
                          name="Tarav.Notebook.DiscussionBlock", workflow=NOTEBOOK_WORKFLOW_SHIP)


class ModelBlock(Notebook):
    """A Notebook intended to express current design."""
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("5f93c667-c08e-408f-8962-c4af74a9a565"),
                          name="Tarav.Notebook.ModelBlock", workflow=NOTEBOOK_WORKFLOW_SHIP)


class ArchiveBlock(Notebook):
    """Historical material retained for reference."""
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("995b7644-eea9-4f35-a189-c195ff8ccb43"),
                          name="Tarav.Notebook.ArchiveBlock", workflow=NOTEBOOK_WORKFLOW_SHIP)


class PathNotebook(Notebook):
    """A nested Notebook whose schema/path Blocks own notes, never registry data."""
    # tarav.breadcrumb 56b7937ac17a

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("c3f7c2b7-3929-45be-8936-a499e499d9df"),
                          name="Tarav.Notebook.Path", workflow=NOTEBOOK_WORKFLOW_SHIP)

    class RecordInterface(Notebook.RecordInterface):
        registry_ship: Ship

    def __init__(self, *, id, registry_ship, parent=None, contents=(), storage=None):
        super().__init__(id=id, parent=parent, contents=contents, storage=storage)
        self.registry_ship = Ship(str(registry_ship))

    def _validated_contents(self, contents):
        values = super()._validated_contents(contents)
        if any(not isinstance(item, (Line, SchemaBlock)) for item in values):
            raise TypeError("PathNotebook contains Lines and SchemaBlocks")
        return values

    def _to_record(self):
        return {**super()._to_record(), "registry_ship": str(self.registry_ship)}

    @classmethod
    def _from_record(cls, loaded):
        obj = super()._from_record(loaded)
        obj.registry_ship = loaded.data.registry_ship
        return obj

    def ships(self):
        return (*super().ships(), self.registry_ship)

    class Records(Notebook.Records):
        def record_example(self):
            return {**super().record_example(), "registry_ship": "7daab078-c8e5-41c4-a644-9653fd53c9e2"}

    @classmethod
    def open(cls, registry, *, parent, storage=None):
        storage = storage if storage is not None else parent.storage
        identity = Ship(uuid5(registry.id.uuid, "PathNotebook"))
        if storage.store.path(str(identity)).exists():
            obj = storage.load(identity)
            if (not isinstance(obj, cls) or obj.registry_ship != registry.id
                    or obj.parent_ship != parent.id):
                raise ValueError("Path Notebook identity, registry or parent mismatch")
            return obj
        return cls(id=identity, registry_ship=registry.id, parent=parent, storage=storage)

    def create(self):
        if isinstance(self.parent, Notebook) and not self.parent.exists:
            if self.id not in self.parent.content_ships:
                self.parent.append(self)
            self._parent = self.parent.create()
        return super().create()

    def _view(self, registry, ship):
        if registry.id != self.registry_ship:
            raise ValueError("PathNotebook belongs to a different registry")
        matches = [view for view in registry.views if view.id == Ship(str(ship))]
        if len(matches) != 1:
            raise LookupError("Schema must identify one registered View")
        return matches[0]

    def schema(self, registry, ship):
        view = self._view(registry, ship)
        matches = [b for b in self.contents if isinstance(b, SchemaBlock) and b.schema_ship == view.id]
        if len(matches) != 1:
            raise LookupError("Schema must identify one direct SchemaBlock")
        return matches[0]

    def add_schema(self, registry, ship):
        view = self._view(registry, ship)
        matches = [b for b in self.contents if isinstance(b, SchemaBlock) and b.schema_ship == view.id]
        if matches:
            return self.schema(registry, ship)
        block = SchemaBlock(id=Ship(uuid5(self.id.uuid, "schema:" + str(view.id))),
                            schema_ship=view.id, parent=self)
        self.append(block)
        return block

    def _chain(self, registry, ship):
        entry = registry.entry(ship)
        view = self._view(registry, entry.typed.view)
        if not entry.typed.active or entry.typed.path is None:
            raise ValueError("Path identity is retired or has no current declaration")
        paths = [""]
        pointer = ""
        if entry.typed.path:
            for token in entry.typed.path.split("/")[1:]:
                pointer += "/" + token
                paths.append(pointer)
        chain = []
        for pointer in paths:
            matches = registry.at(view.id, pointer)
            if len(matches) != 1:
                raise LookupError(f"Path ancestry requires one registered identity at {pointer!r}")
            chain.append(matches[0])
        return view, chain

    def _path_block(self, ship):
        matches = [b for b in self.walk() if isinstance(b, PathBlock) and b.path_ship == ship]
        if len(matches) > 1:
            raise ValueError("Several note Blocks reference the same Path Ship")
        return matches[0] if matches else None

    def path(self, registry, ship):
        view, chain = self._chain(registry, ship)
        if self._path_block(Ship(str(ship))) is None:
            raise LookupError("Path has no note Block")
        parent = self.schema(registry, view.id)
        for entry in chain:
            block = self._path_block(entry.id)
            if block is None or block.parent_ship != parent.id:
                raise ValueError("Path note ancestry changed; maintain the Notebook explicitly")
            parent = block
        return parent

    def add_path(self, registry, ship):
        """Explicit in-memory construction; materialize registered parents only."""
        view, chain = self._chain(registry, ship)
        existing = [self._path_block(entry.id) for entry in chain]
        schemas = [b for b in self.contents if isinstance(b, SchemaBlock) and b.schema_ship == view.id]
        if len(schemas) > 1:
            raise ValueError("Several note Blocks reference the same schema")
        parent = schemas[0] if schemas else None
        for block in existing:
            if block is not None and (parent is None or block.parent_ship != parent.id):
                raise ValueError("Path note ancestry changed; maintain the Notebook explicitly")
            parent = block
        parent = self.add_schema(registry, view.id)
        for entry, block in zip(chain, existing):
            if block is None:
                block = PathBlock(id=Ship(uuid5(self.id.uuid, "path:" + str(entry.id))),
                                  path_ship=entry.id, parent=parent)
                parent.append(block)
            parent = block
        return parent

    def label(self, registry, ship):
        self.path(registry, ship)
        return Label(registry.entry(ship).typed.path)


NOTEBOOK_BLOCK_TYPES = (NotebookBlock, Notebook, TaravNotebook, ProjectBlock,
                        DiscussionBlock, ModelBlock, ArchiveBlock, PathNotebook,
                        SchemaBlock, PathBlock)
