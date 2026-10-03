"""Bounded Git repository operations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
from typing import Literal

from pydantic import ConfigDict, Field

from tarav.l0.kernel import TaravClass, TaravObject, TypeShip, entity

from .workflow import GIT_WORKFLOW_SHIP


class GitError(ValueError):
    """A requested Git operation could not be completed."""


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

        selected = tuple(_repository_path(path) for path in paths)
        if len(selected) != len(set(selected)):
            raise GitError("Commit paths must be unique")
        if not selected and not allow_empty:
            raise GitError("A nonempty commit requires at least one selected path")
        if not isinstance(message, str) or not message.strip():
            raise GitError("Commit message must be nonempty")

        with tempfile.TemporaryDirectory(prefix="tarav-git-") as temporary:
            index = Path(temporary) / "index"
            message_path = Path(temporary) / "message.txt"
            message_path.write_text(message.rstrip("\n") + "\n", encoding="utf-8")
            environment = {**os.environ, "GIT_INDEX_FILE": str(index)}
            head_exists = _git_result(
                self.root,
                "rev-parse",
                "--verify",
                "--quiet",
                "HEAD",
                environment=environment,
            ).returncode == 0
            if head_exists:
                _run_git(self.root, "read-tree", "HEAD", environment=environment)
            else:
                _run_git(self.root, "read-tree", "--empty", environment=environment)
            if selected:
                _run_git(
                    self.root,
                    "add",
                    "-A",
                    "--",
                    *(_literal_pathspec(path) for path in selected),
                    environment=environment,
                )
            changed = (
                _git_result(
                    self.root,
                    "diff",
                    "--cached",
                    "--quiet",
                    environment=environment,
                ).returncode
                != 0
            )
            if not changed and not allow_empty:
                raise GitError("Selected paths contain no changes")
            arguments = [
                "commit",
                "--cleanup=verbatim",
                "--file",
                str(message_path),
            ]
            if allow_empty:
                arguments.append("--allow-empty")
            _run_git(self.root, *arguments, environment=environment)

        exact, retained_message = self.commit_message("HEAD")
        if retained_message != message.rstrip("\n"):
            raise GitError(f"Commit {exact} did not retain the prepared message exactly")
        if selected:
            _run_git(
                self.root,
                "reset",
                "-q",
                "HEAD",
                "--",
                *(_literal_pathspec(path) for path in selected),
            )
        return exact


GIT_RECORD_TYPES = (GitObject, GitRepository)


def git_bytes(repository: str | Path, *args: str) -> bytes:
    return _run_git(repository, *args).stdout


def git_text(repository: str | Path, *args: str) -> str:
    return git_bytes(repository, *args).decode("utf-8").strip()


def _git_result(
    repository: str | Path,
    *args: str,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repository), *args],
        env=dict(environment) if environment is not None else None,
        capture_output=True,
        check=False,
    )


def _run_git(
    repository: str | Path,
    *args: str,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    result = _git_result(repository, *args, environment=environment)
    if result.returncode:
        message = result.stderr.decode(errors="replace").strip()
        raise GitError(message or f"Git command failed: {' '.join(args)}")
    return result


def _repository_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise GitError("Commit paths must be nonempty repository-relative strings")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or ".git" in path.parts:
        raise GitError(f"Unsafe repository path: {value}")
    normalized = path.as_posix()
    if normalized in {"", "."}:
        raise GitError(f"Unsafe repository path: {value}")
    return normalized


def _literal_pathspec(path: str) -> str:
    return f":(top,literal){path}"


__all__ = [
    "GIT_RECORD_TYPES",
    "GitError",
    "GitObject",
    "GitRepository",
    "GitWorktree",
    "git_bytes",
    "git_text",
]
