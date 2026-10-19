"""A Project's rooted partition of the shared Line Notebook."""

from uuid import uuid5

from tarav.l0.kernel import Ship, TaravClass, TaravType, TypeShip, entity
from tarav.l1.lines import Block, Line
from tarav.l1.notebook import Notebook
from tarav.l1.notebook.blocks import ArchiveBlock, DiscussionBlock, ModelBlock, ProjectBlock
from tarav.l1.notebook.workflow import NOTEBOOK_WORKFLOW_SHIP
from tarav.l1.project.base import TaravProject


# tarav.context 0f5bad01:62c5e3e4c77f1cf3
# tarav.context 0f5bad01:89b3bb12c584cdae
class ProjectNotebook(TaravType):
    """Association and initial layout; opening never rewrites saved meaning."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls, id=TypeShip("a33b16b3-2e92-4b47-8b65-89dbf3e1edb8"),
            name="Tarav.Project.Notebook", workflow=NOTEBOOK_WORKFLOW_SHIP,
        )

    def __init__(self, project: TaravProject, *, notebook=None, block_types=None):
        if not isinstance(project, TaravProject):
            raise TypeError("project must be a TaravProject")
        self.project = project
        self.notebook = notebook if notebook is not None else Notebook()
        self.block_types = tuple(block_types) if block_types is not None else (
            DiscussionBlock, ModelBlock, ArchiveBlock,
        )
        if any(not isinstance(cls, type) or not issubclass(cls, Block)
               for cls in self.block_types):
            raise TypeError("Notebook layout members must be Block Types")
        if len(set(self.block_types)) != len(self.block_types):
            raise ValueError("Notebook layout repeats a Block Type")

    @property
    def root_ship(self) -> Ship:
        return Ship(uuid5(self.project.id.uuid, "Tarav.Notebook.Project"))

    @property
    def root(self) -> ProjectBlock:
        root = self.notebook.load(self.root_ship)
        if not isinstance(root, ProjectBlock) or root.project_ship != self.project.id:
            raise ValueError("Notebook root does not belong to this Project")
        return root

    def create(self) -> ProjectBlock:
        """Create the default layout once; preserve every later edit."""
        self.notebook.create()
        if self.notebook.store.path(str(self.root_ship)).exists():
            return self.root
        root = ProjectBlock(id=self.root_ship, project_ship=self.project.id)
        root.append(Line(
            id=Ship(uuid5(root.id.uuid, "context")),
            text=f"This notebook concerns Project {self.project.name} ({self.project.id}).",
            scope=root,
        ))
        explanations = {
            DiscussionBlock: "Discussion: reasoning carries no implementation or alignment obligation.",
            ModelBlock: "Model: these Lines aim to express the current design of this Project.",
            ArchiveBlock: "Historical design material is retained here for reference; it does not claim current applicability.",
        }
        for cls in self.block_types:
            block = cls(id=Ship(uuid5(root.id.uuid, str(entity(cls).id))), parent=root)
            if cls in explanations:
                block.append(Line(
                    id=Ship(uuid5(block.id.uuid, "context")),
                    text=explanations[cls], scope=block,
                ))
            root.append(block)
        self.notebook.save_tree(root)
        return root

    def _branch(self, cls):
        matches = [item for item in self.root.contents if isinstance(item, cls)]
        if len(matches) != 1:
            raise LookupError(f"Expected one direct {cls.__name__}")
        return matches[0]

    @property
    def discussion(self) -> DiscussionBlock:
        return self._branch(DiscussionBlock)

    @property
    def model(self) -> ModelBlock:
        return self._branch(ModelBlock)

    @property
    def archive(self) -> ArchiveBlock:
        return self._branch(ArchiveBlock)
