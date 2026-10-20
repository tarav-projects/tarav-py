"""Select a Project's actual typed Notebook without provisioning on reads."""
from uuid import uuid5

from tarav.l0.kernel import Ship, entity
from tarav.l1.lines import Block, Line
from tarav.l1.notebook import Notebook as NotebookStorage
from tarav.l1.project.base import TaravProject
from tarav.l2.notebook import ArchiveBlock, DiscussionBlock, ModelBlock, ProjectBlock, TaravNotebook


def project_notebook_ship(project):
    return Ship(uuid5(project.id.uuid, "Tarav.Notebook.Project"))


# tarav.breadcrumb 0881a1b88687
# tarav.breadcrumb 8eafd1f9d9e2
# tarav.breadcrumb 1c14a8c1dfd5
def project_notebook(project, *, notebook=None, block_types=None):
    if not isinstance(project, TaravProject):
        raise TypeError("project must be a TaravProject")
    storage = notebook if notebook is not None else NotebookStorage()
    identity = project_notebook_ship(project)
    if storage.store.path(str(identity)).exists():
        root = storage.load(identity)
        if not isinstance(root, ProjectBlock) or root.project_ship != project.id:
            raise ValueError("Notebook root does not belong to this Project")
        return root
    layout = tuple(block_types) if block_types is not None else (
        DiscussionBlock, ModelBlock, ArchiveBlock,
    )
    if any(not isinstance(cls, type) or not issubclass(cls, Block) for cls in layout):
        raise TypeError("Notebook layout members must be Block Types")
    if len(set(layout)) != len(layout):
        raise ValueError("Notebook layout repeats a Block Type")
    root = ProjectBlock(id=identity, project_ship=project.id,
                        parent=TaravNotebook.open(storage), storage=storage)
    root.append(Line(id=Ship(uuid5(root.id.uuid, "context")), scope=root,
                     text=f"This notebook concerns Project {project.name} ({project.id})."))
    explanations = {
        DiscussionBlock: "Discussion: reasoning carries no implementation or alignment obligation.",
        ModelBlock: "Model: these Lines aim to express the current design of this Project.",
        ArchiveBlock: "Historical design material is retained here for reference; it does not claim current applicability.",
    }
    for cls in layout:
        block = cls(id=Ship(uuid5(root.id.uuid, str(entity(cls).id))), parent=root)
        if cls in explanations:
            block.append(Line(id=Ship(uuid5(block.id.uuid, "context")), scope=block,
                              text=explanations[cls]))
        root.append(block)
    return root
