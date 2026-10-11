"""Suites: who manages the actions that follow POIs.

Checks and POIs know nothing of suites. The caller of a check run names the
suite the run belongs to. A suite's meaning is fixed by its Type: running it
on a target tests the same thing as the last time. So a suite can open the
action of each POI it produces, find the actions it manages, and close the
ones whose POI it no longer produces.

A suite manages an action; it does not identify it. An action's identity
comes from its Type and its POI.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone

from tarav.l0.kernel import TaravClass, TaravType, TypeShip, entity
from tarav.l1.poi import POI, IdentifiedPOI
from tarav.l1.poi.actionable import ActionablePOI, BlessablePOI

from . import (
    ACTIONS_WORKFLOW_SHIP, CLOSED, EXIT_ERROR, RUNNING, SUITE, ActionRun, ActionRunStore,
    StepAction, close_run, resolve_action,
)
from .pois import ABSENT, GONE, PRESENT, POIActionClosed, action_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# tarav.breadcrumb 8c3659c3bc9f979c7415dfb1ff90d2557f50e27dac73173b9e521e36f1af5bea
# tarav.breadcrumb 1bea33b960edb844fcd2f6e399e52da1e6e04f2ea5c52ab460ed8738ea0e4a13
class Suite(TaravType):
    """Root of every suite. A subtype's Type identity is the suite's fixed identity."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6f3373d8-5897-49e4-9e92-7cf2102397bc"),
                          name="Tarav.Actions.Suite", workflow=ACTIONS_WORKFLOW_SHIP)

    def __init__(self, runs: ActionRunStore | None = None, *,
                 now: Callable[[], str] = _now) -> None:
        self.runs = runs if runs is not None else ActionRunStore()
        self._now = now

    @classmethod
    def reference(cls) -> dict[str, str]:
        """How an action names the suite that manages it."""
        return {"id": str(entity(cls).id), "name": entity(cls).name}

# tarav.breadcrumb 8ed9a34e3be8cb2b89131394fcd2737dfa14ca238561ee3095eea2d1e0b44c35
    def manages(self, run: ActionRun, target: dict) -> bool:
        return ((run.data.get("suite") or {}).get("id") == self.reference()["id"]
                and (run.data.get("project") or {}).get("root") == target.get("root"))

    def managed(self, target: dict) -> list[ActionRun]:
        """Every action this suite manages for one target, open or closed."""
        return [run for run in self.runs.list() if self.manages(run, target)]

    def _event(self, poi: IdentifiedPOI) -> dict:
        check = getattr(poi, "check", None)
        return {"blessable": isinstance(poi, BlessablePOI), "poi": poi.as_dict(detail=True),
                "check": {"type": entity(type(check)).name} if check is not None else None}

    def _raise(self, poi: IdentifiedPOI, target: dict, at: str) -> tuple[ActionRun, str | None]:
        """Record that the POI is raised: open its action, or reopen it when its closing says so."""
        key = action_id(poi)
        run = self.runs.find(str(key))
        if run is None:
            action_type = resolve_action(type(poi).action)
            return ActionRun(key, {
                "action": entity(action_type).name, "state": RUNNING, "exit": None,
                "started_at": at, "opened_at": at, "closed_at": None, "project": target,
                "skill": action_type.skill.to_json() if action_type.skill else None,
                "intakes": [], "sessions": [], "opening": {"passed": True, "results": []},
                "operations": [], "closings": [], "output": None, "reason": None,
                "event": self._event(poi), "closing": None,
                "situation": {"state": PRESENT, "at": at}, "suite": self.reference(),
            }), "opened"
        change = None
        if run.data.get("suite") is None:  # nobody manages it: this suite takes it over
            run.data.update(suite=self.reference(), project=target)
            change = "updated"
        if not self.manages(run, target):
            return run, None  # another suite's action: seen, left as it is
        event = run.data.get("event") or {}
        if event.get("blessable") != isinstance(poi, BlessablePOI):
            run.data["event"] = {**event, "blessable": isinstance(poi, BlessablePOI)}
            change = "updated"
        if (run.data.get("situation") or {}).get("state") != PRESENT:
            run.data["situation"] = {"state": PRESENT, "at": at}
            change = "updated"
        if run.state == CLOSED and run.exit != EXIT_ERROR:
            closing_type = resolve_action(run.data["action"]).exit_named(run.exit).closing
            if closing_type.reopens(run.data.get("closing"), poi):
                run.data.update(state=RUNNING, exit=None, opened_at=at, closed_at=None,
                                output=None, closing=None, event=self._event(poi))
                change = "reopened"
        return run, change

    # tarav.breadcrumb 0c49d730280e32ff0260c0b1563cbb89a7a4b05d11ff8167fa3750af08fae38c
    # tarav.breadcrumb f41eaa73e7dd28ec2987cd7fa86257b23cd4c1e599a27ebf403472b803565397
# tarav.breadcrumb 90369c005b0a6882530ec4f573a0f7068b6f24762c265593b00972eb8041ae41
    def settle(self, pois: Iterable[POI], *, target: dict, incomplete: Iterable[str] = (),
               complete: bool = True) -> dict:
        """Take the POIs of one run of this suite on `target` and settle its actions.

        Each actionable POI opens its action, or reopens it when the way it
        was closed says so. Then every action this suite manages for the
        target, and whose POI the run did not produce, has its situation
        marked absent and, when open, closes as gone.

        `incomplete` names the check Types that did not run to completion:
        the actions they raised are left as they are. `complete=False` says
        the caller did not run the whole suite; then nothing is closed.
        """
        at = self._now()
        seen: dict[str, ActionRun] = {}
        changed: dict[str, ActionRun] = {}
        summary = {"opened": 0, "reopened": 0, "gone": 0, "updated": 0}
        for poi in pois:
            if (not isinstance(poi, ActionablePOI) or not isinstance(poi, IdentifiedPOI)
                    or type(poi).action is None):
                continue
            key = str(action_id(poi))
            if key in seen:
                continue  # the same POI raised again in this run is the same action
            run, change = self._raise(poi, target, at)
            seen[key] = run
            if change is not None:
                changed[key] = run
                summary[change] += 1
        signals: list[POI] = []
        unknown = set(incomplete)
        for run in self.managed(target) if complete else ():
            key = str(run.id)
            event = run.data.get("event") or {}
            if key in seen or (event.get("check") or {}).get("type") in unknown:
                continue
            if (run.data.get("situation") or {}).get("state") == ABSENT:
                continue
            run.data["situation"] = {"state": ABSENT, "at": at}
            changed[key] = run
            if run.state != RUNNING:
                summary["updated"] += 1
                continue
            action_type = resolve_action(run.data["action"])
            if not issubclass(action_type, StepAction):
                continue
            close_run(action_type(), run, GONE, by=SUITE, at=at,
                      extra={"suite": self.reference()})
            summary["gone"] += 1
            poi_record = event.get("poi") or {}
            signals.append(POIActionClosed(
                f"The situation of {poi_record.get('type')} is gone: "
                f"{poi_record.get('message')}",
                situation={"action": key, "closed_at": at},
                subject={"suite": self.reference(), "target": target},
                evidence={"action": key, "exit": GONE, "poi": poi_record.get("id")}))
        keys = [self.runs.write(run) for run in changed.values()]
        self.runs.commit(keys, f"{entity(type(self)).name}: " + ", ".join(
            f"{count} {name}" for name, count in summary.items() if count))
        return {**summary, "actions": len(seen), "signals": signals}


__all__ = ["Suite"]
