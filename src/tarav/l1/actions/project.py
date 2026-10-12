"""The actions registered under one Project.

A Project hands each suite of its checks that ran to this place. It registers the
actions of the POIs it sees for the first time, and passes the results to
every action registered under the Project; each Action Type decides what
they mean for it. Nothing here runs a check, and nothing here knows what a
POI action does with the results.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from tarav.l1.checks import CheckSuite

from . import ActionError, ActionRun, ActionRunStore, ChecksUpdate, resolve_action
from .pois import action_id, raised


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# tarav.breadcrumb 2e1b9af1c741842d056370e1564523ecd73419a67819a81e503c1a1ca1ddcdce
# tarav.breadcrumb c95725410973be077485242e93ae92ce1e0ff1ec061084a3825575e62a9ea14f
class ProjectActions:
    """The actions of one Project: register them, and hand them the Project's check results."""

    def __init__(self, project: dict, runs: ActionRunStore | None = None, *,
                 now: Callable[[], str] = _now) -> None:
        self.project = {"id": str(project["id"]), "name": project["name"],
                        "root": str(project["root"])}
        self.runs = runs if runs is not None else ActionRunStore()
        self._now = now

    @classmethod
    def of(cls, project, runs: ActionRunStore | None = None) -> "ProjectActions":
        return cls({"id": project.id, "name": project.name, "root": project.root}, runs)

    def list(self, *, state: str | None = None) -> list[ActionRun]:
        """The actions registered under this Project, newest first."""
        return self.runs.list(state=state, project_root=self.project["root"])

    def start(self, checks: CheckSuite, *, at: str | None = None) -> dict[str, ActionRun]:
        """Register here the action of each POI in the results that is not registered here.

        A new action is built by its Type. One registered under another
        Project moves: an action belongs to the Project whose checks produce
        its POI. Returns the changed actions by id; nothing is written.
        """
        at = at if at is not None else self._now()
        changed: dict[str, ActionRun] = {}
        known = {str(run.id) for run in self.list()}
        for chain, result in checks.walk():
            for poi in raised(result.pois()):
                key = str(action_id(poi))
                if key in known:
                    continue
                known.add(key)
                run = self.runs.find(key)
                if run is None:
                    run = resolve_action(type(poi).action).opened(
                        poi, project=self.project, at=at, suites=chain)
                else:
                    run.data["project"] = self.project
                changed[key] = run
        return changed

    def refresh(self, checks: CheckSuite, *, at: str | None = None,
                registered: dict[str, ActionRun] | None = None) -> tuple[dict, ChecksUpdate]:
        """Pass the results to every action registered here, open or closed.

        `registered` are actions `start` just registered and did not write.
        Returns what each changed action says it did, by id, and the update
        with the signals the actions raised.
        """
        update = ChecksUpdate(checks, self.project, at if at is not None else self._now())
        runs = {**{str(run.id): run for run in self.list()}, **(registered or {})}
        changes: dict[str, tuple[ActionRun, str]] = {}
        for key, run in runs.items():
            try:
                action_type = resolve_action(run.data["action"])
            except ActionError:
                continue  # a Type this runtime does not have
            change = action_type.on_checks(run, update)
            if change is not None:
                changes[key] = (run, change)
        return changes, update

    def update(self, checks: CheckSuite) -> dict:
        """Start and refresh this Project's actions from one run of its checks, and record it."""
        at = self._now()
        started = self.start(checks, at=at)
        changes, update = self.refresh(checks, at=at, registered=started)
        summary = {"opened": 0, "reopened": 0, "gone": 0, "updated": 0}
        written = {**started, **{key: run for key, (run, _) in changes.items()}}
        listed = []  # what an operator wants to hear about: opened, reopened, gone
        for key, run in written.items():
            if key in started and run.data["started_at"] == at:
                name = "opened"
            else:
                name = changes[key][1] if key in changes else "updated"
            name = name if name in summary else "updated"
            summary[name] += 1
            if name != "updated":
                poi = (run.data.get("event") or {}).get("poi") or {}
                listed.append({"change": name, "action": key,
                               "type": poi.get("type") or run.data["action"],
                               "message": poi.get("message"), "poi": poi.get("id")})
        keys = [self.runs.write(run) for run in written.values()]
        self.runs.commit(keys, f"Update the actions of {self.project['name']}: " + ", ".join(
            f"{count} {name}" for name, count in summary.items() if count))
        return {**summary, "actions": len({str(action_id(poi)) for poi in raised(checks.pois())}),
                "project": self.project, "changes": listed, "signals": update.signals}


__all__ = ["ProjectActions"]
