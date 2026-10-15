"""A root Project collects listed children; each Project names its environment and Type."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from tarav.l0._core.errors import CliError
from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite
from tarav.l1.project import TaravProject
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP
from tarav.l2.project.harness import ProjectHarness
from tarav.l2.project.root import ChildProjectCheck, RootProject
from tarav.l2.project.runner import ProjectLaunchConfiguration, ProjectRunnerError
from tarav.l3 import runtime as runtime_module
from tarav.l3.project.harness import bootstrap


class _Found(Check):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6c1d4a0e-5b3f-4f62-9a8e-2d7c1e0b9f41"),
                          name="Test.Tree.Found", workflow=PROJECT_WORKFLOW_SHIP)

    def __init__(self, where: str) -> None:
        super().__init__()
        self.where = where

    def _run(self) -> CheckResult:
        poi = CheckPOI(self, f"found in {self.where}", situation={"where": self.where})
        return CheckResult(self, status="completed", pois=[poi])


class _ChildA(TaravProject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7f2e9b1c-0d4a-4c8e-b6f3-1a9d2e5c7b80"),
                          name="Test.Tree.ChildA", workflow=PROJECT_WORKFLOW_SHIP)

    # tarav.breadcrumb c22244b13cabc011727f7988826e4fb7519474b21bedc3e0353411fb1e61c4ab
    class Checks(TaravProject.Checks):
        def suite(self):
            return CheckSuite([_Found("a")])


class _ChildB(TaravProject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8a3f0c2d-1e5b-4d9f-a7c4-2b0e3f6d8c91"),
                          name="Test.Tree.ChildB", workflow=PROJECT_WORKFLOW_SHIP)

    class Checks(TaravProject.Checks):
        def suite(self):
            return CheckSuite([_Found("b")])


def _marker(root: Path, project_type: type | None = None, **fields) -> None:
    (root / ".tarav").mkdir(parents=True, exist_ok=True)
    record = {"project_id": str(uuid.uuid4()), "created_at": "2026-10-15T00:00:00Z", **fields}
    if project_type is not None:
        record["type"] = {"uuid": str(entity(project_type).id),
                          "label": entity(project_type).name}
    (root / ".tarav/project.json").write_text(json.dumps(record))


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A root with children a and b using its environment, and two unlisted folders."""
    root = tmp_path / "root"
    for name in ("a", "b", "unlisted"):
        (root / name).mkdir(parents=True)
    _marker(root, RootProject, children=["a", "b"],
            harness={"environment": "env", "type": "tarav.l2.project.root:RootProject"})
    _marker(root / "a", _ChildA,
            harness={"environment": "../env", "type": "test_project_tree:_ChildA"})
    _marker(root / "b", _ChildB,
            harness={"environment": "../env", "type": "test_project_tree:_ChildB"})
    _marker(root / "unlisted", _ChildA)
    (tmp_path / "elsewhere").mkdir()
    _marker(tmp_path / "elsewhere", _ChildA)
    (root / "link").symlink_to(tmp_path / "elsewhere")
    return root


@pytest.fixture
def in_root_environment(tree: Path, monkeypatch):
    """Load the tree as its shared harness would, then restore the runtime."""
    monkeypatch.setattr(sys, "prefix", str(tree / "env"))
    previous = runtime_module._current_runtime
    project, _ = bootstrap(path=tree)
    yield project
    runtime_module.set_runtime(previous) if previous is not None else None
    runtime_module._current_runtime = previous


def test_a_project_names_its_environment_and_its_type(tree: Path) -> None:
    launch = ProjectLaunchConfiguration.from_path(tree / "a")
    assert launch.root == (tree / "a").resolve()
    assert launch.environment == (tree / "env").resolve()  # the root's, by a plain path
    assert launch.manifest == (tree / "pyproject.toml").resolve()
    assert launch.project_type == "test_project_tree:_ChildA"
    assert ProjectHarness.from_path(path=tree / "b").command(code="pass")[:5] == [
        "-I", "-m", "tarav.l3.project.launch", "--project", str((tree / "b").resolve())]


def test_a_harness_is_declared_and_well_formed(tree: Path) -> None:
    with pytest.raises(ProjectRunnerError, match="declares no harness"):
        ProjectLaunchConfiguration.from_path(tree / "unlisted")
    _marker(tree / "a", _ChildA, harness={"environment": "../env", "type": "no colon"})
    with pytest.raises(ProjectRunnerError, match="module:Class"):
        ProjectLaunchConfiguration.from_path(tree / "a")
    _marker(tree / "a", _ChildA, harness={"project": ".."})
    with pytest.raises(ProjectRunnerError, match="invalid harness"):
        ProjectLaunchConfiguration.from_path(tree / "a")


def test_each_project_loads_as_the_type_its_harness_names(tree: Path,
                                                          in_root_environment) -> None:
    assert isinstance(in_root_environment, RootProject)
    assert [type(child) for child in in_root_environment.children()] == [_ChildA, _ChildB]
    # the Record's Type tag and harness.type must name the same class
    _marker(tree / "b", _ChildA,
            harness={"environment": "../env", "type": "test_project_tree:_ChildB"})
    with pytest.raises(TypeError, match="names the Type Test.Tree.ChildA but harness.type"):
        TaravProject.load_project(path=tree / "b")
    _marker(tree / "b", _ChildB,
            harness={"environment": "../env", "type": "test_project_tree:_Missing"})
    with pytest.raises(CliError, match="does not import"):
        TaravProject.load_project(path=tree / "b")


# tarav.breadcrumb 1b5c7c000bf93d1e3722395822537ab241bac4b01adf08fb5edc3684eabaca03
def test_the_root_runs_its_listed_children_and_nothing_else(tree: Path,
                                                            in_root_environment) -> None:
    run = in_root_environment.checks.run()
    assert [poi.situation["where"] for poi in run.pois()
            if "where" in poi.situation] == ["a", "b"]
    assert all(result.status == "completed" for result in run.results)
    assert in_root_environment.child_paths() == ("a", "b")


def test_a_missing_child_is_reported_not_skipped(tree: Path, in_root_environment) -> None:
    (tree / "b/.tarav/project.json").unlink()
    run = in_root_environment.checks.run()
    child_results = [result for result in run.results
                     if isinstance(result.check, (_Found, ChildProjectCheck))]
    assert [result.status for result in child_results] == ["completed", "incomplete"]
    assert "no Project marker at b" in child_results[1].reason


def test_a_child_with_its_own_environment_reports_its_counts(tree: Path, in_root_environment,
                                                              monkeypatch) -> None:
    _marker(tree / "b", _ChildB,
            harness={"environment": "env", "type": "test_project_tree:_ChildB"})
    (tree / "b/env/bin").mkdir(parents=True)
    (tree / "b/env/pyvenv.cfg").write_text("")
    (tree / "b/env/bin/python").write_text("")
    report = {"summary": {"incomplete": 0, "checks": 1, "pois": 2},
              "items": [{"key": "Test.Tree.Found", "pois": 2, "checks": 1}]}
    calls = []
    real_run = subprocess.run

    def fake_run(command, **kwargs):
        if command[0] == "git":  # the suites read the state of their repositories
            return real_run(command, **kwargs)
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, stdout=json.dumps(report) + "\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    run = in_root_environment.checks.run()
    child = run.results_of(ChildProjectCheck)[0]
    assert calls[0][0] == str((tree / "b/env/bin/python").resolve())
    assert (child.status, len(child.pois())) == ("completed", 1)
    assert child.pois()[0].details["pois"] == 2


def test_listed_children_must_lie_below_the_root(tree: Path, in_root_environment) -> None:
    in_root_environment.fields["children"] = ["../elsewhere"]
    with pytest.raises(ProjectRunnerError, match="below the root"):
        in_root_environment.child_paths()
    with pytest.raises(CliError):
        in_root_environment.child("link")


# tarav.breadcrumb 31b79ffae1aafbd075e9ea96757d902a9b7cb0cb485f88ec9e127d26bf691988
def test_a_root_status_lets_each_project_update_its_own_actions(tree: Path,
                                                                in_root_environment) -> None:
    root = in_root_environment
    assert [type(member) for member in root.members()] == [_ChildA, _ChildB]
    assert [result.check.where for result in root.checks.run().results_of(_Found)] == ["a", "b"]
    assert root.checks.own().run().results_of(_Found) == ()

    status = root.status()
    assert [found.project.name for found in status.each()] == ["root", "a", "b"]
    assert [len(found.checks.results_of(_Found)) for found in status.each()] == [0, 1, 1]
    assert len(status.suite().results_of(_Found)) == 2
    acted = status.acted()
    assert [project["name"] for project in acted["projects"]] == ["root", "a", "b"]
    assert acted["opened"] == acted["actions"] == len(status.suite().pois())

    def found(project) -> list:
        return [run.data["event"]["poi"]["situation"] for run in project.actions.list(own=True)
                if run.data["event"]["check"]["type"] == "Test.Tree.Found"]

    a, b = root.members()
    assert (found(root), found(a), found(b)) == ([], [{"where": "a"}], [{"where": "b"}])

    # the child alone sees the same actions
    again = a.status()
    assert again.actions["opened"] == 0 and found(a) == [{"where": "a"}]


# tarav.breadcrumb 088a6a09cea670f4d80324c13057d6f3d26c811a8fedd1ca0e85622303f0f27c
def test_a_root_sees_the_actions_of_the_projects_it_lists(tree: Path, in_root_environment,
                                                          capsys) -> None:
    from tarav.l1.actions.commands import register_action_commands
    from tarav.l1.project.scope import project_scope
    import argparse

    root = in_root_environment
    root.status()
    a, b = root.members()
    def roots(*parts: str) -> set[str]:
        return {str((tree / part).resolve()) for part in parts}

    assert set(project_scope(tree)) == roots(".", "a", "b")
    assert set(project_scope(tree / "a")) == roots("a")
    assert set(project_scope(tree / "unlisted")) == roots("unlisted")  # below, but not listed

    # the root sees what its children hold; each action still names its own Project
    seen = root.actions.list()
    assert len(seen) == len(root.actions.list(own=True)) + len(a.actions.list()) + len(b.actions.list())
    assert {run.data["project"]["name"] for run in seen} >= {"a", "b"}
    assert all(run.data["project"]["name"] == "a" for run in a.actions.list())

    parser = argparse.ArgumentParser()
    register_action_commands(parser.add_subparsers())
    args = parser.parse_args(["action", "list", "--project", str(tree), "--json"])
    args.handler(args)
    listed = json.loads(capsys.readouterr().out)
    assert len(listed["actions"]) == len(seen) and set(listed["projects"]) == roots(".", "a", "b")
    args = parser.parse_args(["action", "list", "--project", str(tree), "--own", "--json"])
    args.handler(args)
    assert len(json.loads(capsys.readouterr().out)["actions"]) == len(root.actions.list(own=True))
    args = parser.parse_args(["action", "list", "--project", str(tree)])
    args.handler(args)
    out = capsys.readouterr().out
    assert "Projects: root " in out and "--own lists only the first." in out
