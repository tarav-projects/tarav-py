"""tarav-change: an ID every commit carries, so a reference survives history rewrites.

A commit hash names exact bytes and changes when history is rewritten. The
tarav-change handler gives each commit a random ID written twice: as the
trailer `tarav-change: <id>` and as a line appended to the tracked file
`.tarav/changes`. Rewrites keep both the message and the file, so the ID
still finds the commit: `find` lists the commits that gained it.

An amended commit gains a new ID and keeps the line of the one it replaces,
so both IDs find it. Cherry-pick and rebase copy the ID with the content; an
ID in several commits finds them all.

The file is append-only. A witness outside the repository remembers the IDs
each branch had at its last commit; a commit whose file lost some is stopped
until restored or overruled, and stops and overrules become actions of the
Project.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from tarav.l0._core.git_repository import git_result, run_git
from tarav.l0.kernel import Ship, TaravClass, TypeShip
from tarav.l0.project import load_project_marker, project_marker_name
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite

from .hooks import OVERRULE_ENV_VAR, GitHookCall, GitHookHandler, GitHookRefusal
from .witness import ChangeOverrule, ChangeWitness, ChangeWitnesses
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ids(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _held(root: Path) -> list[str]:
    """The IDs in HEAD's `.tarav/changes`; none when HEAD has no such file."""
    shown = git_result(root, "show", f"HEAD:{CHANGES_FILE}", environment=_own_index())
    return _ids(shown.stdout.decode()) if shown.returncode == 0 else []


def _witnessed(root: Path) -> tuple[str, str] | None:
    """The Project and branch the witness keys this repository by; None when it cannot."""
    marker = root / ".tarav" / "project.json"
    project = json.loads(marker.read_text(encoding="utf-8")).get("project_id") if marker.is_file() else None
    branch = git_result(root, "symbolic-ref", "--short", "-q", "HEAD")
    if not project or branch.returncode != 0:
        return None
    return str(project), branch.stdout.decode().strip()


def _missing(witness: ChangeWitness | None, present: list[str]) -> list[str]:
    kept = set(present)
    return [change for change in witness.changes if change not in kept] if witness else []


# tarav.breadcrumb efca261f7a0e
# tarav.breadcrumb 329f9ebba15c
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
        path = call.root / CHANGES_FILE
        self._compare(call, _ids(path.read_text(encoding="utf-8")) if path.exists() else [])
        # Only pre-commit can still stage; Git passes the index being committed as GIT_INDEX_FILE.
        change = str(uuid.uuid4())
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(change + "\n")
        run_git(call.root, "add", "--", CHANGES_FILE)
        _git_path(call.root, "tarav/change").parent.mkdir(parents=True, exist_ok=True)
        _git_path(call.root, "tarav/change").write_text(change, encoding="utf-8")

    # tarav.breadcrumb e2716a515871
    # tarav.breadcrumb 4cb67df5d920
    def _compare(self, call: GitHookCall, present: list[str]) -> None:
        """Stop the commit when IDs the witness holds are gone, unless overruled."""
        key = _witnessed(call.root)
        pending = _git_path(call.root, "tarav/overrule")
        missing = _missing(ChangeWitnesses().get(*key), present) if key else []
        if not missing:
            pending.unlink(missing_ok=True)  # left by a commit that did not happen
            return
        if call.overrules(self.name):
            pending.parent.mkdir(parents=True, exist_ok=True)
            pending.write_text(json.dumps({"missing": missing}), encoding="utf-8")
            return
        note = ""
        try:
            _hand_to_project(call.root, lambda check: _removed(check, key[1], missing))
        except Exception as exc:  # the stop must not depend on the action registry
            note = f" The Project action could not be registered: {exc}."
        shown = ", ".join(missing[:3]) + (", ..." if len(missing) > 3 else "")
        raise GitHookRefusal(
            f"{len(missing)} tarav-change IDs that {key[1]} had at its last commit are gone from "
            f"{CHANGES_FILE} ({shown}); history may have been rewritten. Restore those lines, or "
            f"commit again with {OVERRULE_ENV_VAR}={self.name}; the overrule is recorded as an "
            f"action of the Project.{note}")

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
        self._witness(call)

    def _witness(self, call: GitHookCall) -> None:
        """Record an overrule, then let the witness take HEAD's IDs, unless some vanished unseen."""
        key = _witnessed(call.root)
        if key is None:
            return
        witnesses = ChangeWitnesses()
        held = _held(call.root)
        missing = _missing(witnesses.get(*key), held)
        pending = _git_path(call.root, "tarav/overrule")
        if pending.exists():
            commit = run_git(call.root, "rev-parse", "HEAD").stdout.decode().strip()
            overrule = ChangeOverrule(Ship(str(uuid.uuid4())), project=key[0], branch=key[1],
                                      commit=commit, at=_now(),
                                      missing=json.loads(pending.read_text(encoding="utf-8"))["missing"])
            witnesses.add_overrule(overrule)
            pending.unlink()
            _hand_to_project(call.root, lambda check: _overruled(check, overrule))
            missing = []
        if missing:
            return  # a commit that skipped pre-commit; the witness keeps reporting the loss
        witnesses.put(ChangeWitness(project=key[0], branch=key[1], changes=held, at=_now()))

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
        return TaravChangeCheck(project.root)


# tarav.breadcrumb 598b3bc14abe
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


# tarav.breadcrumb 7d2b4065a2e0
class TaravChangeRemoved(CheckPOI):
    """IDs the witness holds for a branch are gone from its `.tarav/changes`."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e2c9a5f1-7b38-4d06-9f4a-1d8b6e3c0a72"),
                          name="Tarav.Git.Change.Removed", workflow=GIT_WORKFLOW_SHIP)


class TaravChangeOverruled(CheckPOI):
    """A commit went through without IDs the witness held, by overrule."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("71f4d0b8-2e96-4c5a-b3d7-8a0e5c1f9b26"),
                          name="Tarav.Git.Change.Overruled", workflow=GIT_WORKFLOW_SHIP)


def _removed(check: Check, branch: str, missing: list[str]) -> TaravChangeRemoved:
    return TaravChangeRemoved(
        check, f"{len(missing)} tarav-change IDs that {branch} had at its last commit are gone "
        f"from {CHANGES_FILE}", situation={"project": str(check.root), "branch": branch},
        details={"missing": missing})


def _overruled(check: Check, overrule: ChangeOverrule) -> TaravChangeOverruled:
    return TaravChangeOverruled(
        check, f"Commit {overrule.commit[:7]} on {overrule.branch} went through without "
        f"{len(overrule.missing)} tarav-change IDs, by overrule",
        situation={"project": str(check.root), "branch": overrule.branch,
                   "commit": overrule.commit}, details={"missing": overrule.missing})


# tarav.breadcrumb 6d5eab772e44
def _hand_to_project(root: Path, build) -> None:
    """Register the action of one POI on the Project at ``root``, raised by the check Type
    that raises it in the Project's checks, so its status reconciles it.

    The Project is read from its marker: Git does not import the Project Type,
    which imports the Git hooks for its checks.
    """
    from tarav.l1.actions.project import ProjectActions

    marker = load_project_marker(root / ".tarav" / "project.json")
    project = {"id": marker["project_id"], "name": project_marker_name(marker) or root.name,
               "root": root}
    check = TaravChangeCheck(root)
    suite = CheckSuite([CheckResult(check, status="completed", pois=[build(check)])],
                       name="tarav-change hook").run()
    ProjectActions(project).register(suite)


class TaravChangeCheck(Check):
    """Reports commits without a tarav-change, IDs the witness saw vanish, and overrules."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("4a9c1e73-d8b2-4f60-a5e9-0c6d3b8f2e17"),
                          name="Tarav.Git.Change.Check", workflow=GIT_WORKFLOW_SHIP)

    def __init__(self, root: Path | str) -> None:
        super().__init__()
        self.root = Path(root).resolve()

    def _run(self) -> CheckResult:
        root = self.root
        pois: list[CheckPOI] = []
        key = _witnessed(root)
        if key is not None:
            witnesses = ChangeWitnesses()
            missing = _missing(witnesses.get(*key), _held(root))
            if missing:
                pois.append(_removed(self, key[1], missing))
            pois += [_overruled(self, overrule) for overrule in witnesses.overrules(key[0])]
        began = run_git(root, "log", "--reverse", "--format=%H", "--diff-filter=A", "--",
                        CHANGES_FILE).stdout.decode().split()
        if began:
            pois += self._without_change(root, f"{began[0]}..HEAD")
        return CheckResult(self, status="completed", pois=pois)

    def _without_change(self, root: Path, span: str) -> list[CheckPOI]:
        commits = run_git(root, "log", "--no-merges", f"--max-count={CHECKED_COMMITS}",
                          "--format=%H%x00%s%x00%(trailers:key=tarav-change,valueonly,separator=%x2C)",
                          span).stdout.decode().splitlines()
        with_line = set(run_git(root, "log", "--format=%H", span, "--",
                                CHANGES_FILE).stdout.decode().split())
        pois: list[CheckPOI] = []
        for line in commits:
            commit, subject, trailer = line.split("\0")
            if trailer.strip() or commit in with_line:
                continue
            pois.append(TaravChangeMissing(
                self, f"Commit {commit[:7]} carries no tarav-change: {subject}",
                situation={"project": str(root), "commit": commit}))
        return pois


GIT_CHANGE_RECORD_TYPES = (TaravChangeMissing, TaravChangeRemoved, TaravChangeOverruled)

__all__ = ["CHANGES_FILE", "GIT_CHANGE_RECORD_TYPES", "TRAILER", "TaravChange", "TaravChangeCheck",
           "TaravChangeMissing", "TaravChangeOverruled", "TaravChangeRemoved", "find"]
