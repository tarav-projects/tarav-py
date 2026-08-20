"""Slice 5: the depot's git configuration is one repo path, and a write never fails on it."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from tarav.bloberia import BloberiaDepot
from tarav.bloberia.core import InvalidBloberiaInputError
from tarav.bloberia.git import GitCheckpoint


def _repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for args in (
        ("init", "-q"),
        ("config", "user.email", "t@example.com"),
        ("config", "user.name", "t"),
    ):
        subprocess.run(("git", "-C", str(path), *args), check=True, capture_output=True)
    return path


def _log(repo: Path) -> list[str]:
    out = subprocess.run(
        ("git", "-C", str(repo), "log", "--format=%s"),
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in out.stdout.splitlines() if line]


class TestConfiguration:
    def test_a_relative_git_path_resolves_from_meta_json(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path / "project")
        depot = BloberiaDepot(repo / ".tarav" / "index", git="../..")
        depot.insert({"k": 1})
        assert depot.git is not None
        assert depot.git.repo == repo.resolve()

    def test_an_absolute_git_path_is_taken_as_given(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path / "elsewhere")
        depot = BloberiaDepot(tmp_path / "depot", git=str(repo))
        depot.insert({"k": 1})
        assert depot.git is not None
        assert depot.git.repo == repo.resolve()

    def test_configuration_persists_in_meta_and_is_read_back(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path / "project")
        BloberiaDepot(repo / "depot", git="..", git_interval_seconds=1).insert({"k": 1})

        reopened = BloberiaDepot(repo / "depot")
        assert reopened.git is not None
        assert reopened.git.interval_seconds == 1

    def test_a_redeclared_git_path_keeps_the_stored_interval(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path / "project")
        BloberiaDepot(repo / "depot", git="..", git_interval_seconds=3600).insert({"k": 1})

        reopened = BloberiaDepot(repo / "depot", git="..")
        assert reopened.git is not None
        assert reopened.git.interval_seconds == 3600

    def test_a_git_path_that_is_not_a_string_is_refused(self, tmp_path: Path) -> None:
        depot = BloberiaDepot(tmp_path / "depot", git=17)  # type: ignore[arg-type]
        with pytest.raises(InvalidBloberiaInputError):
            _ = depot.git

    def test_an_untracked_depot_has_no_git_handler(self, tmp_path: Path) -> None:
        depot = BloberiaDepot(tmp_path / "depot")
        depot.insert({"k": 1})
        assert depot.git is None


class TestCheckpointing:
    def test_the_first_write_commits_because_nothing_is_committed_yet(
        self, tmp_path: Path
    ) -> None:
        repo = _repo(tmp_path / "project")
        BloberiaDepot(repo / "depot", git="..").insert({"k": 1})
        assert _log(repo) == ["chore(bloberia): checkpoint depot"]

    def test_writes_inside_the_interval_produce_one_commit(self, tmp_path: Path) -> None:
        """The interval is the point: a burst of writes is one checkpoint, not five."""
        repo = _repo(tmp_path / "project")
        depot = BloberiaDepot(repo / "depot", git="..", git_interval_seconds=3600)
        for n in range(5):
            depot.insert({"k": n})
        assert len(_log(repo)) == 1

    def test_a_write_after_the_interval_commits_again(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path / "project")
        depot = BloberiaDepot(repo / "depot", git="..", git_interval_seconds=0)
        depot.insert({"k": 1})
        time.sleep(1.1)
        depot.insert({"k": 2})
        assert len(_log(repo)) == 2

    def test_a_checkpoint_with_nothing_staged_makes_no_empty_commit(
        self, tmp_path: Path
    ) -> None:
        repo = _repo(tmp_path / "project")
        depot = BloberiaDepot(repo / "depot", git="..", git_interval_seconds=0)
        depot.insert({"k": 1})
        time.sleep(1.1)
        depot.delete({"nothing": {"exists": True}})
        assert len(_log(repo)) == 1


class TestFailureIsNeverTheWritersProblem:
    def test_a_configured_repo_that_does_not_exist_does_not_fail_the_write(
        self, tmp_path: Path
    ) -> None:
        depot = BloberiaDepot(tmp_path / "depot", git=str(tmp_path / "absent"))
        depot.insert({"k": 1})
        assert depot.count({"k": {"equals": 1}}) == 1

    def test_a_broken_git_invocation_does_not_fail_the_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _repo(tmp_path / "project")
        depot = BloberiaDepot(repo / "depot", git="..")

        def explode(*_args: object, **_kwargs: object) -> None:
            raise OSError("git is not on this machine")

        monkeypatch.setattr(subprocess, "run", explode)
        depot.insert({"k": 1})
        monkeypatch.undo()
        assert depot.count({"k": {"equals": 1}}) == 1

    def test_bloberia_never_creates_a_repository(self, tmp_path: Path) -> None:
        """A depot inside a project must never nest a second `.git/` under itself.

        Declining is the whole mechanism: there is no init path to get wrong, so a
        misconfigured depot stays untracked instead of detaching its own history.
        """
        depot_root = tmp_path / "project" / "depot"
        depot = BloberiaDepot(depot_root, git="..")
        depot.insert({"k": 1})
        assert not (depot_root / ".git").exists()
        assert not (depot_root.parent / ".git").exists()
        assert GitCheckpoint(repo=depot_root.parent).checkpoint(depot_root) is None
