"""Featured Project integrations with Models and Wiki."""

from tarav.l0.kernel import NamespaceBase, TaravClass, TypeShip
from tarav.l1.project import TaravProject
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP

from .runner import (
    PROJECT_RUNNER_RECORD_TYPES,
    ProjectLaunchConfiguration,
    ProjectRunnerConfigurator,
    ProjectRunnerError,
)


class Project(TaravProject):
    """Tarav's featured project, with optional Models and Wiki access."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip("a5f2412f-1c41-4299-9bcd-90cf38685516"),
                          name="Tarav.Project", workflow=PROJECT_WORKFLOW_SHIP)

    # tarav.breadcrumb c45b62790b589c7dca7f19cf431ca868cdb8739dcd1842b306ba54bdc9721689
    class Docs(NamespaceBase["Project"]):
        """Documentation attached to a Project."""

        @property
        def wiki(self):
            from .wiki import ProjectWiki
            return ProjectWiki(self.obj).open()

    @property
    def docs(self) -> Docs:
        return type(self).Docs(self)

    @property
    def models(self):
        from .models import ProjectModels
        return ProjectModels(self)

    # tarav.breadcrumb ead5ff16cd263a233872279d3931b33bcd85eeedd12400506fccdcd6470802de
    def workspaces(self):
        from .workspaces import ProjectWorkspaces
        return ProjectWorkspaces(self)

    # tarav.breadcrumb 060a215350155cc5aae758df05ae3113dc6967b15fd4cda50852d9327456335b
    def decisions(self):
        """This Project's Decisions: every subtype, blessings included."""
        from .decisions import ProjectDecisions

        return ProjectDecisions(self)

    # tarav.breadcrumb 99811cb8c39c0f0f8a3111bca58e6e7dfcf146cb5aa168c1f9f6e5a8d643ba87
    def poi_board(self, *, blessings=None, decisions=None):
        """Open this Project's tracked-POI board without creating its stores."""
        from tarav.l1.poi import TrackedPOIStore
        from tarav.l2.poi import TrackedPOIBoard

        decisions = decisions or self.decisions()
        if blessings is None and hasattr(decisions, "blessings"):
            blessings = decisions.blessings()
        return TrackedPOIBoard(
            TrackedPOIStore(self.root / ".tarav" / "tracked-pois"),
            blessings=blessings,
            decisions=decisions,
        )


__all__ = [
    "PROJECT_RUNNER_RECORD_TYPES",
    "Project",
    "ProjectLaunchConfiguration",
    "ProjectRunnerConfigurator",
    "ProjectRunnerError",
]
