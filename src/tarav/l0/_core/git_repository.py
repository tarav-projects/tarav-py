"""Workflow-neutral Git repository mutations, and the state of a repository."""
# tarav.breadcrumb 0ac8bc920804

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import os
import re
from pathlib import Path, PurePosixPath
import subprocess
import tempfile


class GitError(ValueError):
    """A requested Git operation could not be completed."""


def git_result(
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


def run_git(
    repository: str | Path,
    *args: str,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    result = git_result(repository, *args, environment=environment)
    if result.returncode:
        message = result.stderr.decode(errors="replace").strip()
        raise GitError(message or f"Git command failed: {' '.join(args)}")
    return result


# tarav.breadcrumb 4779a9beedc5
def repository_states(folders: Iterable[str | Path]) -> dict[str, dict[str, object]]:
    """The state of the repository each folder is in, keyed by repository root.

    A state is HEAD and whether the working tree has no change; untracked
    files are changes. A folder outside any repository, or in one without a
    commit, has none.
    """
    states: dict[str, dict[str, object]] = {}
    for folder in folders:
        try:
            root = str(Path(run_git(Path(folder).expanduser(), "rev-parse", "--show-toplevel")
                            .stdout.decode().strip()).resolve())
            if root not in states:
                commit = run_git(root, "rev-parse", "--verify", "HEAD^{commit}").stdout.decode().strip()
                status = run_git(root, "status", "--porcelain").stdout
                states[root] = {"commit": commit, "clean": not status.strip()}
        except (GitError, OSError):
            continue
    return states


def initialize_repository(root: str | Path) -> Path:
    selected = Path(root).expanduser().resolve()
    selected.mkdir(parents=True, exist_ok=True)
    run_git(selected, "init", "--quiet")
    return selected


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


# Trailer lines a commit-msg hook may append, such as `tarav-change: <id>`.
_HOOK_TRAILERS = re.compile(r"\n\n?(?:[A-Za-z0-9][A-Za-z0-9-]*: [^\n]*\n?)+")


def commit_paths(
    root: str | Path,
    paths: Sequence[str],
    message: str,
    *,
    allow_empty: bool = False,
) -> str:
    """Commit selected working-tree paths while retaining unrelated staged changes."""
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
        head_exists = git_result(
            root, "rev-parse", "--verify", "--quiet", "HEAD", environment=environment,
        ).returncode == 0
        run_git(root, "read-tree", "HEAD" if head_exists else "--empty", environment=environment)
        if selected:
            run_git(
                root, "add", "-A", "--",
                *(_literal_pathspec(path) for path in selected),
                environment=environment,
            )
        changed = git_result(root, "diff", "--cached", "--quiet", environment=environment).returncode != 0
        if not changed and not allow_empty:
            raise GitError("Selected paths contain no changes")
        arguments = ["commit", "--cleanup=verbatim", "--file", str(message_path)]
        if allow_empty:
            arguments.append("--allow-empty")
        run_git(root, *arguments, environment=environment)

    exact = run_git(root, "rev-parse", "HEAD").stdout.decode("utf-8").strip()
    raw = run_git(root, "cat-file", "commit", exact).stdout
    try:
        retained_message = raw.split(b"\n\n", 1)[1].decode("utf-8").rstrip("\n")
    except (IndexError, UnicodeDecodeError) as exc:
        raise GitError(f"Commit {exact} has no UTF-8 message body") from exc
    prepared = message.rstrip("\n")
    added = retained_message[len(prepared):] if retained_message.startswith(prepared) else None
    if added is None or (added and _HOOK_TRAILERS.fullmatch(added) is None):
        raise GitError(f"Commit {exact} did not retain the prepared message, "
                       "apart from trailers its hooks added")
    if selected:
        run_git(root, "reset", "-q", "HEAD", "--", *(_literal_pathspec(path) for path in selected))
    return exact
