from __future__ import annotations

import subprocess
from pathlib import Path

from agentos._core.errors import CliError


def run_git(repo_dir: Path, *git_args: str) -> str:
    result = subprocess.run(
        ["git", *git_args],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise CliError(details)
    return result.stdout.strip()


def resolve_repo_root(repo_hint: str) -> Path:
    hint_path = Path(repo_hint).expanduser().resolve()
    if hint_path.is_file():
        hint_path = hint_path.parent
    if not hint_path.exists():
        raise CliError(f"repo path does not exist: {hint_path}")
    try:
        root = run_git(hint_path, "rev-parse", "--show-toplevel")
    except CliError as exc:
        raise CliError(f"not a git repository: {hint_path} ({exc})") from exc
    return Path(root).resolve()


def resolve_repo_file(repo_root: Path, file_path: str) -> Path:
    raw_path = Path(file_path).expanduser()
    resolved = raw_path.resolve() if raw_path.is_absolute() else (repo_root / raw_path).resolve()
    if not resolved.exists():
        raise CliError(f"file does not exist: {resolved}")
    if not resolved.is_file():
        raise CliError(f"path is not a file: {resolved}")
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise CliError(f"file is outside repository root: {resolved}") from exc
    return resolved


def resolve_repo_relative_path(repo_root: Path, file_path: str) -> str:
    raw_path = Path(file_path).expanduser()
    resolved = raw_path.resolve() if raw_path.is_absolute() else (repo_root / raw_path).resolve()
    try:
        relative_path = resolved.relative_to(repo_root)
    except ValueError as exc:
        raise CliError(f"file is outside repository root: {resolved}") from exc
    return relative_path.as_posix()
