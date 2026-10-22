"""tarav-change through real Git commits: every mode, amend, rebase, find and the check."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tarav.l1.git import GitError, GitRepository
from tarav.l1.git.change import CHANGES_FILE, TaravChangeCheck, find
from tarav.l1.git.hooks import install
from tarav.l1.git.witness import ChangeWitnesses
from tarav.l2.project import Project
from tarav.l3.runtime import create_runtime


PROJECT_ID = "20c26be7-a8e5-4974-9ec0-0b5a3a125a94"


@pytest.fixture(autouse=True)
def _runtime(monkeypatch, tmp_path_factory):
    create_runtime()  # registers tarav-change and the `git` config section
    # The hook scripts call the `tarav` of this environment, with its witness and actions here.
    monkeypatch.setenv("PATH", os.pathsep.join([str(Path(sys.executable).parent), os.environ["PATH"]]))
    monkeypatch.setenv("TARAV_GIT_CHANGES_ROOT", str(tmp_path_factory.mktemp("witness")))
    monkeypatch.setenv("TARAV_RECORDS", str(tmp_path_factory.mktemp("records")))
    monkeypatch.delenv("TARAV_GIT_HOOKS_OVERRULE", raising=False)


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True).stdout


def repository(root: Path, *, commit: bool = True) -> Path:
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "Test")
    (root / ".tarav").mkdir()
    (root / ".tarav/project.json").write_text(json.dumps({
        "type": "Tarav.Project", "project_id": PROJECT_ID,
        "created_at": "2026-10-16T00:00:00Z",
        "harness": {"environment": "env", "type": "tarav.l2.project:Project"}}))
    (root / ".tarav/config.json").write_text("{}")
    install(root, add=["tarav-change"])
    if commit:
        git(root, "add", "-A")
        git(root, "commit", "-qm", "Install the hooks")
    return root


def carried(root: Path, revision: str = "HEAD") -> tuple[list[str], list[str]]:
    """The IDs a commit added to the file, and the IDs its trailers carry."""
    diff = git(root, "diff", f"{revision}^", revision, "--", CHANGES_FILE)
    added = [line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]
    trailers = git(root, "log", "-1", "--format=%(trailers:key=tarav-change,valueonly)", revision)
    return added, trailers.split()


def edit(root: Path, name: str, text: str) -> None:
    with (root / name).open("a") as handle:
        handle.write(text + "\n")


def test_every_commit_mode_carries_one_id_in_its_trailer_and_its_file(tmp_path: Path) -> None:
    root = repository(tmp_path)
    edit(root, "a.txt", "plain")
    git(root, "add", "a.txt")
    git(root, "commit", "-qm", "plain")
    edit(root, "a.txt", "all")
    git(root, "commit", "-qam", "all")
    edit(root, "a.txt", "paths")
    git(root, "commit", "-qm", "paths", "a.txt")
    edit(root, "a.txt", "tarav")
    GitRepository(root).commit(["a.txt"], "through tarav git commit")

    seen = []
    for revision in ("HEAD~3", "HEAD~2", "HEAD~1", "HEAD"):
        added, trailers = carried(root, revision)
        assert len(added) == 1 and added == trailers
        seen += added
    assert len(set(seen)) == 4
    assert git(root, "status", "--short") == ""  # the index matches HEAD in every mode
    assert find(root, seen[2]) == (git(root, "rev-parse", "HEAD~1").strip(),)


def test_the_first_hooked_commit_through_tarav_git_commit_leaves_the_index_clean(
        tmp_path: Path) -> None:
    root = repository(tmp_path, commit=False)
    GitRepository(root).commit([".gitattributes", ".tarav/project.json", ".tarav/config.json",
                                ".tarav/git-hooks"], "Install the hooks")
    assert git(root, "status", "--short") == ""
    trailers = git(root, "log", "-1", "--format=%(trailers:key=tarav-change,valueonly)").split()
    assert len(trailers) == 1 and trailers == git(root, "show", f"HEAD:{CHANGES_FILE}").split()


def test_an_amended_commit_gains_an_id_and_the_old_one_still_finds_it(tmp_path: Path) -> None:
    root = repository(tmp_path)
    edit(root, "a.txt", "first")
    git(root, "add", "a.txt")
    git(root, "commit", "-qm", "first")
    [before], _ = carried(root)

    git(root, "commit", "-q", "--amend", "-m", "first, amended")
    amended = git(root, "rev-parse", "HEAD").strip()
    added, trailers = carried(root)
    [after] = trailers
    assert added == [before, after]
    assert find(root, before) == (amended,) and find(root, after) == (amended,)
    assert git(root, "status", "--short") == ""


def test_a_rebase_keeps_the_ids_and_records_the_rewrite(tmp_path: Path) -> None:
    root = repository(tmp_path)
    git(root, "checkout", "-qb", "topic")
    edit(root, "b.txt", "topic")
    git(root, "add", "b.txt")
    git(root, "commit", "-qm", "topic")
    [change], _ = carried(root)
    old = git(root, "rev-parse", "HEAD").strip()
    git(root, "checkout", "-q", "main")
    edit(root, "a.txt", "main")
    git(root, "add", "a.txt")
    git(root, "commit", "-qm", "main")
    git(root, "checkout", "-q", "topic")

    git(root, "rebase", "-q", "main")  # both appended to the file; merge=union joins them

    new = git(root, "rev-parse", "HEAD").strip()
    assert new != old
    assert find(root, change) == (new,)
    assert carried(root) == ([change], [change])
    rewrites = (root / ".git/tarav/rewrites.jsonl").read_text().splitlines()
    assert [(item["command"], item["old"], item["new"]) for item in map(json.loads, rewrites)] == [
        ("rebase", old, new)]


def test_the_check_reports_commits_made_without_the_hooks(tmp_path: Path) -> None:
    root = repository(tmp_path)
    project = Project.from_path(root)
    edit(root, "a.txt", "hooked")
    git(root, "add", "a.txt")
    git(root, "commit", "-qm", "hooked")
    assert TaravChangeCheck(project.root).run().pois() == ()

    edit(root, "a.txt", "skipped")
    git(root, "add", "a.txt")
    git(root, "commit", "-q", "--no-verify", "-m", "skipped the hooks")
    skipped = git(root, "rev-parse", "HEAD").strip()

    [poi] = TaravChangeCheck(project.root).run().pois()
    assert poi.situation["commit"] == skipped
    assert poi.message == f"Commit {skipped[:7]} carries no tarav-change: skipped the hooks"
    assert {type(item).__name__ for item in project.checks.suite().run().pois()} >= {"TaravChangeMissing"}


def test_find_rejects_what_is_not_an_id_and_the_cli_prints_the_commits(tmp_path: Path) -> None:
    root = repository(tmp_path)
    [change] = git(root, "show", f"HEAD:{CHANGES_FILE}").split()  # the install commit's
    with pytest.raises(ValueError, match="lowercase UUID"):
        find(root, "HEAD")
    printed = subprocess.run(["tarav", "git", "change", "find", "--id", change, "--repo", str(root),
                              "--json"], capture_output=True, text=True, check=True).stdout
    assert json.loads(printed) == {"change": change,
                                   "commits": [git(root, "rev-parse", "HEAD").strip()]}


@pytest.mark.parametrize(("hook", "accepted"), [
    ('printf "\\nsigned-off-by: someone\\n" >> "$1"', True),
    ('echo "rewritten" > "$1"', False),
])
def test_tarav_git_commit_accepts_hook_trailers_and_nothing_else(tmp_path: Path, hook: str,
                                                                  accepted: bool) -> None:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks/commit-msg").write_text(f"#!/bin/sh\n{hook}\n")
    (tmp_path / "hooks/commit-msg").chmod(0o755)
    git(tmp_path, "config", "core.hooksPath", "hooks")
    edit(tmp_path, "a.txt", "a")
    if accepted:
        GitRepository(tmp_path).commit(["a.txt"], "prepared")
        assert git(tmp_path, "log", "-1", "--format=%B").strip() == "prepared\n\nsigned-off-by: someone"
    else:
        with pytest.raises(GitError, match="apart from trailers its hooks added"):
            GitRepository(tmp_path).commit(["a.txt"], "prepared")


def committed(root: Path, message: str, **environment: str) -> subprocess.CompletedProcess:
    edit(root, "a.txt", message)
    git(root, "add", "a.txt")
    return subprocess.run(["git", "commit", "-m", message], cwd=root, capture_output=True, text=True,
                          env={**os.environ, **environment})


def actions(root: Path) -> list[tuple[str, dict]]:
    """The POI type and situation of each action registered on the Project, oldest first."""
    # tarav.breadcrumb 16c9374e62d4
    from tarav.l1.project.actions import ActionManager

    runs = ActionManager(Project.from_path(root)).list(own=True)
    return sorted(((run.data["event"]["poi"]["type"],
                    {key: value for key, value in run.data["event"]["poi"]["situation"].items()
                     if key in ("branch", "commit")}) for run in runs), key=str)


def found(root: Path) -> list[tuple[str, dict]]:
    pois = TaravChangeCheck(root).run().pois()
    return [(type(poi).__name__, {key: value for key, value in poi.situation.items()
                                  if key in ("branch", "commit")}) for poi in pois]


def drop_first_line(root: Path) -> str:
    path = root / CHANGES_FILE
    first, *rest = path.read_text().splitlines()
    path.write_text("".join(line + "\n" for line in rest))
    return first


def test_the_witness_takes_each_commits_ids(tmp_path: Path) -> None:
    root = repository(tmp_path)
    committed(root, "second")
    witness = ChangeWitnesses().get(PROJECT_ID, "main")
    assert witness.changes == (root / CHANGES_FILE).read_text().split()
    assert len(witness.changes) == 2


def test_a_lost_id_stops_the_commit_and_opens_an_action(tmp_path: Path) -> None:
    root = repository(tmp_path)
    committed(root, "second")
    before = git(root, "rev-parse", "HEAD").strip()
    lost = drop_first_line(root)

    stopped = committed(root, "third")

    assert stopped.returncode != 0 and git(root, "rev-parse", "HEAD").strip() == before
    assert f"1 tarav-change IDs that main had at its last commit are gone from {CHANGES_FILE} ({lost})" \
        in stopped.stderr
    assert "TARAV_GIT_HOOKS_OVERRULE=tarav-change" in stopped.stderr
    assert actions(root) == [("Tarav.Git.Change.Removed", {"branch": "main"})]
    assert lost not in (root / CHANGES_FILE).read_text()  # nothing was appended either


def test_an_overrule_commits_records_itself_and_moves_the_witness(tmp_path: Path) -> None:
    root = repository(tmp_path)
    committed(root, "second")
    lost = drop_first_line(root)

    passed = committed(root, "third", TARAV_GIT_HOOKS_OVERRULE="tarav-change")

    assert passed.returncode == 0, passed.stderr
    head = git(root, "rev-parse", "HEAD").strip()
    [overrule] = ChangeWitnesses().overrules(PROJECT_ID)
    assert (overrule.branch, overrule.commit, overrule.missing) == ("main", head, [lost])
    assert lost not in ChangeWitnesses().get(PROJECT_ID, "main").changes
    assert actions(root) == [("Tarav.Git.Change.Overruled", {"branch": "main", "commit": head})]
    assert found(root) == [("TaravChangeOverruled", {"branch": "main", "commit": head})]
    assert committed(root, "fourth").returncode == 0  # the witness accepted the rewrite


def test_the_check_sees_a_rewrite_between_commits_and_a_commit_that_skipped_the_hooks(
        tmp_path: Path) -> None:
    root = repository(tmp_path)
    committed(root, "second")
    git(root, "reset", "-q", "--hard", "HEAD~1")  # cuts the second commit's ID
    assert found(root) == [("TaravChangeRemoved", {"branch": "main"})]

    drop_first_line(root)
    git(root, "commit", "-qam", "skips the hooks", "--no-verify")
    assert [name for name, _ in found(root)].count("TaravChangeRemoved") == 1
    assert len(ChangeWitnesses().get(PROJECT_ID, "main").changes) == 2  # kept, so it keeps reporting


def test_each_branch_has_its_own_witness(tmp_path: Path) -> None:
    root = repository(tmp_path)
    committed(root, "second")
    git(root, "checkout", "-qb", "older", "HEAD~1")  # lacks main's latest ID, legitimately
    assert committed(root, "on older").returncode == 0
    assert len(ChangeWitnesses().get(PROJECT_ID, "older").changes) == 2
    assert len(ChangeWitnesses().get(PROJECT_ID, "main").changes) == 2
