"""Actions that follow a POI.

A POI is an event. An actionable POI also spins one action, and that action
is what persists: it stays open until one of its closing paths is taken. The
instance follows the POI's identity, so raising the same POI again lands on
the same action. A suite opens these actions and settles them; see
`tarav.l1.actions.suites`.
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
    ACTIONS_WORKFLOW_SHIP, OPERATOR, SUITE, ActionRun, ActionRunStore, Closing, Exit,
    StepAction, axes, resolve_action,
)

GONE = "gone"
PRESENT, ABSENT = "present", "absent"


# tarav.breadcrumb 7025ef0587c66a6d14f2ea5252a2442b77d086f0c0875f3031a32b72650786f5
class GoneClosing(Closing):
    """The record of an action closed because its suite no longer detects the situation."""

    class RecordInterface(Closing.RecordInterface):
        suite: dict

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
                    "suite": {"id": "6f3373d8-5897-49e4-9e92-7cf2102397bc",
                              "name": "Tarav.Actions.Suite"}}


# tarav.breadcrumb 66447b514cbe8113e679498308f85202d9091297afcc05a728d1cdffa9ff3b19
# tarav.breadcrumb e2ef906ba9d261e12b8eb7df9f7387f374e995076befb02acc3a8b599844b624
# tarav.breadcrumb fcc647ba041a791d3ee820ca5920cbc53a53235822a446126b369e6f5313fa1f
class POIResolutionAction(StepAction):
    """The action a POI spins: open while the POI stands, closed when it is gone or blessed.

    `gone` is taken by the suite that manages the action, when a run of that
    suite no longer produces the POI. `blessed` is taken by an operator who
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


class POIActions:
    """Read the actions that follow POIs: which action, how it stands, its blessing."""

    def __init__(self, runs: ActionRunStore | None = None) -> None:
        self.runs = runs if runs is not None else ActionRunStore()

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
    "ABSENT", "ActionablePOI", "BLESSED", "BlessablePOI", "GONE", "GoneClosing",
    "POIActionClosed", "POIActions", "POIResolutionAction", "POI_ACTION_RECORD_TYPES",
    "PRESENT", "action_id",
]
