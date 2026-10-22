"""Project Classes select managers, which own and extend integration loops."""

from pathlib import Path

import pytest

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l0.testing import DEFAULT_TEST_PROJECT_ID, write_raw_json
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite
from tarav.l1.project import TaravProject
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP
from tarav.l1.records import RecordRegistry
from tarav.l2.project import Project
from tarav.l2.project.skw import SkillLoadCheck
from tarav.l3.runtime import create_runtime, get_runtime, set_runtime


class TaskCheck(Check):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("0b94e76f-eed4-4d03-b6fa-838c6f143b23"),
                          name="Test.ProjectManagers.Task", workflow=PROJECT_WORKFLOW_SHIP)

    def __init__(self, project):
        super().__init__()
        self.project = project

    def _run(self):
        pois = [CheckPOI(self, "Task remains", situation={"project": str(self.project.id)})
                ] if (self.project.root / "todo").is_file() else []
        return CheckResult(self, status="completed", pois=pois)


# tarav.breadcrumb 2c7afbed54e9
# tarav.breadcrumb 143731247f39
class ManagedProject(Project):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("25ca306a-18e8-41a6-8f37-54556c76a701"),
                          name="Test.ProjectManagers.Project", workflow=PROJECT_WORKFLOW_SHIP)

    class Checks(Project.Checks):
        def suite(self):
            return CheckSuite([TaskCheck(self.obj)])

    class Actions(Project.Actions):
        def status(self, **options):
            self.obj.events.append("loop")
            return super().status(**options)

        def update(self, checks):
            self.obj.events.append("results")
            return super().update(checks)

    class Records(Project.Records):
        @property
        def registry(self):
            return RecordRegistry(self.obj.root / "record-store", records=self.types)

    class Skw(Project.Skw):
        @property
        def depot(self):
            return self.obj.root / "sources"

        def skill_depots(self):
            return (self.depot / "broken",)


@pytest.fixture
def project(tmp_path):
    previous = get_runtime()
    set_runtime(create_runtime())
    try:
        _marker(tmp_path)
        project = ManagedProject.from_path(tmp_path)
        project.events = []
        yield project
    finally:
        set_runtime(previous)


def _marker(root, project_id=DEFAULT_TEST_PROJECT_ID):
    write_raw_json(root / ".tarav/project.json", {
        "project_id": project_id, "created_at": "2026-10-22T00:00:00Z"})


def test_a_project_selects_all_four_managers_without_provisioning(project):
    assert type(project.actions) is ManagedProject.Actions
    assert type(project.checks) is ManagedProject.Checks
    assert type(project.records) is ManagedProject.Records
    assert type(project.skw) is ManagedProject.Skw
    assert all(manager.obj is project for manager in (
        project.actions, project.checks, project.records, project.skw))
    assert project.actions.list() == []
    assert not (project.root / "record-store").exists()
    assert project.records.to_record()["project_id"] == str(project.id)
    assert ManagedProject.records.record_example()["type"] == "Test.ProjectManagers.Project"


def test_the_selected_manager_owns_the_status_loop_and_record_storage(project):
    (project.root / "todo").write_text("work remains")
    checks = project.checks.run()
    assert [poi.message for poi in checks.pois()] == ["Task remains"]
    assert project.events == [] and project.actions.list() == []

    status = project.status()
    assert status.project is project
    assert status.actions["opened"] == 1
    assert project.events == ["loop", "results"]
    [action] = project.actions.list()
    assert action.data["project"]["id"] == str(project.id)
    assert action.state == "running"
    assert project.actions.runs.map.root.parent == project.root / "record-store"

    (project.root / "todo").unlink()
    assert project.actions.status().actions["gone"] == 1
    assert project.events == ["loop", "results", "loop", "results"]
    assert project.actions.list()[0].exit == "gone"


def test_skw_manager_binds_documents_and_supplies_its_selected_depot_checks(project):
    with pytest.raises(ValueError, match="No sources depot found"):
        project.skw.document("guide.skw.json")
    assert not (project.root / "sources").exists()
    write_raw_json(project.root / "sources/src/guide.skw.json", {
        "type": "Tarav.Skillware.Document", "schema_version": 1,
        "output": "guide.md", "blocks": []})
    document = project.skw.document("guide.skw.json")
    assert document.source == project.root / "sources/src/guide.skw.json"
    assert not (project.root / "guide.md").exists()
    checks = project.skw.checks().run()
    assert len(checks.results) == 1
    result = checks.results[0]
    assert isinstance(result.check, SkillLoadCheck)
    assert result.check.skill == project.root / "sources/broken"
    assert result.status == "incomplete"
    assert project.actions.list() == []


def test_the_loop_enters_each_member_through_its_selected_action_manager(project):
    root = project.root / "child"
    _marker(root, "00000000-0000-4000-8000-000000000002")
    child = ManagedProject.from_path(root)
    child.events = []
    (root / "todo").write_text("child task")
    project.members = lambda: (child,)

    status = project.actions.status()
    assert status.actions["opened"] == 0
    assert status.members[0].project is child
    assert status.members[0].actions["opened"] == 1
    assert project.events == child.events == ["loop", "results"]
    assert project.actions.list() == []  # visibility still follows listed Project markers
    assert child.actions.list()[0].data["project"]["id"] == str(child.id)


def test_minimal_project_exposes_the_same_manager_contract(tmp_path: Path):
    _marker(tmp_path)
    project = TaravProject.from_path(tmp_path)
    assert project.skw.depot == tmp_path / ".tarav/skillware"
    assert project.records.to_record()["project_id"] == str(project.id)
    assert project.checks.obj is project and project.actions.obj is project
