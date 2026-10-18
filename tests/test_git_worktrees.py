"""Worktree operations use Git's own registration and safety checks."""

import subprocess

import pytest

from tarav.l1.git.repository import GitError, GitRepository


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


# tarav.breadcrumb 7182ea5e5121
def test_branch_worktree_lifecycle(tmp_path):
    repository_root = tmp_path / "source"
    repository_root.mkdir()
    _git(repository_root, "init", "-q")
    _git(repository_root, "config", "user.name", "Test")
    _git(repository_root, "config", "user.email", "test@example.invalid")
    (repository_root / "data.txt").write_text("initial", encoding="utf-8")
    _git(repository_root, "add", "data.txt")
    _git(repository_root, "commit", "-qm", "initial")

    repository = GitRepository(repository_root)
    commit = repository.exact_commit("HEAD")
    destination = tmp_path / "workspace" / "source"
    created = repository.add_worktree(destination, commit=commit, branch="workspace-test")
    assert created.path == destination
    assert created.commit == commit
    assert created.branch == "workspace-test"
    assert any(item.path == destination for item in repository.worktrees())

    (destination / "data.txt").write_text("dirty", encoding="utf-8")
    with pytest.raises(GitError):
        repository.remove_worktree(destination)
    assert destination.exists()

    (destination / "data.txt").write_text("initial", encoding="utf-8")
    repository.remove_worktree(destination)
    assert not destination.exists()
    assert not any(item.path == destination for item in repository.worktrees())
    assert repository.attach_worktree(destination, branch="workspace-test").commit == commit
