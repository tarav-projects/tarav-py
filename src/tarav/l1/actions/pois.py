"""Actions that follow a POI.

A POI is an event. An actionable POI also spins one action, and that action
is what persists: it stays open until one of its exits is met. The instance
follows the POI's identity, so raising the same POI again lands on the same
action.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import ClassVar
from uuid import UUID

from tarav.l0.kernel import Ship, TaravClass, TypeShip, entity
from tarav.l1.checks import Check, CheckPOI, CheckResult, ClearPOI, SituationCheck
from tarav.l1.operator_context import OPERATOR_CONTEXT_WORKFLOW_SHIP, OperatorContext
from tarav.l1.poi import POI, IdentifiedPOI, fingerprint
from tarav.l1.poi.actionable import ActionablePOI

from . import (
    ACTIONS_WORKFLOW_SHIP, CLOSED, LOOP, OPERATOR, RUNNING, ActionRun, ActionRunStore, Exit,
    StepAction, resolve_action,
)

GONE, DISMISSED = "gone", "dismissed"


class DismissalInput(OperatorContext):
    """An operator's reason for dismissing a POI's action."""

    class RecordInterface(OperatorContext.RecordInterface):
        reason: str

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6f4a2d7e-1c39-4b85-a0d6-3e9b7c5f1a28"),
                          name="Tarav.Actions.POI.DismissalInput",
                          workflow=OPERATOR_CONTEXT_WORKFLOW_SHIP)

    class Records(OperatorContext.Records):
        def record_example(self) -> dict[str, object]:
            return {**super().record_example(), "reason": "Accepted as it is."}


class DismissalWithoutReason(CheckPOI):
    """A dismissal was attempted and its input gives no reason."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b3e8c1f5-9d27-4a60-8c4b-7f2e5a9d0c13"),
                          name="Tarav.Actions.POI.DismissalWithoutReason",
                          workflow=ACTIONS_WORKFLOW_SHIP)


class DismissalReasonCheck(SituationCheck):
    """Does the operator's input give a reason?"""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d7a5f3b9-2e61-4c08-9b7d-1a4c8e6f2d35"),
                          name="Tarav.Actions.POI.DismissalReasonCheck",
                          workflow=ACTIONS_WORKFLOW_SHIP)

    def __init__(self, run: ActionRun, context: OperatorContext) -> None:
        super().__init__(situation={"run": str(run.id), "context": str(context.id)})
        self._reason = context.fields.get("reason")

    def _run(self) -> CheckResult:
        if isinstance(self._reason, str) and self._reason.strip():
            return CheckResult(self, status="completed")
        return CheckResult(self, status="completed", pois=(self.poi(
            DismissalWithoutReason, message="The dismissal input gives no reason"),))


# tarav.breadcrumb 66447b514cbe8113e679498308f85202d9091297afcc05a728d1cdffa9ff3b19
# tarav.breadcrumb e2ef906ba9d261e12b8eb7df9f7387f374e995076befb02acc3a8b599844b624
class POIResolutionAction(StepAction):
    """The action a POI spins: open while the POI stands, closed when it is gone or dismissed.

    `gone` is taken when the POI's check reports clear for the same subject.
    `dismissed` is taken by an operator who gives a reason; the dismissal is
    kept in this action's record.
    """

    InputType: ClassVar[type[OperatorContext]] = DismissalInput
    exits: ClassVar[tuple[Exit, ...]] = (Exit(GONE, by=(LOOP,)), Exit(DISMISSED, by=(OPERATOR,)))

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e1c7a9d3-5b42-4f86-b3a0-8d6f2c4e7b19"),
                          name="Tarav.Actions.POI.Resolution", workflow=ACTIONS_WORKFLOW_SHIP)

    def exit_checks(self, name: str, run: ActionRun,
                    context: OperatorContext | None) -> Iterable[Check]:
        if name == DISMISSED and context is not None:
            return (DismissalReasonCheck(run, context),)
        return ()

    def output(self, name: str, run: ActionRun, context: OperatorContext | None) -> dict:
        if name == DISMISSED and context is not None:
            return {"reason": context.fields["reason"].strip(),
                    "by": (run.data["sessions"] or [None])[-1],
                    "context": str(context.id)}
        return {}


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


def _matches(run: ActionRun, check: Check) -> bool:
    """Is this the check that owns the run's POI, examining the same thing?

    The subject key decides when the check declares one; otherwise the check's
    identity across runs does.
    """
    event_check = (run.data.get("event") or {}).get("check") or {}
    if event_check.get("type") != entity(type(check)).name:
        return False
    if check.subject_key is not None or run.data.get("subject") is not None:
        return run.data.get("subject") == check.subject_key
    return check.identity is not None and event_check.get("identity") == check.identity


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class POIActions:
    """Hand POIs to the Actions workflow: findings open their action, clear results close.

    The checks know nothing of this. Whoever ran them decides to hand the
    POIs over, as it decides to show them.
    """

    def __init__(self, runs: ActionRunStore | None = None, *,
                 now: Callable[[], str] = _now) -> None:
        self.runs = runs if runs is not None else ActionRunStore()
        self._now = now

    # tarav.breadcrumb 0c49d730280e32ff0260c0b1563cbb89a7a4b05d11ff8167fa3750af08fae38c
    # tarav.breadcrumb f41eaa73e7dd28ec2987cd7fa86257b23cd4c1e599a27ebf403472b803565397
    def _trigger(self, poi: IdentifiedPOI, project: dict | None) -> tuple[ActionRun, str | None]:
        """Open the POI's action: created if absent, reopened if it was gone, else left as it is."""
        key = action_id(poi)
        run = self.runs.find(str(key))
        if run is None:
            check = getattr(poi, "check", None)
            action_type = resolve_action(type(poi).action)
            run = ActionRun(key, {
                "action": entity(action_type).name, "state": RUNNING, "exit": None,
                "started_at": self._now(), "opened_at": self._now(), "closed_at": None,
                "project": project,
                "skill": action_type.skill.to_json() if action_type.skill else None,
                "intakes": [], "sessions": [], "opening": {"passed": True, "results": []},
                "operations": [], "closings": [], "output": None, "reason": None,
                "subject": check.subject_key if check is not None else None,
                "event": {"poi": poi.as_dict(detail=True),
                          "check": {"type": entity(type(check)).name,
                                    "identity": check.identity} if check is not None else None},
            })
            return run, "opened"
        if run.state == CLOSED and run.exit == GONE:
            run.data.update(state=RUNNING, exit=None, opened_at=self._now(), closed_at=None,
                            output=None)
            return run, "reopened"
        return run, None

    def observe(self, pois: Iterable[POI], *, completed: Iterable[Check] = (),
                whole: bool = False, project: dict | None = None) -> dict:
        """Take one batch of POIs. Returns what changed and the POIs that say so.

        A finding opens its action. An open action closes as gone when its
        check completed in this batch, examining the same thing, and did not
        raise it: a clear POI says so, and so does a check named in
        `completed`. `whole` states that the batch is the provider's entire
        suite; then a check Type that cannot say which check it is closes its
        absent actions too, since every check of that Type has run.
        """
        pois = tuple(pois)
        present, changed, summary = set(), {}, {"opened": 0, "reopened": 0, "gone": 0}
        for poi in pois:
            if (not isinstance(poi, ActionablePOI) or not isinstance(poi, IdentifiedPOI)
                    or type(poi).action is None):
                continue
            if str(action_id(poi)) in present:
                continue  # the same POI raised again in this batch is the same action
            run, change = self._trigger(poi, project)
            present.add(str(run.id))
            if change is not None:
                changed[str(run.id)] = run
                summary[change] += 1
        checks = [*completed, *(poi.check for poi in pois if isinstance(poi, ClearPOI))]
        keyless = {entity(type(check)).name for check in checks
                   if check.subject_key is None and check.identity is None} if whole else set()
        signals: list[POI] = []
        if checks:
            root = (project or {}).get("root")
            for run in self.runs.list(state=RUNNING):
                key = str(run.id)
                event = run.data.get("event") or {}
                if key in present or (run.data.get("project") or {}).get("root") != root:
                    continue
                event_check = event.get("check") or {}
                unnamed = (run.data.get("subject") is None
                           and event_check.get("identity") is None
                           and event_check.get("type") in keyless)
                if not unnamed and not any(_matches(run, check) for check in checks):
                    continue
                run.data["closings"].append({"at": self._now(), "exit": GONE, "by": LOOP,
                                             "passed": True, "results": []})
                run.data.update(state=CLOSED, exit=GONE, closed_at=self._now(), output={})
                changed[key] = run
                summary["gone"] += 1
                poi_record = event.get("poi") or {}
                signals.append(POIActionClosed(
                    f"The situation of {poi_record.get('type')} is gone: "
                    f"{poi_record.get('message')}",
                    situation={"action": key, "closed_at": run.data["closed_at"]},
                    subject=run.data.get("subject") or {},
                    evidence={"action": key, "exit": GONE, "poi": poi_record.get("id")}))
        keys = [self.runs.write(run) for run in changed.values()]
        self.runs.commit(keys, "POI actions: " + ", ".join(
            f"{count} {name}" for name, count in summary.items() if count))
        return {**summary, "actions": len(present), "signals": signals}

    def of(self, poi: IdentifiedPOI) -> ActionRun | None:
        """The action of one POI, when it has one."""
        return self.runs.find(str(action_id(poi)))


POI_ACTION_RECORD_TYPES = (DismissalInput,)

__all__ = [
    "ActionablePOI", "DISMISSED", "DismissalInput", "DismissalReasonCheck",
    "DismissalWithoutReason", "GONE", "POIActionClosed", "POIActions",
    "POIResolutionAction", "POI_ACTION_RECORD_TYPES", "action_id",
]
