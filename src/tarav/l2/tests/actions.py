"""A disposable workspace whose POIs are followed by actions.

The workspace is a folder of text files. A line holding the marker word
raises a POI for its file, and that POI spins its action. The workspace
stands in for a Project: its suite is owned, so a run of it resolves actions.
"""

from __future__ import annotations

__test__ = False

from pathlib import Path

from tarav.l0.kernel.identity import TypeShip, WorkflowShip
from tarav.l0.kernel.records import TaravClass
from tarav.l1.actions import ActionRunStore
from tarav.l1.actions.project import ProjectActions
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite, SituationCheck
from tarav.l1.poi import POI
from tarav.l1.actions.pois import BlessableResolution

from .workflow import TestsWorkflow


ACTIONS_TESTS_WORKFLOW_SHIP = WorkflowShip("f73c1415-a100-48f4-be13-4d2d7e61980e")
MARKER = "TODO"


# tarav.breadcrumb 4cce8a468688
class ActionsTestsWorkflow(TestsWorkflow):
    """Synthetic workspace for trying Actions over POIs and blessings."""

    __test__ = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("7a203c7c-661f-42ba-92d6-d4320d87d88f"),
            name="Tarav.Workflow.Tests.Actions",
            workflow=ACTIONS_TESTS_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return ACTIONS_TESTS_WORKFLOW_SHIP

    @property
    def workflow(self):
        return TestsWorkflow()

    constitution = "Exercise Actions with a disposable workspace of files, POIs and blessings."


class TestMarkerPOI(CheckPOI):
    """A workspace file holds marker lines."""

    __test__ = False
    action = "Tarav.Test.Actions.MarkerPOI.Resolution"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("89a7dba4-9457-4802-96fc-d703fd5ce31c"),
                          name="Tarav.Test.Actions.MarkerPOI",
                          workflow=ACTIONS_TESTS_WORKFLOW_SHIP)


class TestMarkerResolution(BlessableResolution):
    """The action of a TestMarkerPOI; it may be blessed."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("155d3548-d8da-491c-bbb7-589c282d51f5"),
                          name="Tarav.Test.Actions.MarkerPOI.Resolution", workflow=ACTIONS_TESTS_WORKFLOW_SHIP)


class TestMarkerCheck(SituationCheck):
    """Does one workspace file hold marker lines?

    The situation is what was found: the file and those lines.
    """

    __test__ = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("1f0f6f0e-6d0f-4c5d-9a37-6a7d9f1b2c41"),
                          name="Tarav.Test.Actions.MarkerCheck",
                          workflow=ACTIONS_TESTS_WORKFLOW_SHIP)

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.lines = [line.strip() for line in self.path.read_text(encoding="utf-8").splitlines()
                      if MARKER in line]
        super().__init__(situation={"file": self.path.name, "lines": self.lines})

    def _run(self) -> CheckResult:
        if not self.lines:
            return CheckResult(self, status="completed")
        return CheckResult(self, status="completed", pois=(self.poi(
            TestMarkerPOI, message=f"{self.path.name} holds {len(self.lines)} marker line(s)",
            details={"file": str(self.path)}),))


def workspace_checks(workspace: str | Path) -> list[Check]:
    """One check per text file of the workspace, in name order."""
    return [TestMarkerCheck(path) for path in sorted(Path(workspace).glob("*.txt"))]


def workspace_pois(workspace: str | Path) -> list[POI]:
    """Every POI the workspace's checks raise now."""
    return [poi for check in workspace_checks(workspace) for poi in check.run().pois()]


FIXTURES = ".tarav/tests"


# tarav.breadcrumb 1363e5fa344c
# tarav.breadcrumb ecb8f5c2a800
class TestFixturesSuite(CheckSuite):
    """The test fixtures of a Project: the files of `.tarav/tests/`, checked on the live path.

    An agent and the User put files there to watch real actions react; the
    actions are registered under the Project like any other. The folder
    holds a `.gitignore` of `*`, so it never makes a repository dirty.
    Removing the folder ends the suite, and its actions close as gone.
    """

    __test__ = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("cfba3228-972f-4c40-80dc-5d079632ad07"),
                          name="Tarav.Test.Actions.Fixtures",
                          workflow=ACTIONS_TESTS_WORKFLOW_SHIP)

    def __init__(self, project_root: str | Path) -> None:
        self.folder = Path(project_root) / FIXTURES
        super().__init__(lambda suite: workspace_checks(self.folder), name="test fixtures",
                         key=FIXTURES)

    @classmethod
    def present(cls, project_root: str | Path) -> "list[TestFixturesSuite]":
        """The Project's fixtures suite while its folder exists, otherwise none."""
        return [cls(project_root)] if (Path(project_root) / FIXTURES).is_dir() else []


# tarav.breadcrumb 206abf4474ef
def workspace_project(workspace: str | Path) -> dict:
    """The workspace as the Project its actions are registered under."""
    return {"id": "test-workspace", "name": "test-workspace", "root": str(Path(workspace))}


def update_workspace(workspace: str | Path, runs: ActionRunStore | None = None) -> dict:
    """Run the workspace's checks and hand the results to its actions."""
    return ProjectActions(workspace_project(workspace), runs).update(
        CheckSuite(workspace_checks(workspace), name="test-workspace").run())


__all__ = [
    "ActionsTestsWorkflow", "FIXTURES", "MARKER", "TestFixturesSuite", "TestMarkerCheck", "TestMarkerPOI",
    "update_workspace", "workspace_checks", "workspace_pois", "workspace_project",
]
