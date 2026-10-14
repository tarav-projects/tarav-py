"""Featured Project integrations with Models and Wiki."""

from tarav.l0.kernel import NamespaceBase, TaravClass, TypeShip
from tarav.l1.checks import CheckSuite
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

    # tarav.breadcrumb 06121c6784784eb89691b23fcc74b31b83476bb35d089df8b38b5f5fcbcfc48b
    # tarav.breadcrumb 961c0af675b5234e34b528c13823337174b4482463a62def0c482ae5df9c8b41
    class Checks(TaravProject.Checks):
        def suite(self) -> CheckSuite:
            """The Project's checks, and its test fixtures while `.tarav/tests/` exists."""
            from tarav.l2.tests.actions import TestFixturesSuite

            return CheckSuite([super().suite(),
                               CheckSuite(lambda run: TestFixturesSuite.present(self.obj.root))],
                              name=self.obj.name, repositories=self.obj.repositories())

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
        """This Project's Decisions, every subtype."""
        from .decisions import ProjectDecisions

        return ProjectDecisions(self)


__all__ = [
    "PROJECT_RUNNER_RECORD_TYPES",
    "Project",
    "ProjectLaunchConfiguration",
    "ProjectRunnerConfigurator",
    "ProjectRunnerError",
]
