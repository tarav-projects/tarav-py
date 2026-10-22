"""Featured Project integrations with Wiki."""

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
from .skw import SkwManager


class Project(TaravProject):
    """Tarav's featured project, with Wiki access."""

    # tarav.breadcrumb b5f1123150af
    Skw = SkwManager

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip("a5f2412f-1c41-4299-9bcd-90cf38685516"),
                          name="Tarav.Project", workflow=PROJECT_WORKFLOW_SHIP)

    # tarav.breadcrumb 06121c678478
    # tarav.breadcrumb 961c0af675b5
    class Checks(TaravProject.Checks):
        def suite(self) -> CheckSuite:
            """The Project's checks, and its test fixtures while `.tarav/tests/` exists."""
            from tarav.l2.tests.actions import TestFixturesSuite
            # tarav.breadcrumb b4812048cdc1
            from tarav.l2.project.notebook_checks import ProjectNotebookSuite
            from tarav.l2.git.archive import OwnedRepositorySuite
            # tarav.breadcrumb 01089efbfdf1

            return CheckSuite([super().suite(), ProjectNotebookSuite(self.obj), OwnedRepositorySuite(self.obj),
                               CheckSuite(lambda run: TestFixturesSuite.present(self.obj.root))],
                              name=self.obj.name, repositories=self.obj.repositories())

    # tarav.breadcrumb c45b62790b58
    class Docs(NamespaceBase["Project"]):
        """Documentation attached to a Project."""

        @property
        def wiki(self):
            from .wiki import ProjectWiki
            return ProjectWiki(self.obj).open()

    @property
    def docs(self) -> Docs:
        return type(self).Docs(self)

    # tarav.breadcrumb ead5ff16cd26
    def workspaces(self):
        from .workspaces import ProjectWorkspaces
        return ProjectWorkspaces(self)

    # tarav.breadcrumb 060a21535015
    def decisions(self):
        """This Project's Decisions, every subtype."""
        from .decisions import ProjectDecisions

        return ProjectDecisions(self)

    # tarav.breadcrumb 5497fcfeb1d2
    def notebook_layout(self):
        """The initial layout; Project subtypes may choose other Block Types."""
        from tarav.l2.notebook import ArchiveBlock, DiscussionBlock, ModelBlock

        return (DiscussionBlock, ModelBlock, ArchiveBlock)

    # tarav.breadcrumb db2a7942d72a
    def notebook(self, *, notebook=None):
        """Select this Project's notebook without creating storage."""
        from .notebook import project_notebook

        return project_notebook(self, notebook=notebook, block_types=self.notebook_layout())


__all__ = [
    "PROJECT_RUNNER_RECORD_TYPES",
    "Project",
    "ProjectLaunchConfiguration",
    "ProjectRunnerConfigurator",
    "ProjectRunnerError",
]
