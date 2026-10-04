"""Workspace recipes, checks, and conservative lifecycle behavior."""

import argparse
import json
import subprocess

import pytest

from tarav.l1.git.repository import GitRepository
from tarav.l0._core.project import initialize_project_layout
from tarav.l1.workspaces.depot import WorkspaceDepot, WorkspaceError
from tarav.l1.workspaces.commands import register_workspace_commands
from tarav.l1.workspaces.model import (
    CopiedDocument, NewDocument, RepositoryWorktree, WorkspaceManifest,
    WorkspaceSymlink,
)
from tarav.l2.project import Project
from tarav.l2.project.workspaces import ProjectWorkspaces


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _repository(root):
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@example.invalid")
    (root / "tracked.txt").write_text("base", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-qm", "base")
    return GitRepository(root)


# tarav.breadcrumb 53e7ef5a6e65f1dbee18a31a98f98f452d697a72ff805b884a87e8238c287f62
def test_workspace_reproduces_seeded_files_and_unique_worktree_branches(tmp_path):
    repository = _repository(tmp_path / "repo")
    source = tmp_path / "source.txt"
    source.write_text("first", encoding="utf-8")
    seeds = tmp_path / "inputs"
    seeds.mkdir()
    (seeds / "draft.txt").write_text("draft", encoding="utf-8")
    manifest = WorkspaceManifest.new(label="experiment", entries=[
        CopiedDocument(path="copied.txt", source=str(source)),
        NewDocument(path="draft.txt", seed="draft.txt"),
        WorkspaceSymlink(path="live.txt", target=str(source)),
        RepositoryWorktree(path="code", repository=str(repository.root),
                           commit=repository.exact_commit("HEAD")),
    ])
    depot = WorkspaceDepot(tmp_path / "workspaces")
    workspace = depot.create(manifest, seed_root=seeds)
    setup = depot.setup_record(workspace)
    assert (workspace.root / "copied.txt").read_text() == "first"
    assert (workspace.root / "draft.txt").read_text() == "draft"
    assert (workspace.root / "live.txt").read_text() == "first"
    assert setup.entries["code"].commit == repository.exact_commit("HEAD")
    assert not workspace.checks()[0].run().pois()

    source.write_text("second", encoding="utf-8")
    assert {poi.code for poi in workspace.checks()[0].run().pois()} == {"copy-source-changed"}
    clone = depot.clone(workspace, label="copy")
    assert clone.id != workspace.id
    assert (clone.root / "copied.txt").read_text() == "first"
    assert depot.setup_record(clone).entries["code"].branch != setup.entries["code"].branch

    (workspace.root / "draft.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(WorkspaceError) as failure:
        depot.reset(workspace)
    assert {poi.code for poi in failure.value.pois} == {"changed-document"}
    (workspace.root / "draft.txt").write_text("draft", encoding="utf-8")
    depot.reset(workspace)
    assert (workspace.root / "copied.txt").read_text() == "first"
    (workspace.root / "draft.txt").unlink()
    depot.reset(workspace)
    assert (workspace.root / "draft.txt").read_text() == "draft"

    with pytest.raises(WorkspaceError, match="Open Workspace"):
        depot.remove(workspace)
    workspace = depot.set_status(workspace, "harvested", extracted="copied")
    depot.remove(workspace)
    assert not workspace.root.exists()
    assert not any(item.path == workspace.root / "code" for item in repository.worktrees())


def test_missing_worktree_produces_poi(tmp_path):
    repository = _repository(tmp_path / "repo")
    manifest = WorkspaceManifest.new(label="missing", entries=[
        RepositoryWorktree(path="code", repository=str(repository.root),
                           commit=repository.exact_commit("HEAD")),
    ])
    depot = WorkspaceDepot(tmp_path / "workspaces")
    workspace = depot.create(manifest)
    repository.remove_worktree(workspace.root / "code")
    assert {poi.code for poi in workspace.checks()[0].run().pois()} == {"missing-worktree"}
    with pytest.raises(WorkspaceError):
        depot.reset(workspace)


# tarav.breadcrumb aa7ddb5c6a2ff71cb03ce1fa70ea9847b09bf10025a5157c5730bb55ee71d096
def test_project_workspace_discovers_two_nested_repositories(tmp_path):
    umbrella = tmp_path / "umbrella"
    umbrella.mkdir()
    initialize_project_layout(umbrella)
    first = _repository(umbrella / "first")
    second = _repository(umbrella / "second")
    project = Project.from_path(umbrella)
    assert isinstance(project.workspaces(), ProjectWorkspaces)
    integration = ProjectWorkspaces(project, depot=WorkspaceDepot(tmp_path / "depot"))
    assert integration.repositories() == [first.root, second.root]
    workspace = integration.create(label="umbrella-test")
    assert [entry.path for entry in workspace.manifest.entries] == [
        "repositories/first", "repositories/second",
    ]
    assert [item.id for item in integration.list()] == [workspace.id]
    assert not workspace.checks()[0].run().pois()


def test_completed_workspace_removal_retains_committed_branch(tmp_path):
    repository = _repository(tmp_path / "repo")
    manifest = WorkspaceManifest.new(label="committed", entries=[
        RepositoryWorktree(path="code", repository=str(repository.root),
                           commit=repository.exact_commit("HEAD")),
    ])
    depot = WorkspaceDepot(tmp_path / "workspaces")
    workspace = depot.create(manifest)
    branch = depot.setup_record(workspace).entries["code"].branch
    code = workspace.root / "code"
    (code / "tracked.txt").write_text("work", encoding="utf-8")
    with pytest.raises(WorkspaceError) as failure:
        depot.remove(depot.set_status(workspace, "abandoned"))
    assert {poi.code for poi in failure.value.pois} == {"dirty-worktree"}
    _git(code, "add", "tracked.txt")
    _git(code, "commit", "-qm", "work")
    workspace = depot.open(workspace.id)
    depot.remove(workspace)
    assert not workspace.root.exists()
    assert repository.exact_commit(branch) != manifest.entries[0].commit


def test_workspace_cli_create_list_and_check(tmp_path, capsys):
    depot_root = tmp_path / "depot"
    manifest = WorkspaceManifest.new(label="cli", entries=[])
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest.model_dump(mode="json")), encoding="utf-8")
    parser = argparse.ArgumentParser()
    register_workspace_commands(parser.add_subparsers(dest="command", required=True))
    for arguments in (
        ["workspace", "create", "--root", str(depot_root), "--manifest", str(manifest_path)],
        ["workspace", "list", "--root", str(depot_root)],
        ["workspace", "check", "--root", str(depot_root), "--id", str(manifest.id)],
    ):
        args = parser.parse_args(arguments)
        assert args.handler(args) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_known_reference_into_workspace_is_a_nonblocking_reminder(tmp_path):
    depot = WorkspaceDepot(tmp_path / "depot")
    workspace = depot.create(WorkspaceManifest.new(label="reference", entries=[]))
    outside = tmp_path / "stable.md"
    target = workspace.root / "draft.md"
    findings = depot.reference_check(source=outside, target=target).run().pois()
    assert [poi.code for poi in findings] == ["workspace-reference"]
    assert not depot.reference_check(source=workspace.root / "AGENTS.md",
                                     target=target).run().pois()


def test_missing_copy_seed_cannot_silently_fall_back_to_changed_source(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("original", encoding="utf-8")
    depot = WorkspaceDepot(tmp_path / "depot")
    workspace = depot.create(WorkspaceManifest.new(label="seed", entries=[
        CopiedDocument(path="copy.txt", source=str(source)),
    ]))
    source.write_text("later", encoding="utf-8")
    (workspace.root / "seeds" / "copy.txt").unlink()
    assert "seed-changed" in {poi.code for poi in workspace.checks()[0].run().pois()}
    with pytest.raises(WorkspaceError) as failure:
        depot.reset(workspace)
    assert "seed-changed" in {poi.code for poi in failure.value.pois}
    with pytest.raises(WorkspaceError, match="Retained copy seed is missing"):
        depot.clone(workspace, label="clone")
