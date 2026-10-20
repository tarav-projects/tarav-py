"""Actions that follow a POI.

A POI is an event. An actionable POI also spins one action, and that action
is what persists: it stays open until one of its closing paths is taken. The
instance follows the POI's identity, so raising the same POI again lands on
the same action.

A POI is a flag between detecting and working: momentary, owning nothing. An
action is registered under a Project. That Project hands each run of its
checks to its actions, and the Action Type here says what the run means for
one of them. Checks and POIs know nothing of this; a run that no Project
handed over is momentary and changes nothing. How an action stands for a POI
is asked of the Project (`project.actions`).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar
from uuid import UUID

from tarav.l0.kernel import Ship, TaravClass, TypeShip, entity
from tarav.l1.checks import Check
from tarav.l1.operator_context import OperatorContext
from tarav.l1.poi import POI, SituationPOI, fingerprint, plain
from tarav.l1.poi.actionable import ActionablePOI

from .blessing import BLESSED, Blessing, BlessingInput, BlessingInputCheck
from . import (
    ACTIONS_WORKFLOW_SHIP, CLOSED, EXIT_ERROR, OPERATOR, PROJECT, RUNNING, ActionRun, ChecksUpdate, Closing, Exit, StepAction,
    close_run, resolve_action,
)
from . import tape
from tarav.l0.kernel import LoadedRecord

GONE = "gone"
PRESENT, ABSENT, CHECK_FAILED, NOT_RUN = "present", "absent", "check failed", "not run"


# tarav.breadcrumb 7025ef0587c6
class GoneClosing(Closing):
    """The record of an action closed because its Project's checks no longer produce its POI."""

    class RecordInterface(Closing.RecordInterface):
        project: dict

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a14a7bc9-9483-4380-934a-324c53426fc1"),
                          name="Tarav.Actions.POI.Gone", workflow=ACTIONS_WORKFLOW_SHIP)

    reopens = True  # the situation is back

    class Records(Closing.Records):
        def record_example(self) -> dict[str, object]:
            return {**super().record_example(), "exit": GONE, "by": PROJECT,
                    "project": {"id": "0f9d2c6a-7b14-4e85-a3c1-5d8e6f2b9a70",
                                "name": "example", "root": "/example"}}


# tarav.breadcrumb 66447b514cbe
# tarav.breadcrumb e2ef906ba9d2
# tarav.breadcrumb fcc647ba041a
class POIResolutionAction(StepAction):
    """The action a POI spins: open while the POI stands, closed when it is gone.

    `gone` is taken by the action's Project when a suite above the POI's check
    ran completely and did not produce the POI. Each closing path leaves its
    own record, and its Closing Type says whether the POI raised again
    reopens the action. An Action Type whose POI may be accepted as it stands
    is a `BlessableResolution`.
    """

    exits: ClassVar[tuple[Exit, ...]] = (Exit(GONE, by=(PROJECT,), closing=GoneClosing),)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e1c7a9d3-5b42-4f86-b3a0-8d6f2c4e7b19"),
                          name="Tarav.Actions.POI.Resolution", workflow=ACTIONS_WORKFLOW_SHIP)

    # tarav.breadcrumb c5db1b346c8b
    @classmethod
    def opened(cls, poi: SituationPOI, *, project: dict, at: str,
               suites: tuple[dict, ...] = (), git: dict | None = None) -> ActionRun:
        """Build the action of a POI, open and not yet registered anywhere.

        `suites` are the identified suites above the check that raised it, and
        `git` the state of the repositories they declare.
        """
        run = ActionRun(action_id(poi), {
            "action": entity(cls).name, "project": project,
            "skill": cls.skill.to_json() if cls.skill else None,
            "intakes": [], "sessions": [], "opening": {"passed": True, "results": []},
            "operations": [], "output": None, "reason": None, "tape": [],
            "event": _event(poi, suites), "situation": {"state": PRESENT, "at": at},
        })
        tape.opened(run, at=at, states=git)
        return run

    # tarav.breadcrumb 5aeb4d2196d4
    @classmethod
    def on_checks(cls, run: ActionRun, update: ChecksUpdate) -> str | None:
        """Follow the POI through a suite of the Project's checks that ran.

        The POI is among the results: the situation is present, and a closed
        action reopens when the way it was closed says so. It is not: the
        suites above its check are the detectors, and only one whose own
        code ran to its end can say the situation is gone. The nearest of
        them that is in this run decides; when none is, the suite handed
        over does only if it is an unscoped Project suite or an identified
        ancestor of the detector. A suite that did not run, or in which a
        check of the POI's Type failed, says nothing, and the action stays.
        """
        event = run.data.get("event") or {}
        if not event:
            return None
        seen = update.memo.get(cls)
        if seen is None:
            raised_now = {}
            for chain, result in update.checks.walk():
                for poi in raised(result.pois()):
                    raised_now.setdefault(str(action_id(poi)), (poi, chain, result.git))
            seen = update.memo[cls] = {
                "raised": raised_now,
                "suites": {_suite_key(suite.identity): suite
                           for suite in reversed(update.checks.suites())
                           if suite.identity is not None},
            }
        found = seen["raised"].get(str(run.id))
        situation = (run.data.get("situation") or {}).get("state")
        if found is not None:
            poi, chain, git = found
            change = None
            fresh = _event(poi, chain)
            if event != fresh:
                # the same POI, raised again with other words or other details:
                # the action keeps the POI as it is raised now
                run.data["event"] = event = fresh
                change = "updated"
            if situation != PRESENT:
                run.data["situation"] = {"state": PRESENT, "at": update.at}
                change = "updated"
            if run.state == CLOSED and run.exit != EXIT_ERROR:
                if cls.exit_named(run.exit).closing.reopens:
                    # tarav.breadcrumb a41daa65b5b4
                    # tarav.breadcrumb a16bb5e9dc95
                    # the closing stays on the tape; the action opens again
                    run.data.update(output=None, event=fresh)
                    tape.reopened(run, at=update.at, states=git)
                    change = "reopened"
            if tape.clean(run, git, at=update.at):
                change = change or "updated"
            return change
        # tarav.breadcrumb db909a4b904d
        recorded = {_suite_key(suite) for suite in event["suites"]}
        detector = next((seen["suites"][key] for key in map(_suite_key, reversed(event["suites"]))
                         if key in seen["suites"]), None)
        if detector is None:
            root = update.checks
            if root.identity is None or _suite_key(root.identity) in recorded:
                detector = root
        if detector is None:
            if situation == NOT_RUN:
                return None
            run.data["situation"] = {"state": NOT_RUN, "at": update.at}
            return "updated"
        check_type = (event.get("check") or {}).get("type")
        if detector.conclusive_for(check_type):
            state = ABSENT
        elif detector.exhausted:
            state = CHECK_FAILED
        else:
            state = NOT_RUN
        logged = tape.clean(run, detector.git, at=update.at)
        if situation == state:
            return "updated" if logged else None
        run.data["situation"] = {"state": state, "at": update.at}
        if state != ABSENT or run.state != RUNNING:
            return "updated"
        close_run(cls(), run, GONE, by=PROJECT, at=update.at, extra={"project": update.project},
                  git=detector.git)
        poi_record = event.get("poi") or {}
        update.signals.append(POIActionClosed(
            f"The situation of {poi_record.get('type')} is gone: {poi_record.get('message')}",
            situation={"action": str(run.id), "closed_at": update.at},
            project=update.project,
            closed={"action": str(run.id), "exit": GONE, "poi": poi_record.get("id")}))
        return GONE


# tarav.breadcrumb b91637159644
# tarav.breadcrumb 10dc415d9609
class BlessableResolution(POIResolutionAction):
    """Family: the action of a POI that an operator may accept as it stands.

    `blessed` is taken by an operator who gives a reason: the action closes
    although the situation still exists, and stays closed while the same POI
    is raised. A blessing is one closing path of such an action; whether a
    POI may be blessed is whether its Action Type has this exit. Each POI Type
    names its own subtype.
    """

    InputType: ClassVar[type[OperatorContext]] = BlessingInput
    exits: ClassVar[tuple[Exit, ...]] = (
        *POIResolutionAction.exits,
        Exit(BLESSED, by=(OPERATOR,), closing=Blessing),
    )

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3b337bc7-1275-46ad-87f0-f4c221cd4804"),
                          name="Tarav.Actions.POI.BlessableResolution",
                          workflow=ACTIONS_WORKFLOW_SHIP)

    def exit_checks(self, name: str, run: ActionRun,
                    context: OperatorContext | None) -> Iterable[Check]:
        if name == BLESSED and context is not None:
            return (BlessingInputCheck(run, context),)
        return ()


class POIActionClosed(SituationPOI):
    """An open POI action closed because its situation is gone.

    `project` is the Project the action belongs to, and `closed` says which
    action closed, by which exit, and the id of the POI it followed.
    """

    def __init__(self, message: str, *, situation, project: dict, closed: dict) -> None:
        super().__init__(message, situation=situation)
        self.project = dict(project)
        self.closed = dict(closed)

    class RecordInterface(SituationPOI.RecordInterface):
        project: dict
        closed: dict

    def _to_record(self) -> dict[str, object]:
        return {**super()._to_record(), "project": plain(self.project),
                "closed": plain(self.closed)}

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        result = super()._from_record(loaded)
        result.project, result.closed = loaded.data.project, loaded.data.closed
        return result

    class Records(SituationPOI.Records):
        def record_example(self) -> dict[str, object]:
            return {**super().record_example(), "project": {"id": "0f9d2c6a-7b14-4e85-a3c1-5d8e6f2b9a70", "name": "example",
                                "root": "/example"},
                    "closed": {"action": "example", "exit": GONE, "poi": "example"}}

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("c5b2f8a6-3d94-4e17-a8c1-6e0d9b7a4f52"),
                          name="Tarav.Actions.POI.Closed", workflow=ACTIONS_WORKFLOW_SHIP)


# tarav.breadcrumb 41d2f8ae4aa8
def action_id(poi: SituationPOI) -> Ship:
    """The action instance of a POI: its Action Type and the POI's identity, hashed."""
    action_type = resolve_action(type(poi).action)
    return Ship(str(UUID(fingerprint([str(entity(action_type).id), poi.identity])[:32])))


def raised(pois: Iterable[POI]) -> Iterable[SituationPOI]:
    """The POIs among these that name the Type of the action they spin."""
    return (poi for poi in pois
            if isinstance(poi, ActionablePOI) and isinstance(poi, SituationPOI)
            and type(poi).action is not None)


def _event(poi: SituationPOI, suites: tuple[dict, ...] = ()) -> dict:
    """What an action keeps of the POI it follows: the POI's record, and its detectors."""
    check = getattr(poi, "check", None)
    return {"poi": poi.records.to_record(),
            "check": {"type": entity(type(check)).name} if check is not None else None,
            "suites": [dict(suite) for suite in suites]}


def _suite_key(identity: dict) -> tuple:
    return identity["type"], identity["key"]


POI_ACTION_RECORD_TYPES = (GoneClosing,)

__all__ = [
    "ABSENT", "ActionablePOI", "BLESSED", "BlessableResolution", "CHECK_FAILED", "GONE", "GoneClosing",
    "NOT_RUN",
    "POIActionClosed", "POIResolutionAction", "POI_ACTION_RECORD_TYPES",
    "PRESENT", "action_id", "raised",
]
