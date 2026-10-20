"""Project Notebook selection and identity integration for the Context workflow."""

from tarav.l0.kernel import TaravClass, TaravType, TypeShip
from tarav.l1.context import ContextHook
from tarav.l1.context.query import ContextCandidate, IdentityContextQuery
from tarav.l1.lines import Block, Line
from tarav.l1.lines.context import explore
from tarav.l1.notebook import Notebook
# tarav.breadcrumb 3fdbdc32d6fb
from tarav.l2.notebook import ArchiveBlock, DiscussionBlock, ModelBlock
from tarav.l1.notebook.workflow import NOTEBOOK_WORKFLOW_SHIP
from tarav.l1.project import TaravProject
from tarav.l1.search import SearchEngine, SearchHit
from tarav.l2.project.notebook import project_notebook, project_notebook_ship

NOTEBOOK = "urn:tarav:notebook:root"
BRANCHES = {"model": ModelBlock, "discussion": DiscussionBlock, "archive": ArchiveBlock}


# tarav.breadcrumb 77db4896a68d
class NotebookContext(TaravType):
    """One selected subtree collected into the existing Context Explorer."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("e168c31c-8d47-43cf-9cb2-cc7390c3a990"),
                          name="Tarav.Notebook.Context", workflow=NOTEBOOK_WORKFLOW_SHIP)

    def __init__(self, project: TaravProject, *, notebook=None, branch="model", block=None):
        self.project = project
        self.notebook = notebook if notebook is not None else Notebook()
        project_root = project_notebook(project, notebook=self.notebook)
        if not project_root.exists:
            raise FileNotFoundError(f"No Notebook for Project {project.id}")
        if block is not None:
            candidates = [obj for obj in project_root.walk() if isinstance(obj, Block)]
            self.root = _find(candidates, block)
        elif branch == "project":
            self.root = project_root
        else:
            if branch not in BRANCHES:
                raise ValueError(f"Unknown Notebook branch {branch!r}")
            candidates = [obj for obj in project_root.contents if isinstance(obj, BRANCHES[branch])]
            if len(candidates) != 1:
                raise LookupError(f"Expected one {branch} Block; found {len(candidates)}")
            self.root = candidates[0]
        self.explorer = explore(self.root)

    def get(self, identifier=None) -> Block | Line:
        if identifier is None:
            return self.root
        subjects = [context.subject for context in self.explorer.contexts.values()]
        return _find(subjects, identifier)


def _find(objects, identifier):
    wanted = str(identifier).removeprefix("urn:uuid:")
    if len(wanted) < 8:
        raise ValueError("Use a Ship or at least eight characters of its prefix")
    matches = [obj for obj in objects if str(obj.id).startswith(wanted)]
    if len(matches) != 1:
        raise LookupError(f"{len(matches)} Notebook items match {wanted!r} in the selected scope")
    return matches[0]


class NotebookProjectHook(ContextHook):
    """Expose existing Project notebook roots without provisioning them."""

    def __init__(self, notebook):
        self.notebook = notebook

    def run(self, cxt):
        if not isinstance(cxt.subject, TaravProject):
            return
        identity = project_notebook_ship(cxt.subject)
        if self.notebook.store.path(str(identity)).is_file():
            cxt.triplets.append((cxt.subject, NOTEBOOK, project_notebook(cxt.subject, notebook=self.notebook)))


# tarav.breadcrumb ebaa241f6bba
class NotebookResolver(SearchEngine):
    """Resolve stored Line/Block Ships; this supplies identity, not text search."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("dc929c86-d3f1-4db5-a2c1-9608334cb096"),
                          name="Tarav.Notebook.ContextResolver", workflow=NOTEBOOK_WORKFLOW_SHIP)

    def __init__(self, notebook=None):
        self.notebook = notebook if notebook is not None else Notebook()

    class Search(SearchEngine.Search):
        def accepts(self, query):
            return isinstance(query, IdentityContextQuery)

        def _iter_hits(self, query):
            wanted = query.identifier.removeprefix("urn:uuid:")
            if len(wanted) < 8 or set(wanted).difference("0123456789abcdef-"):
                return
            for ship in self.obj.notebook.ids():
                if str(ship).startswith(wanted):
                    obj = self.obj.notebook.load(ship)
                    yield SearchHit(ContextCandidate(obj, str(obj.id)))
