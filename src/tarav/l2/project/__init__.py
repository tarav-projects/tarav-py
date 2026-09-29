"""Featured Project integrations with Models and Wiki."""

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.project import TaravProject
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP


class Project(TaravProject):
    """Tarav's featured project, with optional Models and Wiki access."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip("a5f2412f-1c41-4299-9bcd-90cf38685516"),
                          name="Tarav.Project", workflow=PROJECT_WORKFLOW_SHIP)

    def models(self):
        from .models import ProjectModels
        return ProjectModels(self)

    def wiki(self):
        from .wiki import ProjectWiki
        return ProjectWiki(self).open()


__all__ = ["Project"]
