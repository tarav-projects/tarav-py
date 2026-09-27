"""The conventional Project Wiki attachment."""

from tarav.l0.kernel import TaravClass, TaravType, TaravWorkflow, TypeShip, WorkflowShip
from tarav.project.base import TaravProject
from tarav.project.workflow import ProjectWorkflow
from tarav.wiki import Wiki

PROJECT_WIKI_WORKFLOW_SHIP = WorkflowShip("27922f68-ecea-43ae-9316-2c81ed387e95")


class ProjectWikiWorkflow(TaravWorkflow):
    workflow_name = "project.wiki"
    constitution = "Expose the conventional Wiki folder attached to a Project."

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("82e04d38-ee5a-46e4-a924-dd2026d858d8"),
                          name="Tarav.Workflow.Project.Wiki", workflow=PROJECT_WIKI_WORKFLOW_SHIP)

    @classmethod
    def _workflow_id(cls):
        return PROJECT_WIKI_WORKFLOW_SHIP

    @property
    def workflow(self):
        return ProjectWorkflow()


class ProjectWiki(TaravType):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("f1216644-d3cf-448a-b2b7-5ca8b18ea6d1"),
                          name="Tarav.Project.Wiki", workflow=PROJECT_WIKI_WORKFLOW_SHIP)

    def __init__(self, project: TaravProject):
        if not isinstance(project, TaravProject):
            raise TypeError("project must be a TaravProject")
        self.project = project

    def open(self) -> Wiki:
        return Wiki.from_path(self.project.root / "notes" / "wiki")
