"""Project associations to Models, separate from both domain cores."""

from tarav.l0.kernel import TaravClass, TaravType, TaravWorkflow, TypeShip, WorkflowShip
from tarav.l1.project.base import TaravProject
from tarav.l1.project.workflow import ProjectWorkflow

PROJECT_MODELS_WORKFLOW_SHIP = WorkflowShip("a195af42-7509-4939-aa6c-90f73c241eb5")


class ProjectModelsWorkflow(TaravWorkflow):
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

    # tarav.breadcrumb 79087186b939
    def _resolver(self):
        from tarav.l2.models.errors import require_models

        require_models()
        from tarav.l2.unsorted.storage import DiagramConfiguration

        diagram = self._diagram
        if diagram is None:
            diagram = DiagramConfiguration.load().diagram()
        return diagram

    def ls(self) -> tuple[str, ...]:
        """List configured names without loading Model storage."""
        return tuple(sorted(self._named_models()))

    def get(self, name: str):
        """Resolve one named association; unknown names raise KeyError."""
        if not isinstance(name, str):
            raise TypeError("Model name must be a string")
        ship = self._named_models()[name]
        return self._resolver().model(ship)

    def _named_models(self) -> dict[str, str]:
        from tarav.l0.kernel import Ship
        from tarav.l1.project.config import ProjectConfig
        from tarav.l2.unsorted.storage import DiagramConfig

        setting = ProjectConfig(self.project.root).section("diagram", DiagramConfig)
        models = setting.models if setting is not None else {}
        for name, ship in models.items():
            if not name.strip():
                raise ValueError("Project Model names must be non-empty strings")
            Ship(ship)
        return models

    def main(self):
        """Resolve the existing main Model, independently of named aliases."""
        return self._resolver().project_model(self.project.root)
