"""Actions that follow a POI.

A POI is an event. An actionable POI also spins one action, and that action
is what persists: it stays open until one of its closing paths is taken. The
instance follows the POI's identity, so raising the same POI again lands on
the same action.

Actions are resolved from a run of a Project's suite. The suite is the
Project's current set of checks: what a run of it produces is what is
happening now in that Project. Checks and POIs know nothing of this; a run
that no Project's suite produced is momentary and resolves nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import ClassVar
from uuid import UUID

from tarav.l0.kernel import Ship, TaravClass, TypeShip, entity
from tarav.l1.checks import Check, CheckResult, CheckRun
from tarav.l1.operator_context import OperatorContext
from tarav.l1.poi import POI, IdentifiedPOI, fingerprint
from tarav.l1.poi.actionable import ActionablePOI, BlessablePOI

from .blessing import BLESSED, Blessing, BlessingInput, BlessingInputCheck
from . import (
    ACTIONS_WORKFLOW_SHIP, CLOSED, EXIT_ERROR, OPERATOR, RUNNING, SUITE, ActionRun,
    ActionRunStore, Closing, Exit, StepAction, axes, close_run, resolve_action,
)

GONE = "gone"
PRESENT, ABSENT, CHECK_FAILED = "present", "absent", "check failed"


# tarav.breadcrumb 7025ef0587c66a6d14f2ea5252a2442b77d086f0c0875f3031a32b72650786f5
class GoneClosing(Closing):
    """The record of an action closed because its Project's suite no longer produces its POI."""

    class RecordInterface(Closing.RecordInterface):
        project: dict

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a14a7bc9-9483-4380-934a-324c53426fc1"),
                          name="Tarav.Actions.POI.Gone", workflow=ACTIONS_WORKFLOW_SHIP)

    @classmethod
    def reopens(cls, record: dict | None, poi: object) -> bool:
        return True  # the situation is back

    class Records(Closing.Records):
        def record_example(self) -> dict[str, object]:
            return {**super().record_example(), "exit": GONE, "by": SUITE,
                    "project": {"id": "0f9d2c6a-7b14-4e85-a3c1-5d8e6f2b9a70",
                                "name": "example", "root": "/example"}}


# tarav.breadcrumb 66447b514cbe8113e679498308f85202d9091297afcc05a728d1cdffa9ff3b19
# tarav.breadcrumb e2ef906ba9d261e12b8eb7df9f7387f374e995076befb02acc3a8b599844b624
# tarav.breadcrumb fcc647ba041a791d3ee820ca5920cbc53a53235822a446126b369e6f5313fa1f
class POIResolutionAction(StepAction):
    """The action a POI spins: open while the POI stands, closed when it is gone or blessed.

    `gone` is taken when a run of the suite of the action's Project no longer
    produces the POI. `blessed` is taken by an operator who
    gives a reason: the action closes although the situation still exists.
    Each path leaves its own record, and that record decides whether the POI
    raised again reopens the action.
    """

    InputType: ClassVar[type[OperatorContext]] = BlessingInput
    exits: ClassVar[tuple[Exit, ...]] = (
        Exit(GONE, by=(SUITE,), closing=GoneClosing),
        Exit(BLESSED, by=(OPERATOR,), closing=Blessing),
    )

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e1c7a9d3-5b42-4f86-b3a0-8d6f2c4e7b19"),
                          name="Tarav.Actions.POI.Resolution", workflow=ACTIONS_WORKFLOW_SHIP)

    def exit_checks(self, name: str, run: ActionRun,
                    context: OperatorContext | None) -> Iterable[Check]:
        if name == BLESSED and context is not None:
            return (BlessingInputCheck(run, context),)
        return ()


class POIActionClosed(IdentifiedPOI):
    """An open POI action closed because its situation is gone."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("c5b2f8a6-3d94-4e17-a8c1-6e0d9b7a4f52"),
                          name="Tarav.Actions.POI.Closed", workflow=ACTIONS_WORKFLOW_SHIP)


# tarav.breadcrumb 41d2f8ae4aa84337dc50a80be7140b1e8cda502096313cd5a5cc002c0d5ecb0f
def action_id(poi: IdentifiedPOI) -> Ship:
    """The action instance of a POI: its Action Type and the POI's identity, hashed."""
    action_type = resolve_action(type(poi).action)
    return Ship(str(UUID(fingerprint([str(entity(action_type).id), poi.identity])[:32])))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class POIActions:
    """The actions that follow POIs: resolve them from a run, and read how they stand."""

    def __init__(self, runs: ActionRunStore | None = None, *,
                 now: Callable[[], str] = _now) -> None:
        self.runs = runs if runs is not None else ActionRunStore()
        self._now = now

    def _event(self, poi: IdentifiedPOI) -> dict:
        check = getattr(poi, "check", None)
        return {"blessable": isinstance(poi, BlessablePOI), "poi": poi.as_dict(detail=True),
                "check": {"type": entity(type(check)).name} if check is not None else None}

    def _raise(self, poi: IdentifiedPOI, project: dict, at: str) -> tuple[ActionRun, str | None]:
        """Record that the POI is raised: open its action, or reopen it when its closing says so."""
        key = action_id(poi)
        run = self.runs.find(str(key))
        if run is None:
            action_type = resolve_action(type(poi).action)
            return ActionRun(key, {
                "action": entity(action_type).name, "state": RUNNING, "exit": None,
                "started_at": at, "opened_at": at, "closed_at": None, "project": project,
                "skill": action_type.skill.to_json() if action_type.skill else None,
                "intakes": [], "sessions": [], "opening": {"passed": True, "results": []},
                "operations": [], "closings": [], "output": None, "reason": None,
                "event": self._event(poi), "closing": None,
                "situation": {"state": PRESENT, "at": at},
            }), "opened"
        change = None
        if run.data.get("project") != project:
            # the action belongs to the Project whose suite produces its POI now
            run.data["project"] = project
            change = "updated"
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

# tarav.breadcrumb f7b417307203211567c885ca1212f7e3fe83f81d4975db8cf6d6b1da3bc0fe47
    def _raised(self, project: dict, results: tuple[CheckResult, ...], at: str,
                summary: dict, changed: dict, seen: dict) -> None:
        """Open, reopen or take over the action of each POI one Project's suite produced."""
        for poi in (poi for result in results for poi in result.pois()):
            if (not isinstance(poi, ActionablePOI) or not isinstance(poi, IdentifiedPOI)
                    or type(poi).action is None):
                continue
            key = str(action_id(poi))
            if key in seen:
                continue  # the same POI raised again in this run is the same action
            run, change = self._raise(poi, project, at)
            seen[key] = run
            if change is not None:
                changed[key] = run
                summary[change] += 1

# tarav.breadcrumb d1263f6bb272bc868b0e5fa4047c69f11f4ef67adddba122ceed9f10df6e7248
    def _unproduced(self, project: dict, results: tuple[CheckResult, ...], at: str,
                    summary: dict, changed: dict, seen: dict, signals: list) -> None:
        """Mark the actions of one Project whose POI its suite did not produce; close the open ones."""
        # a check that did not complete is present: it is a result, and it says
        # nothing about the situations checks of its Type raised before
        failed = {entity(type(result.check)).name for result in results
                  if result.status != "completed"}
        for run in self.runs.list(project_root=project.get("root")):
            key = str(run.id)
            event = run.data.get("event") or {}
            if key in seen or not event:
                continue
            state = CHECK_FAILED if (event.get("check") or {}).get("type") in failed else ABSENT
            if (run.data.get("situation") or {}).get("state") == state:
                continue
            run.data["situation"] = {"state": state, "at": at}
            changed[key] = run
            if state == CHECK_FAILED or run.state != RUNNING:
                summary["updated"] += 1
                continue
            action_type = resolve_action(run.data["action"])
            if not issubclass(action_type, StepAction):
                continue
            close_run(action_type(), run, GONE, by=SUITE, at=at, extra={"project": project})
            summary["gone"] += 1
            poi_record = event.get("poi") or {}
            signals.append(POIActionClosed(
                f"The situation of {poi_record.get('type')} is gone: "
                f"{poi_record.get('message')}",
                situation={"action": key, "closed_at": at},
                subject={"project": project},
                evidence={"action": key, "exit": GONE, "poi": poi_record.get("id")}))

    # tarav.breadcrumb 0c49d730280e32ff0260c0b1563cbb89a7a4b05d11ff8167fa3750af08fae38c
    # tarav.breadcrumb f41eaa73e7dd28ec2987cd7fa86257b23cd4c1e599a27ebf403472b803565397
# tarav.breadcrumb 7caa100f97b2250311e9db91718bd780c05dc1e45d156595b02901785fe646c4
    def resolve(self, check_run: CheckRun) -> dict:
        """Resolve the actions of every Project whose suite produced results in this run.

        For each such Project: a POI its suite produced opens its action, or
        reopens it when the way it was closed says so; an action of that
        Project whose POI no suite of this run produced has its situation
        marked absent and, when open, closes as gone. An action whose check
        is present and did not complete is left as it is, and says so. An
        action belongs to the Project whose suite produces its POI.

        Results that no Project's suite produced resolve nothing.
        """
        at = self._now()
        summary = {"opened": 0, "reopened": 0, "gone": 0, "updated": 0}
        changed: dict[str, ActionRun] = {}
        seen: dict[str, ActionRun] = {}
        signals: list[POI] = []
        groups = check_run.groups()
        for project, results in groups:
            self._raised(project, results, at, summary, changed, seen)
        for project, results in groups:
            self._unproduced(project, results, at, summary, changed, seen, signals)
        keys = [self.runs.write(run) for run in changed.values()]
        self.runs.commit(keys, "Resolve POI actions: " + ", ".join(
            f"{count} {name}" for name, count in summary.items() if count))
        return {**summary, "actions": len(seen),
                "projects": [project for project, _ in groups], "signals": signals}

    def of(self, poi: POI) -> ActionRun | None:
        """The action of one POI, when it has one."""
        if (not isinstance(poi, ActionablePOI) or not isinstance(poi, IdentifiedPOI)
                or type(poi).action is None):
            return None
        return self.runs.find(str(action_id(poi)))

    # tarav.breadcrumb 8f939b3150b542c2209f9343f1af08edebc857e9eb4f18d1ccbc5d446e3b27cd
    def standing(self, poi: POI) -> str:
        """`blessed` when the POI's action is closed by a blessing, otherwise `open`.

        A POI that is being raised has an open situation whatever an earlier
        `gone` closing says, so only a blessing settles it.
        """
        run = self.of(poi)
        return BLESSED if run is not None and run.exit == BLESSED else "open"

    def axes(self, poi: POI) -> dict[str, str | None] | None:
        """The status axes of the POI's action; None when it has no action yet."""
        run = self.of(poi)
        return axes(run) if run is not None else None

    def blessing(self, poi: POI) -> Blessing | None:
        """The Blessing that closed the POI's action, when one did."""
        run = self.of(poi)
        closing = run.closing() if run is not None else None
        return closing if isinstance(closing, Blessing) else None

    def blessing_standing(self, poi: POI) -> dict | None:
        """For reports: whether a blessable POI is blessed, and by which Blessing."""
        if not isinstance(poi, BlessablePOI):
            return None
        blessing = self.blessing(poi)
        return {"status": "blessed" if blessing is not None else "unblessed",
                "blessing": str(blessing.id) if blessing is not None else None}


POI_ACTION_RECORD_TYPES = (GoneClosing,)

__all__ = [
    "ABSENT", "ActionablePOI", "BLESSED", "BlessablePOI", "CHECK_FAILED", "GONE", "GoneClosing",
    "POIActionClosed", "POIActions", "POIResolutionAction", "POI_ACTION_RECORD_TYPES",
    "PRESENT", "action_id",
]
