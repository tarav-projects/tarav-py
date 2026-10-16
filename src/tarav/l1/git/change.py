"""tarav-change: an ID every commit carries, so a reference survives history rewrites.

A commit hash names exact bytes and changes when history is rewritten. The
tarav-change handler gives each commit a random ID written twice: as the
trailer `tarav-change: <id>` and as a line appended to the tracked file
`.tarav/changes`. Rewrites keep both the message and the file, so the ID
still finds the commit: `find` lists the commits that gained it.

An amended commit gains a new ID and keeps the line of the one it replaces,
so both IDs find it. Cherry-pick and rebase copy the ID with the content; an
ID in several commits finds them all.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from tarav.l0._core.git_repository import git_result, run_git
from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import Check, CheckPOI, CheckResult

from .hooks import GitHookCall, GitHookHandler
from .workflow import GIT_WORKFLOW_SHIP

CHANGES_FILE = ".tarav/changes"
TRAILER = "tarav-change"
CHECKED_COMMITS = 200
_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _git_path(root: Path, name: str) -> Path:
    """A file in the repository's Git folder, kept with this clone only."""
    relative = run_git(root, "rev-parse", "--git-path", name).stdout.decode().strip()
    return (root / relative).resolve()


def _own_index() -> dict[str, str]:
    """The environment that reaches the repository's own index, not the one being committed."""
    return {key: value for key, value in os.environ.items() if key != "GIT_INDEX_FILE"}


# tarav.breadcrumb efca261f7a0e27f57fc4fb2cde52b901369ef3fd7c573b1a7bcaedd7fc0855d3
# tarav.breadcrumb 329f9ebba15c1612d87d4caa8c439881711069b7c076554b672da23d872124b7
class TaravChange(GitHookHandler):
    """Writes a new ID into each commit, in its trailer and in `.tarav/changes`."""

    name = "tarav-change"
    hooks = frozenset({"pre-commit", "commit-msg", "post-commit", "post-rewrite"})
    attributes = (f"{CHANGES_FILE} merge=union",)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8f3a6d21-4c97-4e05-b1a8-d6e2f0c35b79"),
                          name="Tarav.Git.Change", workflow=GIT_WORKFLOW_SHIP)

    def run(self, call: GitHookCall) -> None:
        {"pre-commit": self._pre_commit, "commit-msg": self._commit_msg,
         "post-commit": self._post_commit, "post-rewrite": self._post_rewrite}[call.hook](call)

    def _pre_commit(self, call: GitHookCall) -> None:
        # Only pre-commit can still stage; Git passes the index being committed as GIT_INDEX_FILE.
        change = str(uuid.uuid4())
        path = call.root / CHANGES_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(change + "\n")
        run_git(call.root, "add", "--", CHANGES_FILE)
        _git_path(call.root, "tarav/change").parent.mkdir(parents=True, exist_ok=True)
        _git_path(call.root, "tarav/change").write_text(change, encoding="utf-8")

    def _commit_msg(self, call: GitHookCall) -> None:
        pending = _git_path(call.root, "tarav/change")
        if not pending.exists():
            raise RuntimeError("pre-commit wrote no tarav-change for this commit")
        change = pending.read_text(encoding="utf-8").strip()
        run_git(call.root, "interpret-trailers", "--in-place", "--trailer",
                f"{TRAILER}: {change}", str(call.root / call.arguments[0]))
        pending.unlink()

    def _post_commit(self, call: GitHookCall) -> None:
        # `git commit <paths>` and temporary-index commits leave the repository's own index
        # with the old file; realign it when the worktree already holds what HEAD holds.
        # Compare contents directly: `git diff HEAD` relies on that same index.
        environment = _own_index()
        held = git_result(call.root, "show", f"HEAD:{CHANGES_FILE}", environment=environment)
        path = call.root / CHANGES_FILE
        if held.returncode == 0 and path.is_file() and path.read_bytes() == held.stdout:
            run_git(call.root, "reset", "-q", "--", CHANGES_FILE, environment=environment)

    def _post_rewrite(self, call: GitHookCall) -> None:
        at = datetime.now(timezone.utc).isoformat()
        lines = []
        for line in call.stdin.splitlines():
            old, new, *_ = line.split()
            lines.append(json.dumps({"command": call.arguments[0], "old": old, "new": new, "at": at}))
        if lines:
            log = _git_path(call.root, "tarav/rewrites.jsonl")
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")

    def check(self, project) -> Check:
        return TaravChangeCheck(project)


# tarav.breadcrumb 598b3bc14abe93125131b71d14e1fc61de685f3e4ce53092f321a68a3e256d5d
def find(root: Path | str, change: str) -> tuple[str, ...]:
    """The commits on any branch that gained ``change``, in its file or its trailer, oldest first."""
    if _ID.fullmatch(change) is None:
        raise ValueError(f"A tarav-change is a lowercase UUID, not {change!r}")
    root = Path(root)
    touched = run_git(root, "log", "--all", "--format=%H", f"-S{change}", "--",
                      CHANGES_FILE).stdout.decode().split()
    gained = [commit for commit in touched
              if change in run_git(root, "show", f"{commit}:{CHANGES_FILE}").stdout.decode()]
    trailed = run_git(root, "log", "--all", "--format=%H", "--fixed-strings",
                      f"--grep={TRAILER}: {change}").stdout.decode().split()
    commits = list(dict.fromkeys([*gained, *trailed]))
    if not commits:
        return ()
    ordered = run_git(root, "log", "--no-walk=sorted", "--reverse", "--format=%H", *commits)
    return tuple(ordered.stdout.decode().split())


class TaravChangeMissing(CheckPOI):
    """A commit carries no tarav-change: no trailer, and no line added to the file."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b6d2e8f4-1a73-4c59-8e06-3f9b7a2d1c45"),
                          name="Tarav.Git.Change.Missing", workflow=GIT_WORKFLOW_SHIP)


# tarav.breadcrumb 7d2b4065a2e05297316bf9a0f21bb7960eebcdc7c37efecffe3a32b9389072ae
class TaravChangeCheck(Check):
    """Reports recent commits made after `.tarav/changes` began that carry no tarav-change."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("4a9c1e73-d8b2-4f60-a5e9-0c6d3b8f2e17"),
                          name="Tarav.Git.Change.Check", workflow=GIT_WORKFLOW_SHIP)

    def __init__(self, project) -> None:
        super().__init__()
        self.project = project

    def _run(self) -> CheckResult:
        root = self.project.root
        began = run_git(root, "log", "--reverse", "--format=%H", "--diff-filter=A", "--",
                        CHANGES_FILE).stdout.decode().split()
        if not began:
            return CheckResult(self, status="completed", pois=[])
        span = f"{began[0]}..HEAD"
        commits = run_git(root, "log", "--no-merges", f"--max-count={CHECKED_COMMITS}",
                          "--format=%H%x00%s%x00%(trailers:key=tarav-change,valueonly,separator=%x2C)",
                          span).stdout.decode().splitlines()
        with_line = set(run_git(root, "log", "--format=%H", span, "--",
                                CHANGES_FILE).stdout.decode().split())
        pois = []
        for line in commits:
            commit, subject, trailer = line.split("\0")
            if trailer.strip() or commit in with_line:
                continue
            pois.append(TaravChangeMissing(
                self, f"Commit {commit[:7]} carries no tarav-change: {subject}",
                situation={"project": str(root), "commit": commit}))
        return CheckResult(self, status="completed", pois=pois)


GIT_CHANGE_RECORD_TYPES = (TaravChangeMissing,)

__all__ = ["CHANGES_FILE", "GIT_CHANGE_RECORD_TYPES", "TRAILER", "TaravChange", "TaravChangeCheck",
           "TaravChangeMissing", "find"]
