"""Blessing a POI as an Action: the root of every action that aims to bless.

A bundle of three parts. `BlessingAction` is a Step whose `bless` operation
writes the blessing and names the run in it. `BlessedThroughAction` is the
POI capability "blessed only through a blessing action". The
`UnharnessedBlessingCheck` reports a blessing of such a POI that names no run.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.actions import (
    ACTIONS_WORKFLOW_SHIP, RUN_REFERENCE_TYPE, ActionError, ActionRun, StepAction,
)
from tarav.l1.blessings import BlessablePOI, BlessingStore
from tarav.l1.checks import Check, CheckPOI, CheckResult, SituationCheck
from tarav.l1.operator_context import OPERATOR_CONTEXT_WORKFLOW_SHIP, OperatorContext
from tarav.l1.poi import POI, fingerprint


# tarav.breadcrumb f298c36c9d7fead8dcabbad3eefa0c1792ad464090fe8e2e389bf5ca8db1f409
class BlessedThroughAction(BlessablePOI):
    """A blessable POI whose blessings are made through a blessing action."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("92b67c0f-44b3-4d4d-9b9f-6a60044a06ae"),
                          name="Tarav.Actions.Blessing.BlessedThroughAction",
                          workflow=ACTIONS_WORKFLOW_SHIP)


class BlessingInput(OperatorContext):
    """Which POI to bless and, once the operator has it, why."""

    class RecordInterface(OperatorContext.RecordInterface):
        poi_id: str
        rationale: str | None = None

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d611fd8d-803a-405c-8e05-3e03e4755eee"),
                          name="Tarav.Actions.Blessing.Input",
                          workflow=OPERATOR_CONTEXT_WORKFLOW_SHIP)

    class Records(OperatorContext.Records):
        def record_example(self) -> dict[str, object]:
            return {**super().record_example(), "poi_id": "0" * 64}


class BlessingTargetNotRaised(CheckPOI):
    """The POI named for blessing is not raised now."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("72942599-f50a-47f1-8909-162e5e2e60d4"),
                          name="Tarav.Actions.Blessing.TargetNotRaised",
                          workflow=ACTIONS_WORKFLOW_SHIP)


class BlessingTargetOutsideAction(CheckPOI):
    """The POI named for blessing is not of the Type this action blesses."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("4178598c-561c-4b15-b84a-38ea617c474a"),
                          name="Tarav.Actions.Blessing.TargetOutsideAction",
                          workflow=ACTIONS_WORKFLOW_SHIP)


class BlessingTargetAlreadyBlessed(CheckPOI):
    """The POI named for blessing already has a blessing."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ce0d02f0-03e1-42d1-a06d-0907465f54d7"),
                          name="Tarav.Actions.Blessing.TargetAlreadyBlessed",
                          workflow=ACTIONS_WORKFLOW_SHIP)


class BlessingNotMadeInRun(CheckPOI):
    """The run is closing and no blessing of its POI names this run."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d20dd8a7-d0ae-49b4-838e-16a2b60c5087"),
                          name="Tarav.Actions.Blessing.NotMadeInRun",
                          workflow=ACTIONS_WORKFLOW_SHIP)


class UnharnessedBlessing(CheckPOI):
    """A POI blessed only through an action has a blessing that names no action run."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e3b16a65-d23b-4ad2-a4cb-ea3a462d8d52"),
                          name="Tarav.Actions.Blessing.Unharnessed",
                          workflow=ACTIONS_WORKFLOW_SHIP)


def _names_run(record: dict, run_id: str | None = None) -> bool:
    return any(item.get("type") == RUN_REFERENCE_TYPE
               and (run_id is None or item.get("locator", {}).get("run") == run_id)
               for item in record.get("support", ()))


class BlessingOpeningCheck(SituationCheck):
    """Can this run bless its POI: is it raised, of the right Type, and unblessed?"""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("dc61709e-2c2e-4303-b8c6-af9016a1ba97"),
                          name="Tarav.Actions.Blessing.OpeningCheck",
                          workflow=ACTIONS_WORKFLOW_SHIP)

    def __init__(self, action: "BlessingAction", run: ActionRun,
                 context: OperatorContext) -> None:
        super().__init__(situation={"run": str(run.id), "poi": context.fields["poi_id"]})
        self._action, self._context = action, context

    def _run(self) -> CheckResult:
        action, context = self._action, self._context
        poi = action.find_poi(context)
        if poi is None:
            found = self.poi(BlessingTargetNotRaised,
                             message=f"POI {context.fields['poi_id']} is not raised now")
        elif not isinstance(poi, type(action).poi_type):
            found = self.poi(
                BlessingTargetOutsideAction,
                message=f"{entity(type(poi)).name} is not blessed by {entity(type(action)).name}",
                details={"poi_type": entity(type(poi)).name,
                         "blessed_type": entity(type(action).poi_type).name})
        elif action.blessings(context).standing(poi)["status"] == "blessed":
            found = self.poi(BlessingTargetAlreadyBlessed,
                             message=f"POI {poi.identity} is already blessed")
        else:
            return CheckResult(self, status="completed")
        return CheckResult(self, status="completed", pois=(found,))


class BlessingClosingCheck(SituationCheck):
    """Did this run bless its POI?"""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("48ac4a18-d111-4799-bc55-716aa2b9b315"),
                          name="Tarav.Actions.Blessing.ClosingCheck",
                          workflow=ACTIONS_WORKFLOW_SHIP)

    def __init__(self, action: "BlessingAction", run: ActionRun,
                 context: OperatorContext) -> None:
        super().__init__(situation={"run": str(run.id), "poi": context.fields["poi_id"]})
        self._action, self._run_id, self._context = action, str(run.id), context

    def _run(self) -> CheckResult:
        if self._action.blessings_in_run(self._run_id, self._context):
            return CheckResult(self, status="completed")
        return CheckResult(self, status="completed", pois=(self.poi(
            BlessingNotMadeInRun,
            message=f"No blessing of POI {self._context.fields['poi_id']} names run {self._run_id}"),))


# tarav.breadcrumb 761731e314ddda77af6f36d81676b8c1ea03e1be876a305656743a54b7d88035
# tarav.breadcrumb f654f00b8a205382dcc2d0ea4507274d0680bd8cc8dab6a527d5d25d7626e68b
class BlessingAction(StepAction):
    """Root of the actions that bless a POI.

    A subtype says where its POIs and blessings are (`find_poi`, `blessings`)
    and may narrow `poi_type` to the POI Types it blesses.
    """

    InputType: ClassVar[type[OperatorContext]] = BlessingInput
    operations: ClassVar[tuple[str, ...]] = ("bless",)
    poi_type: ClassVar[type[POI]] = BlessablePOI

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a94cadd6-a356-4200-9b86-1eaa6559bb7f"),
                          name="Tarav.Actions.Blessing", workflow=ACTIONS_WORKFLOW_SHIP)

    def find_poi(self, context: OperatorContext) -> POI | None:
        """The POI the input names, as it is raised now; None when it is not."""
        raise NotImplementedError

    def blessings(self, context: OperatorContext) -> BlessingStore:
        raise NotImplementedError

    def actor(self, run: ActionRun, context: OperatorContext) -> dict:
        session = (run.data["sessions"] or [None])[-1]
        return {"type": "Tarav.Actions.Operator",
                "locator": session and {"provider": session["provider"],
                                        "session_id": session["session_id"]}
                or {"operator": "unidentified"}}

    def blessings_in_run(self, run_id: str, context: OperatorContext) -> list[str]:
        records = self.blessings(context).snapshot()["records"]
        return [record["id"] for record in records
                if record.get("poi", {}).get("id") == context.fields["poi_id"]
                and _names_run(record, run_id)]

    def opening_checks(self, run: ActionRun, context: OperatorContext) -> Iterable[Check]:
        return (BlessingOpeningCheck(self, run, context),)

    def closing_checks(self, run: ActionRun, context: OperatorContext) -> Iterable[Check]:
        return (BlessingClosingCheck(self, run, context),)

    def operate(self, name: str, run: ActionRun, context: OperatorContext) -> dict:
        if name != "bless":
            return super().operate(name, run, context)
        rationale = context.fields.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ActionError("The input has no rationale; put it in the Operator Context first")
        poi = self.find_poi(context)
        if poi is None or not isinstance(poi, type(self).poi_type):
            raise ActionError(f"POI {context.fields['poi_id']} cannot be blessed by this run now")
        record = self.blessings(context).bless(
            poi, actor=self.actor(run, context), rationale=rationale.strip(),
            support=(run.reference(),))
        return {"blessing": record["id"], "poi": poi.identity}

    def output(self, run: ActionRun, context: OperatorContext) -> dict:
        return {"poi": context.fields["poi_id"],
                "blessings": self.blessings_in_run(str(run.id), context)}


# tarav.breadcrumb 03480e65123e74e9235940bdd48cb906e323154edc3a0083caf2077b349358fd
class UnharnessedBlessingCheck(Check):
    """Blessings of action-blessed POI Types that were made outside an action run."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e57156ef-a949-4cff-ae53-3a9953669ff5"),
                          name="Tarav.Actions.Blessing.UnharnessedCheck",
                          workflow=ACTIONS_WORKFLOW_SHIP)

    def __init__(self, store: BlessingStore, *, poi_types: Iterable[type[POI]]) -> None:
        super().__init__()
        self.store = store
        self.poi_types = tuple(poi_types)
        if any(not issubclass(item, BlessedThroughAction) for item in self.poi_types):
            raise TypeError("Expected POI Types that are blessed through an action")

    @property
    def identity(self) -> str:
        return fingerprint([str(entity(type(self)).id), str(Path(self.store.root)),
                            sorted(entity(item).name for item in self.poi_types)])

    def _run(self) -> CheckResult:
        names = {entity(item).name for item in self.poi_types}
        pois = [
            UnharnessedBlessing(
                self, f"Blessing {record['id']} of a {record['poi'].get('type')} names no action run",
                situation={"blessing": record["id"]},
                details={"blessing": record["id"], "poi": record["poi"].get("id"),
                         "poi_type": record["poi"].get("type"), "actor": record.get("actor")})
            for record in self.store.snapshot()["records"]
            if isinstance(record.get("poi"), dict)
            and record["poi"].get("type") in names and not _names_run(record)
        ]
        return CheckResult(self, status="completed", pois=pois)


BLESSING_ACTION_RECORD_TYPES = (BlessingInput,)

__all__ = [
    "BLESSING_ACTION_RECORD_TYPES", "BlessedThroughAction", "BlessingAction",
    "BlessingClosingCheck", "BlessingInput", "BlessingNotMadeInRun", "BlessingOpeningCheck",
    "BlessingTargetAlreadyBlessed", "BlessingTargetNotRaised", "BlessingTargetOutsideAction",
    "UnharnessedBlessing", "UnharnessedBlessingCheck",
]
