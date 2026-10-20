"""Project access checks compose the Notebook's own recursive suites."""
from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import CheckSuite
from tarav.l1.notebook import Notebook
from tarav.l1.notebook.workflow import NOTEBOOK_WORKFLOW_SHIP
from tarav.l2.notebook_checks import NotebookAccessChain
from .notebook import project_notebook, project_notebook_ship


# tarav.breadcrumb a31033601bd1
class ProjectNotebookSuite(CheckSuite):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("608c7d9a-e1cf-4f8e-b681-ec5b32873033"),
                          name="Tarav.Project.Notebook.Suite", workflow=NOTEBOOK_WORKFLOW_SHIP)

    def __init__(self, project, *, notebook=None):
        self.project = project
        self.notebook = notebook if notebook is not None else Notebook()
        super().__init__(name="Project Notebook", key=str(project.id))

    def produce(self):
        identity = project_notebook_ship(self.project)

        def load():
            if not self.notebook.store.path(str(identity)).exists():
                return None
            return project_notebook(self.project, notebook=self.notebook)

        access = NotebookAccessChain({"project": str(self.project.id), "root": str(identity)}).check(load=load)
        yield access
        if access.error is not None:
            self._refused += 1
        elif access.root is not None:
            yield access.root.checks.suite()
