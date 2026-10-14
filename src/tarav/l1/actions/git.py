"""The Git log of an action: the state of its checks' repositories when it changes.

The suites above an action's checks declare the repositories those checks
read, and each run records their state: HEAD, and whether the working tree
was clean. An action logs that state at every status change (opened, closed
by any exit, reopened), and, for each repository, the first clean state seen
after that change. Git keeps everything else: what changed between two
logged commits is a `git diff`. The log is good to have; no exit depends on
it.
"""

from __future__ import annotations

from copy import deepcopy

from tarav.l0._core.git_repository import repository_states

# tarav.breadcrumb e3f0712275963a28cdab25d977599faffc3e4b4d001935c782237979c97d29c0
# tarav.breadcrumb e38d2674669e9b91e4cd7f564ebceb0857d10de1f8fe6871606d543c23493c2d
OPENED, REOPENED, CLOSED, CLEAN = "opened", "reopened", "closed", "clean"


def log_status(run, event: str, states: dict | None, *, at: str,
               exit: str | None = None) -> bool:
    """Log a status change with the state of every repository; False when none is known."""
    if not states:
        return False
    git = run.data.get("git") or {"repositories": [], "log": []}
    git["repositories"] = sorted(states)
    entry = {"event": event, "at": at, "repositories": deepcopy(states)}
    if exit is not None:
        entry["exit"] = exit
    git["log"].append(entry)
    run.data["git"] = git
    return True


def log_closing(run, exit: str, states: dict | None, *, at: str) -> bool:
    """Log a closing. Taken outside a run of the checks, it reads the repositories now."""
    git = run.data.get("git")
    if not states and git:
        states = repository_states(git["repositories"])
    return log_status(run, CLOSED, states, at=at, exit=exit)


# tarav.breadcrumb 96965ee9c5ef32c0d3793ca03344a5473fcc4fad4c1a5064bcead58566c6c338
# tarav.breadcrumb b8be776e5859bf1d518d07af0a8b687e3bc33d2346e7ea66262441953120e7c4
def log_clean(run, states: dict | None, *, at: str) -> bool:
    """Log each repository seen clean for the first time since the last status change."""
    git = run.data.get("git")
    if not git or not states:
        return False
    phase = _phase(git["log"])
    added = False
    for root, state in sorted(states.items()):
        if not state["clean"] or root not in git["repositories"] or _clean_in(phase, root):
            continue
        entry = {"event": CLEAN, "at": at, "repositories": {root: dict(state)}}
        git["log"].append(entry)
        phase.append(entry)
        added = True
    return added


def waiting(run) -> list[str]:
    """The repositories with no clean state since the action's last status change."""
    git = run.data.get("git")
    if not git:
        return []
    phase = _phase(git["log"])
    return [root for root in git["repositories"] if not _clean_in(phase, root)]


# tarav.breadcrumb ed8e1e75080d60fe25dbf368f2d1885b35abcc766ca9e31ef7cb82b396d77880
def advice(run) -> list[str]:
    """What an agent can do so that the log holds clean commits."""
    if not run.data.get("git"):
        return ["The suites above its checks declare no Git repository, so it logs none."]
    project = (run.data.get("project") or {}).get("root", "<project>")
    return [f"{root} was not clean at the last change of this action, nor since. Commit "
            f"it and run the checks again (tarav status --project {project}), so the log "
            f"holds a clean commit." for root in waiting(run)]


def _phase(log: list[dict]) -> list[dict]:
    """The entries since the last status change, that change included."""
    for index in range(len(log) - 1, -1, -1):
        if log[index]["event"] != CLEAN:
            return log[index:]
    return list(log)


def _clean_in(entries: list[dict], root: str) -> bool:
    return any((entry["repositories"].get(root) or {}).get("clean") for entry in entries)


__all__ = ["CLEAN", "CLOSED", "OPENED", "REOPENED", "advice", "log_clean", "log_closing",
           "log_status", "waiting"]
