"""tarav.unsorted.io: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

from tarav.unsorted.primitives import DiagramError
from tarav.unsorted.primitives import _object
import json
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from tarav.unsorted.constants import JsonObject
    from pathlib import Path

def _read_json(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DiagramError(f"cannot read Diagram JSON {path}: {exc}") from exc
    return _object(value, field=str(path))


def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repo), *args), capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise DiagramError(
            f"Git failed for {repo}: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def _commit_paths(repo: Path, paths: Iterable[Path], *, message: str) -> None:
    values = tuple(path.as_posix() for path in paths)
    _run_git(repo, "add", "--", *values)
    _run_git(
        repo,
        "-c",
        "user.name=Tarav Diagram",
        "-c",
        "user.email=diagram@tarav.invalid",
        "commit",
        "-q",
        "--only",
        "-m",
        message,
        "--",
        *values,
    )
