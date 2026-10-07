"""Bounded Git repository operations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ConfigDict, Field

from tarav.l0._core.git_repository import (
    GitError,
    commit_paths,
    initialize_repository,
    run_git as _run_git,
)
# tarav.breadcrumb 748e430a920a826d8c69df0ccf0cd18353e8665d899ec7b1bbea01cf3b5f4c61
from tarav.l0.kernel import TaravClass, TaravObject, TypeShip, entity

from .workflow import GIT_WORKFLOW_SHIP


@dataclass(frozen=True)
class GitWorktree:
    path: Path
    commit: str
    branch: str | None


class GitObject(TaravObject):
    """Base Type for objects owned by the Git workflow."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("2e2ba747-d55e-416f-bc30-c9bb40c3d881"),
            name="Tarav.Git.Object",
            workflow=GIT_WORKFLOW_SHIP,
        )


class GitRepository(GitObject):
    """One discovered repository and its explicit operations."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("2d7c1638-630d-4853-8b32-2490810f1832"),
            name="Tarav.Git.Repository",
            workflow=GIT_WORKFLOW_SHIP,
        )

    class RecordInterface(GitObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal["Tarav.Git.Repository"]
        root: str = Field(min_length=1)

    def __init__(self, root: str | Path) -> None:
        super().__init__()
        selected = Path(root).expanduser().resolve()
        discovered = git_text(selected, "rev-parse", "--show-toplevel")
        self.root = Path(discovered).resolve()
        self._record = {"type": entity(type(self)).name, "root": str(self.root)}

    @classmethod
    def initialize(cls, root: str | Path) -> GitRepository:
        """Initialize an explicitly selected repository and open it."""
        return cls(initialize_repository(root))

    @classmethod
    def _from_record(cls, record_data):
        result = super()._from_record(record_data)
        result.root = Path(record_data.root).expanduser().resolve()
        return result

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {"type": entity(cls).name, "root": "/example/repository"}

    def exact_commit(self, revision: str) -> str:
        return git_text(
            self.root,
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{revision}^{{commit}}",
        )

    def commit_message(self, revision: str) -> tuple[str, str]:
        exact = self.exact_commit(revision)
        raw = git_bytes(self.root, "cat-file", "commit", exact)
        try:
            body = raw.split(b"\n\n", 1)[1].decode("utf-8")
        except (IndexError, UnicodeDecodeError) as exc:
            raise GitError(f"Commit {exact} has no UTF-8 message body") from exc
        return exact, body.rstrip("\n")

    def first_parent_ancestors(self, revision: str, *, limit: int = 5) -> tuple[str, ...]:
        exact = self.exact_commit(revision)
        output = git_text(
            self.root,
            "rev-list",
            "--first-parent",
            f"--max-count={limit + 1}",
            exact,
        )
        return tuple(output.splitlines()[1:])

    # tarav.breadcrumb b564516ed6ef50cde4a78994d64ef119985a150dfa5fa294382bea1ad588cc49
    def worktrees(self) -> tuple[GitWorktree, ...]:
        """Ask Git for its registered worktrees, including missing paths."""
        raw = git_bytes(self.root, "worktree", "list", "--porcelain", "-z")
        result = []
        for item in raw.split(b"\0\0"):
            fields = dict(
                line.split(b" ", 1) if b" " in line else (line, b"")
                for line in item.strip(b"\0").split(b"\0") if line
            )
            if b"worktree" not in fields:
                continue
            result.append(GitWorktree(
                path=Path(fields[b"worktree"].decode()).resolve(),
                commit=fields[b"HEAD"].decode(),
                branch=(fields[b"branch"].decode().removeprefix("refs/heads/")
                        if b"branch" in fields else None),
            ))
        return tuple(result)

    def add_worktree(self, path: Path | str, *, commit: str, branch: str) -> GitWorktree:
        """Create one branch-backed worktree from an exact base commit."""
        base = self.exact_commit(commit)
        _run_git(self.root, "check-ref-format", "--branch", branch)
        target = Path(path).expanduser().resolve()
        _run_git(self.root, "worktree", "add", "-b", branch, str(target), base)
        return next(item for item in self.worktrees() if item.path == target)

    def attach_worktree(self, path: Path | str, *, branch: str) -> GitWorktree:
        """Reattach an existing branch after its prior worktree was removed."""
        target = Path(path).expanduser().resolve()
        _run_git(self.root, "worktree", "add", str(target), branch)
        return next(item for item in self.worktrees() if item.path == target)

    def remove_worktree(self, path: Path | str) -> None:
        """Remove through Git; dirty worktrees are refused by Git."""
        _run_git(self.root, "worktree", "remove", str(Path(path).expanduser().resolve()))

    def prune_worktrees(self) -> None:
        _run_git(self.root, "worktree", "prune")

    def commit(
        self,
        paths: Sequence[str],
        message: str,
        *,
        allow_empty: bool = False,
    ) -> str:
        """Commit exactly ``paths`` while retaining unrelated staged changes."""

        return commit_paths(self.root, paths, message, allow_empty=allow_empty)


GIT_RECORD_TYPES = (GitObject, GitRepository)


def git_bytes(repository: str | Path, *args: str) -> bytes:
    return _run_git(repository, *args).stdout


def git_text(repository: str | Path, *args: str) -> str:
    return git_bytes(repository, *args).decode("utf-8").strip()


__all__ = [
    "GIT_RECORD_TYPES",
    "GitError",
    "GitObject",
    "GitRepository",
    "GitWorktree",
    "git_bytes",
    "git_text",
]
