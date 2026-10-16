"""A Project's Git hooks: install, the scripts Git runs, dispatch and the check."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tarav.l1.git.hooks import (
    HOOKS_FOLDER,
    GitHookCall,
    GitHookHandler,
    dispatch,
    git_hook_checks,
    install,
    register_git_hook_handler,
)
from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l2.project import Project
from tarav.l3.runtime import create_runtime

CALLS: list[GitHookCall] = []


class Recorder(GitHookHandler):
    """Remembers each call; fails when Git's first argument says so."""

    __test__ = False
    name = "test-recorder"
    hooks = frozenset({"commit-msg", "post-commit"})
    attributes = ("*.rec merge=union",)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2b9e4f61-8d03-4a7c-b5e2-6f1a9c3d7e80"),
                          name="Tarav.Test.Git.Recorder")

    def run(self, call: GitHookCall) -> None:
        if call.arguments[:1] == ("fail",):
            raise RuntimeError("asked to fail")
        CALLS.append(call)


@pytest.fixture(autouse=True)
def _runtime():
    create_runtime()  # registers the `git` config section
    register_git_hook_handler(Recorder())
    CALLS.clear()


def git(root: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, env=env, capture_output=True, text=True,
                          check=True)


def project(root: Path, config: dict | None = None) -> Project:
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "Test")
    (root / ".tarav").mkdir()
    (root / ".tarav/project.json").write_text(json.dumps({
        "type": "Tarav.Project", "project_id": "20c26be7-a8e5-4974-9ec0-0b5a3a125a94",
        "created_at": "2026-10-16T00:00:00Z",
        "harness": {"environment": "env", "type": "tarav.l2.project:Project"}}))
    (root / ".tarav/config.json").write_text(json.dumps(config or {}))
    return Project.from_path(root)


def found(target: Project) -> list[tuple[str, dict]]:
    pois = []
    for check in git_hook_checks(target):
        result = check.run()
        assert result.status == "completed"
        pois += [(type(poi).__name__, {key: value for key, value in poi.situation.items()
                                       if key != "project"}) for poi in result.pois()]
    return pois


def path_with(*folders: str) -> dict:
    """An environment whose PATH has git and the shell, plus ``folders``."""
    return {**os.environ, "PATH": os.pathsep.join(
        [*folders, str(Path(shutil.which("git")).parent), "/usr/bin", "/bin"])}


def test_install_writes_the_scripts_the_handlers_need_and_points_git_there(tmp_path: Path) -> None:
    target = project(tmp_path)
    assert found(target) == []  # no `git` section: nothing to keep

    config = install(tmp_path, add=["test-recorder"])

    assert config.handlers == ["test-recorder"]
    assert json.loads((tmp_path / ".tarav/config.json").read_text()) == {
        "git": {"hooks": {"handlers": ["test-recorder"]}}}
    assert sorted(path.name for path in (tmp_path / HOOKS_FOLDER).iterdir()) == [
        "commit-msg", "post-commit"]
    assert os.access(tmp_path / HOOKS_FOLDER / "commit-msg", os.X_OK)
    assert git(tmp_path, "config", "core.hooksPath").stdout.strip() == HOOKS_FOLDER
    assert (tmp_path / ".gitattributes").read_text() == "*.rec merge=union\n"
    assert found(target) == []


def test_dispatch_runs_the_handlers_that_use_the_hook_and_turns_failures_into_warnings(
        tmp_path: Path) -> None:
    project(tmp_path, {"git": {"hooks": {"handlers": ["test-recorder", "nobody"]}}})

    warnings = dispatch(GitHookCall("commit-msg", (".git/COMMIT_EDITMSG",), tmp_path))
    assert warnings == ["No Git hook handler is named nobody"]
    assert [(call.hook, call.arguments) for call in CALLS] == [("commit-msg", (".git/COMMIT_EDITMSG",))]

    assert dispatch(GitHookCall("pre-commit", (), tmp_path))[1:] == []  # the recorder skips it
    assert len(CALLS) == 1
    assert dispatch(GitHookCall("post-commit", ("fail",), tmp_path)) == [
        "test-recorder failed in post-commit: asked to fail", "No Git hook handler is named nobody"]


def test_git_runs_the_scripts_and_a_missing_or_unknowing_tarav_never_blocks_a_commit(
        tmp_path: Path) -> None:
    project(tmp_path)
    install(tmp_path, add=["test-recorder"])
    git(tmp_path, "add", "-A")

    # The installed tarav does not know this test's handler: it warns, the commit goes through.
    with_tarav = git(tmp_path, "commit", "-m", "first", env=path_with(str(Path(sys.executable).parent)))
    assert "No Git hook handler is named test-recorder" in with_tarav.stderr

    (tmp_path / "a.txt").write_text("a")
    git(tmp_path, "add", "a.txt")
    without = git(tmp_path, "commit", "-m", "second", env=path_with())
    assert "tarav: not found on PATH; the Tarav commit-msg hook did nothing" in without.stderr
    assert git(tmp_path, "log", "--format=%s").stdout.split() == ["second", "first"]


def test_a_chained_hook_runs_first_and_its_failure_stops_the_commit(tmp_path: Path) -> None:
    project(tmp_path, {"git": {"hooks": {"handlers": ["test-recorder"], "chain": "old-hooks"}}})
    install(tmp_path)
    (tmp_path / "old-hooks").mkdir()
    old = tmp_path / "old-hooks/commit-msg"
    old.write_text('#!/bin/sh\ngrep -q ok "$1"\n')
    old.chmod(0o755)
    git(tmp_path, "add", "-A")

    refused = subprocess.run(["git", "commit", "-m", "no"], cwd=tmp_path, env=path_with(),
                             capture_output=True, text=True)
    assert refused.returncode != 0
    git(tmp_path, "commit", "-m", "ok", env=path_with())
    assert git(tmp_path, "log", "--format=%s").stdout.split() == ["ok"]


def test_the_check_reports_each_way_the_repository_drifted_from_the_config(tmp_path: Path) -> None:
    target = project(tmp_path)
    install(tmp_path, add=["test-recorder"])
    git(tmp_path, "config", "core.hooksPath", ".husky")
    (tmp_path / HOOKS_FOLDER / "commit-msg").write_text("#!/bin/sh\n")
    (tmp_path / HOOKS_FOLDER / "pre-push").write_text("#!/bin/sh\n")
    (tmp_path / HOOKS_FOLDER / "post-commit").unlink()
    (tmp_path / ".gitattributes").write_text("")
    config = json.loads((tmp_path / ".tarav/config.json").read_text())
    config["git"]["hooks"]["handlers"].append("nobody")
    (tmp_path / ".tarav/config.json").write_text(json.dumps(config))

    assert found(target) == [
        ("UnknownHookHandler", {"handler": "nobody"}),
        ("HooksNotInstalled", {"hooks_path": ".husky"}),
        ("HookStale", {"hook": "commit-msg"}),
        ("HookStale", {"hook": "post-commit"}),
        ("HookStale", {"hook": "pre-push"}),
        ("HookAttributesMissing", {"line": "*.rec merge=union"}),
    ]


def test_the_project_suite_includes_the_hooks_check(tmp_path: Path) -> None:
    target = project(tmp_path, {"git": {"hooks": {"handlers": ["test-recorder"]}}})
    suite = target.checks.suite().run()
    names = {type(poi).__name__ for poi in suite.pois()}
    assert {"HooksNotInstalled", "HookStale"} <= names
