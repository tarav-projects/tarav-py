"""Actions that follow a POI.

A POI is an event. An actionable POI also spins one action, and that action
is what persists: it stays open until one of its closing paths is taken. The
instance follows the POI's identity, so raising the same POI again lands on
the same action.

An action is registered under a Project. That Project hands each run of its
checks to its actions, and the Action Type here says what the run means for
one of them. Checks and POIs know nothing of this; a run that no Project
handed over is momentary and changes nothing.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar
from uuid import UUID

from tarav.l0.kernel import Ship, TaravClass, TypeShip, entity
from tarav.l1.checks import Check
from tarav.l1.operator_context import OperatorContext
from tarav.l1.poi import POI, IdentifiedPOI, fingerprint
from tarav.l1.poi.actionable import ActionablePOI, BlessablePOI

from .blessing import BLESSED, Blessing, BlessingInput, BlessingInputCheck
from . import (
    ACTIONS_WORKFLOW_SHIP, CLOSED, EXIT_ERROR, OPERATOR, PROJECT, RUNNING, ActionRun,
    ActionRunStore, ChecksUpdate, Closing, Exit, StepAction, axes, close_run, resolve_action,
)

GONE = "gone"
PRESENT, ABSENT, CHECK_FAILED = "present", "absent", "check failed"


# tarav.breadcrumb 7025ef0587c66a6d14f2ea5252a2442b77d086f0c0875f3031a32b72650786f5
class GoneClosing(Closing):
    """The record of an action closed because its Project's checks no longer produce its POI."""

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
            return {**super().record_example(), "exit": GONE, "by": PROJECT,
                    "project": {"id": "0f9d2c6a-7b14-4e85-a3c1-5d8e6f2b9a70",
                                "name": "example", "root": "/example"}}


# tarav.breadcrumb 66447b514cbe8113e679498308f85202d9091297afcc05a728d1cdffa9ff3b19
# tarav.breadcrumb e2ef906ba9d261e12b8eb7df9f7387f374e995076befb02acc3a8b599844b624
# tarav.breadcrumb fcc647ba041a791d3ee820ca5920cbc53a53235822a446126b369e6f5313fa1f
class POIResolutionAction(StepAction):
    """The action a POI spins: open while the POI stands, closed when it is gone or blessed.

    `gone` is taken by the action's Project when a run of its checks no longer
    produces the POI. `blessed` is taken by an operator who
    gives a reason: the action closes although the situation still exists.
    Each path leaves its own record, and that record decides whether the POI
    raised again reopens the action.
    """

    InputType: ClassVar[type[OperatorContext]] = BlessingInput
    exits: ClassVar[tuple[Exit, ...]] = (
        Exit(GONE, by=(PROJECT,), closing=GoneClosing),
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

    # tarav.breadcrumb c5db1b346c8b5ff563c654bb294079f0d167cfcdabea9a4e04cf10d35bceed8d
    @classmethod
    def opened(cls, poi: IdentifiedPOI, *, project: dict, at: str) -> ActionRun:
        """Build the action of a POI, open and not yet registered anywhere."""
        return ActionRun(action_id(poi), {
            "action": entity(cls).name, "state": RUNNING, "exit": None,
            "started_at": at, "opened_at": at, "closed_at": None, "project": project,
            "skill": cls.skill.to_json() if cls.skill else None,
            "intakes": [], "sessions": [], "opening": {"passed": True, "results": []},
            "operations": [], "closings": [], "output": None, "reason": None,
            "event": _event(poi), "closing": None,
            "situation": {"state": PRESENT, "at": at},
        })

    # tarav.breadcrumb 3379190a2340530d84b3e29c0a244d0687187b475d890292047e1f8a3f1ef4eb
    @classmethod
    def on_checks(cls, run: ActionRun, update: ChecksUpdate) -> str | None:
        """Follow the POI through a run of the Project's checks.

        The POI is among the results: the situation is present, and a closed
        action reopens when the way it was closed says so. The POI's check is
        there and did not complete: that is a result too, and it says nothing
        about the situation, so the action stays as it is. Otherwise the
        situation is absent, and an open action closes as gone.
        """
        event = run.data.get("event") or {}
        if not event:
            return None
        seen = update.memo.get(cls)
        if seen is None:
            seen = update.memo[cls] = {
                "raised": {str(action_id(poi)): poi for poi in raised(update.checks.pois())},
                "failed": {entity(type(result.check)).name
                           for result in update.checks.results
                           if result.status != "completed"},
            }
        poi = seen["raised"].get(str(run.id))
        situation = (run.data.get("situation") or {}).get("state")
        if poi is not None:
            change = None
            if event.get("blessable") != isinstance(poi, BlessablePOI):
                run.data["event"] = {**event, "blessable": isinstance(poi, BlessablePOI)}
                change = "updated"
            if situation != PRESENT:
                run.data["situation"] = {"state": PRESENT, "at": update.at}
                change = "updated"
            if run.state == CLOSED and run.exit != EXIT_ERROR:
                if cls.exit_named(run.exit).closing.reopens(run.data.get("closing"), poi):
                    run.data.update(state=RUNNING, exit=None, opened_at=update.at,
                                    closed_at=None, output=None, closing=None,
                                    event=_event(poi))
                    change = "reopened"
            return change
        state = CHECK_FAILED if (event.get("check") or {}).get("type") in seen["failed"] else ABSENT
        if situation == state:
            return None
        run.data["situation"] = {"state": state, "at": update.at}
        if state == CHECK_FAILED or run.state != RUNNING:
            return "updated"
        close_run(cls(), run, GONE, by=PROJECT, at=update.at, extra={"project": update.project})
        poi_record = event.get("poi") or {}
        update.signals.append(POIActionClosed(
            f"The situation of {poi_record.get('type')} is gone: {poi_record.get('message')}",
            situation={"action": str(run.id), "closed_at": update.at},
            subject={"project": update.project},
            evidence={"action": str(run.id), "exit": GONE, "poi": poi_record.get("id")}))
        return GONE


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


def raised(pois: Iterable[POI]) -> Iterable[IdentifiedPOI]:
    """The POIs among these that name the Type of the action they spin."""
    return (poi for poi in pois
            if isinstance(poi, ActionablePOI) and isinstance(poi, IdentifiedPOI)
            and type(poi).action is not None)


def _event(poi: IdentifiedPOI) -> dict:
    check = getattr(poi, "check", None)
    return {"blessable": isinstance(poi, BlessablePOI), "poi": poi.as_dict(detail=True),
            "check": {"type": entity(type(check)).name} if check is not None else None}


class POIActions:
    """Read how the actions that follow POIs stand."""

    def __init__(self, runs: ActionRunStore | None = None) -> None:
        self.runs = runs if runs is not None else ActionRunStore()

    def of(self, poi: POI) -> ActionRun | None:
        """The action of one POI, when it has one."""
        if next(iter(raised((poi,))), None) is None:
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
    "PRESENT", "action_id", "raised",
]
