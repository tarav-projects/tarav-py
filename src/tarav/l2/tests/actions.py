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
from tarav.l1.poi.actionable import BlessablePOI

from .workflow import TestsWorkflow


ACTIONS_TESTS_WORKFLOW_SHIP = WorkflowShip("f73c1415-a100-48f4-be13-4d2d7e61980e")
MARKER = "TODO"


# tarav.breadcrumb 4cce8a468688a3cb9289b0d96ee80b4e44094df1b0b37a70f6c2b4bb5fa67e62
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


class TestMarkerPOI(CheckPOI, BlessablePOI):
    """A workspace file holds marker lines."""

    __test__ = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("89a7dba4-9457-4802-96fc-d703fd5ce31c"),
                          name="Tarav.Test.Actions.MarkerPOI",
                          workflow=ACTIONS_TESTS_WORKFLOW_SHIP)


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
            details={"file": str(self.path), "lines": self.lines}),))


def workspace_checks(workspace: str | Path) -> list[Check]:
    """One check per text file of the workspace, in name order."""
    return [TestMarkerCheck(path) for path in sorted(Path(workspace).glob("*.txt"))]


def workspace_pois(workspace: str | Path) -> list[POI]:
    """Every POI the workspace's checks raise now."""
    return [poi for check in workspace_checks(workspace) for poi in check.run().pois()]


# tarav.breadcrumb 206abf4474ef638d58b0cb83951ece731a4f7c7ca76bd05a90c4f79cc5aee019
def workspace_project(workspace: str | Path) -> dict:
    """The workspace as the Project its actions are registered under."""
    return {"id": "test-workspace", "name": "test-workspace", "root": str(Path(workspace))}


def update_workspace(workspace: str | Path, runs: ActionRunStore | None = None) -> dict:
    """Run the workspace's checks and hand the results to its actions."""
    return ProjectActions(workspace_project(workspace), runs).update(
        CheckSuite(workspace_checks(workspace), name="test-workspace").run())


__all__ = [
    "ActionsTestsWorkflow", "MARKER", "TestMarkerCheck", "TestMarkerPOI",
    "update_workspace", "workspace_checks", "workspace_pois", "workspace_project",
]
