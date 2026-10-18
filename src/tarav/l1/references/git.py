"""Shared, read-only Git reference mechanics."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import subprocess
from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from tarav.l0.kernel import TaravClass, entity
from tarav.l0.kernel import TaravObject, TypeShip
from tarav.l0.kernel.records import _json_object
from . import Reference


class GitFileLocator(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid")

    repository: str = Field(min_length=1)
    commit: str = Field(min_length=1)
    path: str = Field(min_length=1)


class GitOidCheck(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid")

    git_oid: str = Field(min_length=1)


class GitCommitMessagePositionLocator(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid")

    repository: str = Field(min_length=1)
    commit: str = Field(min_length=1)
    line: Annotated[int, Field(ge=1)]


class GitCommitMessagePositionCheck(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid")

    contains: str = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class GitCommitMessagePositionTarget:
    repository: Path
    commit: str
    line: int
    text: str


def git_bytes(repository: str | Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repository), *args], capture_output=True, check=False
    )
    if result.returncode:
        raise ValueError(result.stderr.decode(errors="replace").strip())
    return result.stdout


def git_text(repository: str | Path, *args: str) -> str:
    return git_bytes(repository, *args).decode().strip()


def git_commit_message(repository: str | Path, commit: str) -> tuple[str, str]:
    exact = git_text(
        repository,
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{commit}^{{commit}}",
    )
    raw = git_bytes(repository, "cat-file", "commit", exact)
    try:
        body = raw.split(b"\n\n", 1)[1].decode("utf-8")
    except (IndexError, UnicodeDecodeError) as exc:
        raise ValueError(f"Commit {exact} has no UTF-8 message body") from exc
    return exact, body.rstrip("\n")


def git_first_parent_ancestors(
    repository: str | Path,
    commit: str,
    *,
    limit: int = 5,
) -> tuple[str, ...]:
    output = git_text(
        repository,
        "rev-list",
        "--first-parent",
        f"--max-count={limit + 1}",
        commit,
    )
    return tuple(output.splitlines()[1:])


def git_file(repository: str | Path, commit: str, path: str) -> tuple[str, bytes]:
    relative = PurePosixPath(path)
    if not path or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Git path must be relative to the repository")
    exact = git_text(
        repository, "rev-parse", "--verify", "--end-of-options", f"{commit}^{{commit}}"
    )
    address = f"{exact}:{path}"
    oid = git_text(repository, "rev-parse", "--verify", "--end-of-options", address)
    return oid, git_bytes(repository, "cat-file", "blob", oid)


class GitFileReference(Reference):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('64b04e85-9899-4ab6-93a1-492d06e4509a'),
            name='Tarav.Reference.GitFile',
        )

    class RecordInterface(Reference.RecordInterface):
        locator: GitFileLocator
        check: GitOidCheck | None = None

    class Records(Reference.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return {
                "type": entity(cls).name,
                "locator": {
                    "repository": "/example/repository",
                    "commit": "0" * 40,
                    "path": "README.md",
                },
            }


    def __init__(
        self,
        record: Mapping | None = None,
        *,
        repository=None,
        commit=None,
        path=None,
        hints=None,
    ):
        if record is None:
            if (
                repository is None
                or not isinstance(commit, str)
                or not isinstance(path, str)
            ):
                raise ValueError("Git reference requires repository, commit and path")
            root = str(Path(repository).expanduser().absolute())
            exact = git_text(
                root,
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{commit}^{{commit}}",
            )
            oid, content = git_file(root, exact, path)
            observed = {
                "repository": root,
                "revision": commit,
                "commit": exact,
                "path": path,
                "size": len(content),
            }
            if hints is not None:
                observed.update(hints)
            record = {
                "type": entity(type(self)).name,
                "locator": {"repository": root, "commit": exact, "path": path},
                "check": {"git_oid": oid},
                "hints": observed,
            }
        elif any(value is not None for value in (repository, commit, path, hints)):
            raise ValueError("Loading retained data cannot override reference fields")
        super().__init__()
        self._fields = _json_object(record)

    def locate(self, locator):
        if not isinstance(locator, dict) or set(locator) != {
            "repository",
            "commit",
            "path",
        }:
            raise ValueError("Invalid Git file locator")
        oid, content = git_file(**locator)
        return {"git_oid": oid, "content": content}

    def check_target(self, target, check):
        if check is None:
            return True
        if not isinstance(check, dict) or set(check) != {"git_oid"}:
            raise ValueError("Git file check requires git_oid")
        return target["git_oid"] == check["git_oid"]


class GitCommitMessagePositionReference(Reference):
    """One exact line in one immutable Git commit message."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("7e025407-2d04-48ca-b5dd-fe4f021532dd"),
            name="Tarav.Reference.GitCommitMessagePosition",
        )

    class RecordInterface(Reference.RecordInterface):
        type: Literal["Tarav.Reference.GitCommitMessagePosition"]
        locator: GitCommitMessagePositionLocator
        check: GitCommitMessagePositionCheck | None = None

    class Records(Reference.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return {
                "type": entity(cls).name,
                "locator": {
                    "repository": "/example/repository",
                    "commit": "0" * 40,
                    "line": 1,
                },
            }


    def __init__(
        self,
        record: Mapping | None = None,
        *,
        repository=None,
        commit=None,
        line=None,
        hints=None,
    ):
        if record is None:
            if repository is None or not isinstance(commit, str) or not isinstance(line, int):
                raise ValueError(
                    "Git commit-message position requires repository, commit and line"
                )
            root = str(Path(repository).expanduser().absolute())
            exact, message = git_commit_message(root, commit)
            lines = message.splitlines()
            if line < 1 or line > len(lines):
                raise ValueError(f"Commit-message line {line} is outside {exact}")
            observed = {
                "revision": commit,
                "parents": list(git_first_parent_ancestors(root, exact, limit=1)),
                "recent_first_parent_ancestors": list(
                    git_first_parent_ancestors(root, exact)
                ),
            }
            if hints is not None:
                observed.update(hints)
            record = {
                "type": entity(type(self)).name,
                "locator": {
                    "repository": root,
                    "commit": exact,
                    "line": line,
                },
                "hints": observed,
            }
        elif any(value is not None for value in (repository, commit, line, hints)):
            raise ValueError("Loading retained data cannot override reference fields")
        super().__init__()
        self._fields = _json_object(record)

    def locate(self, locator):
        if not isinstance(locator, Mapping) or set(locator) != {
            "repository",
            "commit",
            "line",
        }:
            raise ValueError("Invalid Git commit-message position locator")
        repository = locator["repository"]
        commit = locator["commit"]
        line = locator["line"]
        if not isinstance(repository, str) or not isinstance(commit, str):
            raise ValueError("Git commit-message locator requires string addresses")
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            raise ValueError("Git commit-message line must be a positive integer")
        root = Path(repository).expanduser().resolve()
        exact, message = git_commit_message(root, commit)
        lines = message.splitlines()
        if line > len(lines):
            raise ValueError(f"Commit-message line {line} is outside {exact}")
        return GitCommitMessagePositionTarget(root, exact, line, lines[line - 1])

    def check_target(self, target, check):
        if not isinstance(target, GitCommitMessagePositionTarget):
            raise TypeError("Git commit-message target has an invalid runtime shape")
        if check is None:
            return True
        if not isinstance(check, Mapping) or set(check) != {"contains"}:
            raise ValueError("Git commit-message check requires exactly 'contains'")
        contains = check["contains"]
        if not isinstance(contains, str) or not contains:
            raise ValueError("Git commit-message contains check must be nonempty")
        return contains in target.text


__all__ = [
    "GitCommitMessagePositionCheck",
    "GitCommitMessagePositionLocator",
    "GitCommitMessagePositionReference",
    "GitCommitMessagePositionTarget",
    "GitFileLocator",
    "GitFileReference",
    "GitOidCheck",
    "git_commit_message",
    "git_file",
]
