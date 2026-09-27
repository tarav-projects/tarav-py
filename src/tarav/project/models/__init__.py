"""Project associations to Models, separate from both domain cores."""

from tarav.kernel import TaravClass, TaravType, TaravWorkflow, TypeShip, WorkflowShip
from tarav.project.base import TaravProject
from tarav.project.workflow import ProjectWorkflow

PROJECT_MODELS_WORKFLOW_SHIP = WorkflowShip("a195af42-7509-4939-aa6c-90f73c241eb5")


class ProjectModelsWorkflow(TaravWorkflow):
    workflow_name = "project.models"
    constitution = "Resolve Models associated with Projects without implying Model ownership."

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("4bb1cbdb-229b-4de1-9f98-88bf2932522b"),
                          name="Tarav.Workflow.Project.Models", workflow=PROJECT_MODELS_WORKFLOW_SHIP)

    @classmethod
    def _workflow_id(cls):
        return PROJECT_MODELS_WORKFLOW_SHIP

    @property
    def workflow(self):
        return ProjectWorkflow()


class ProjectModels(TaravType):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("b7b4cb96-22d4-4680-bb1d-c99e919e490c"),
                          name="Tarav.Project.Models", workflow=PROJECT_MODELS_WORKFLOW_SHIP)

    def __init__(self, project: TaravProject, *, diagram=None):
        if not isinstance(project, TaravProject):
            raise TypeError("project must be a TaravProject")
        self.project = project
        self._diagram = diagram

    def main(self):
        """Resolve the existing main Model, never creating data."""
        from tarav.unsorted.storage import DiagramConfiguration

        diagram = self._diagram
        if diagram is None:
            diagram = DiagramConfiguration.load().diagram()
        return diagram.project_model(self.project.root)
