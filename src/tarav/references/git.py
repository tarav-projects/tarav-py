"""Shared, read-only Git reference mechanics."""

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
import subprocess

from pydantic import ConfigDict, Field

from tarav.harness import TaravObject, TypeShip
from . import Reference


class GitFileLocator(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid")

    repository: str = Field(min_length=1)
    commit: str = Field(min_length=1)
    path: str = Field(min_length=1)


class GitOidCheck(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid")

    git_oid: str = Field(min_length=1)


def git_bytes(repository: str | Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repository), *args], capture_output=True, check=False
    )
    if result.returncode:
        raise ValueError(result.stderr.decode(errors="replace").strip())
    return result.stdout


def git_text(repository: str | Path, *args: str) -> str:
    return git_bytes(repository, *args).decode().strip()


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
    type_name = "Tarav.Reference.GitFile"
    type_ship = TypeShip("64b04e85-9899-4ab6-93a1-492d06e4509a")

    class RecordInterface(Reference.RecordInterface):
        locator: GitFileLocator
        check: GitOidCheck | None = None

    @classmethod
    def json_example(cls) -> dict[str, object]:
        return {
            "type": cls.type_name,
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
                "type": self.type_name,
                "locator": {"repository": root, "commit": exact, "path": path},
                "check": {"git_oid": oid},
                "hints": observed,
            }
        elif any(value is not None for value in (repository, commit, path, hints)):
            raise ValueError("Loading retained data cannot override reference fields")
        super().__init__(record)

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
