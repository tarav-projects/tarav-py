"""Typed Actions and their recorded runs.

An Action Type is a definition and an ActionRun is one instance of it, as a
program and a process are. The base Action prescribes almost nothing. A
StepAction closes a piece of an operator's work into one step: an opening
test, the work, closing tests.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar
from uuid import uuid4

from tarav.l0.kernel import (
    FileRecord, Ship, TaravClass, TaravEntity, TaravType, TypeShip, entity,
)
from tarav.l1.checks import Check, CheckPOI, CheckResult
from tarav.l1.poi import IdentifiedPOI
from tarav.l1.operator_context import Intake, OperatorContext, OperatorContextStore
from tarav.l1.records import RecordRegistry

from .workflow import ACTIONS_WORKFLOW_SHIP, ActionsWorkflow

RUNNING, CLOSED = "running", "closed"
EXIT_OK, EXIT_ERROR = "ok", "error"
RUN_REFERENCE_TYPE = "Tarav.Actions.RunReference"


class ActionError(RuntimeError):
    """An Action was used in a way its definition or its run does not allow."""


@dataclass(frozen=True)
class SkillLink:
    """Where the operator's instructions for an Action are: a skill and a path inside it."""

    skill: str
    path: str = ""

    def to_json(self) -> dict[str, str]:
        return {"skill": self.skill, "path": self.path}


# tarav.breadcrumb 172bd4f5f4e23e808f5494a5f027e73f698c95cde8cb01634728d6d12ff891df
class Action(TaravType):
    """Root of every Action Type. It prescribes only the link to its instructions."""

    skill: ClassVar[SkillLink | None] = None

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("5b7deb17-f328-4470-87ea-a17ef370e92f"),
                          name="Tarav.Actions.Action", workflow=ACTIONS_WORKFLOW_SHIP)


# tarav.breadcrumb 9653fbc6c09471fe85885cd12a4a103d86fba2aba9efab0ac507c2dd94cd3942
# tarav.breadcrumb 211a93166d7c38a5177f8e8030e591f12be1bd619048d46bf285556f282d24e1
class StepAction(Action):
    """One step of work between an opening test and closing tests.

    The input is an Operator Context object of `InputType`. The tests are
    Checks. `operations` name what this step lets the operator do through the
    run while it is running; a domain write placed there is under the action.
    """

    InputType: ClassVar[type[OperatorContext]] = OperatorContext
    operations: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a3b2fd7f-0a5b-489a-90d7-f3ee98904bbc"),
                          name="Tarav.Actions.Step", workflow=ACTIONS_WORKFLOW_SHIP)

    def opening_checks(self, run: "ActionRun", context: OperatorContext) -> Iterable[Check]:
        return ()

    def closing_checks(self, run: "ActionRun", context: OperatorContext) -> Iterable[Check]:
        return ()

    def operate(self, name: str, run: "ActionRun", context: OperatorContext) -> dict:
        raise ActionError(f"{entity(type(self)).name} has no operation {name!r}")

    def output(self, run: "ActionRun", context: OperatorContext) -> dict:
        return {}


class ActionRun(TaravEntity, FileRecord):
    """One recorded instance of an Action: its intakes, sessions, tests, state and output."""

    class RecordInterface(TaravEntity.RecordInterface):
        action: str
        state: str
        exit: str | None
        started_at: str
        closed_at: str | None
        project: dict | None
        skill: dict | None
        intakes: list[dict]
        sessions: list[dict]
        opening: dict
        operations: list[dict]
        closings: list[dict]
        output: dict | None
        reason: str | None

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("9e21d29c-4dba-482d-b721-756d98e5a149"),
                          name="Tarav.Actions.Run", workflow=ACTIONS_WORKFLOW_SHIP)

    def __init__(self, id: Ship, data: dict) -> None:
        super().__init__(id)
        self.data = data

    @classmethod
    def _from_record(cls, data):
        values = data.model_dump(mode="json", exclude_unset=True)
        values.pop("type", None)
        values.pop("id")
        return cls(data.id, values)

    def _to_record(self):
        return {**super()._to_record(), **self.data}

    @property
    def state(self) -> str:
        return self.data["state"]

    @property
    def exit(self) -> str | None:
        return self.data["exit"]

    def reference(self) -> dict:
        """A typed reference to this run, for records made under it."""
        return {"type": RUN_REFERENCE_TYPE,
                "locator": {"run": str(self.id), "action": self.data["action"]}}

    class Records(TaravEntity.Records):
        def validate_record(self, value):
            data = super().validate_record(value)
            if data.state not in (RUNNING, CLOSED):
                raise ValueError("Unknown action run state")
            if (data.state == RUNNING) != (data.exit is None):
                raise ValueError("A running action run has no exit; a closed one has")
            if data.exit not in (None, EXIT_OK, EXIT_ERROR):
                raise ValueError("Unknown action run exit")
            return data

        def record_example(self) -> dict[str, object]:
            return {
                "type": entity(self._owner).name,
                "id": "4a9af366-b093-4ba0-aedd-6d71a3f2bbd0",
                "action": "Tarav.Actions.Step", "state": RUNNING, "exit": None,
                "started_at": "2026-10-09T00:00:00+00:00", "closed_at": None,
                "project": None, "skill": None, "intakes": [], "sessions": [],
                "opening": {"passed": True, "results": []}, "operations": [],
                "closings": [], "output": None, "reason": None,
            }


class ActionRunStore:
    """The Actions partition of the Record Registry: one record per run."""

    def __init__(self, registry: RecordRegistry | None = None) -> None:
        self.map = (registry or RecordRegistry()).for_workflow(ActionsWorkflow)

    def save(self, run: ActionRun, message: str) -> None:
        self.map.create()
        key = str(run.id)
        if self.map.path(key).is_file():
            self.map.replace(key, run)
        else:
            self.map.insert(key, run)
        self.map.commit((key,), message)

    def load(self, key: str) -> ActionRun:
        self.map.create()
        loaded = self.map.load(key)
        if not isinstance(loaded, ActionRun):
            raise TypeError(f"Record {key} is not an action run")
        return loaded

    # tarav.breadcrumb 83a58759d5febdca43d99b02dbd6392dd01a85053c7fe4f266a7af3bce768c5b
    def list(self, *, state: str | None = None, exit: str | None = None,
             project_root: str | None = None) -> list[ActionRun]:
        """Runs, newest first, optionally by state, exit or the Project they name."""
        self.map.create()
        runs = [self.load(name) for name in self.map.names()]
        selected = [
            run for run in runs
            if (state is None or run.state == state)
            and (exit is None or run.exit == exit)
            and (project_root is None
                 or (run.data["project"] or {}).get("root") == project_root)
        ]
        return sorted(selected, key=lambda run: run.data["started_at"], reverse=True)


_ACTION_TYPES: dict[str, type[Action]] = {}


def register_action(action_type: type[Action]) -> type[Action]:
    """Make an Action Type startable by name. Registration is explicit."""
    if not isinstance(action_type, type) or not issubclass(action_type, Action):
        raise TypeError("Expected an Action Type")
    name = entity(action_type).name
    if _ACTION_TYPES.get(name, action_type) is not action_type:
        raise ValueError(f"Another Action Type is registered as {name}")
    _ACTION_TYPES[name] = action_type
    return action_type


def action_types() -> dict[str, type[Action]]:
    return dict(_ACTION_TYPES)


def resolve_action(name: str) -> type[Action]:
    try:
        return _ACTION_TYPES[name]
    except KeyError:
        raise ActionError(f"No Action Type is registered as {name!r}") from None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session() -> dict | None:
    from tarav.l1.agent.current_session import CurrentSessionError, current_session

    try:
        found = current_session()
    except CurrentSessionError:
        return None
    return {"provider": found.provider, "session_id": found.session_id}


def _results(checks: Iterable[Check]) -> tuple[bool, list[dict]]:
    """Run tests; they pass when every one completed and none raised a failure."""
    passed, rows = True, []
    for check in checks:
        result = check.run()
        if not isinstance(result, CheckResult):
            raise TypeError("An action test must be a Check")
        pois = result.pois()
        if result.status != "completed" or any(
                isinstance(poi, CheckPOI) and poi.failure for poi in pois):
            passed = False
        rows.append({"check": entity(type(check)).name, "status": result.status,
                     "reason": result.reason,
                     "pois": [poi.as_dict(detail=True) if isinstance(poi, IdentifiedPOI)
                              else poi.as_dict() for poi in pois]})
    return passed, rows


# tarav.breadcrumb b28e1fd55c6190c26e3501773aa9f51ac39cc40e790570ff36a2e3e1e801685b
class StepRunner:
    """Start, operate and close runs of Step actions.

    Each command takes the operator's input from the Operator Context store
    and records what it took, so a run always knows what it was given.
    """

    def __init__(self, *, runs: ActionRunStore | None = None,
                 contexts: OperatorContextStore | None = None,
                 session: Callable[[], dict | None] = _session,
                 now: Callable[[], str] = _now) -> None:
        self.runs = runs if runs is not None else ActionRunStore()
        self.contexts = contexts if contexts is not None else OperatorContextStore()
        self._session = session
        self._now = now

    def _take(self, action: StepAction, run: ActionRun, context_id: str | None,
              purpose: str) -> Intake:
        if context_id is None:
            context_id = run.data["intakes"][-1]["context"]
        intake = self.contexts.take(context_id, expected=type(action).InputType)
        run.data["intakes"].append({"at": self._now(), "for": purpose, "context": intake.id,
                                    "hash": intake.hash, "record": intake.record})
        session = self._session()
        if session is not None and not any(
                (known["provider"], known["session_id"])
                == (session["provider"], session["session_id"])
                for known in run.data["sessions"]):
            run.data["sessions"].append({**session, "since": self._now()})
        return intake

    def _running(self, run_id: str) -> tuple[StepAction, ActionRun]:
        run = self.runs.load(run_id)
        if run.state != RUNNING:
            raise ActionError(f"Action run {run_id} is closed ({run.exit})")
        action_type = resolve_action(run.data["action"])
        if not issubclass(action_type, StepAction):
            raise ActionError(f"{run.data['action']} is not a Step action")
        return action_type(), run

    def start(self, action_type: type[StepAction], context_id: str) -> ActionRun:
        """Take the input and run the opening test. A failed opening is a closed run."""
        if not isinstance(action_type, type) or not issubclass(action_type, StepAction):
            raise ActionError("Only Step actions can be started")
        action = action_type()
        name = entity(action_type).name
        run = ActionRun(Ship(str(uuid4())), {
            "action": name, "state": RUNNING, "exit": None, "started_at": self._now(),
            "closed_at": None, "project": None,
            "skill": action_type.skill.to_json() if action_type.skill else None,
            "intakes": [], "sessions": [], "opening": {"passed": False, "results": []},
            "operations": [], "closings": [], "output": None, "reason": None,
        })
        intake = self._take(action, run, context_id, "start")
        run.data["project"] = intake.context.project
        passed, rows = _results(action.opening_checks(run, intake.context))
        run.data["opening"] = {"passed": passed, "results": rows}
        if not passed:
            run.data.update(state=CLOSED, exit=EXIT_ERROR, closed_at=self._now(),
                            reason="The opening test did not pass.")
        self.runs.save(run, f"Start {name} run {run.id}")
        return run

    def operate(self, run_id: str, name: str, context_id: str | None = None
                ) -> tuple[ActionRun, dict]:
        """Do one of the step's operations; only a running run has operations."""
        action, run = self._running(run_id)
        if name not in type(action).operations:
            raise ActionError(f"{run.data['action']} has no operation {name!r}")
        intake = self._take(action, run, context_id, f"operation {name}")
        result = action.operate(name, run, intake.context)
        run.data["operations"].append({"at": self._now(), "name": name, "result": result})
        self.runs.save(run, f"Operation {name} in run {run.id}")
        return run, result

    def close(self, run_id: str, context_id: str | None = None) -> ActionRun:
        """Run the closing tests. The run closes only when they pass."""
        action, run = self._running(run_id)
        intake = self._take(action, run, context_id, "close")
        passed, rows = _results(action.closing_checks(run, intake.context))
        run.data["closings"].append({"at": self._now(), "passed": passed, "results": rows})
        if passed:
            run.data.update(state=CLOSED, exit=EXIT_OK, closed_at=self._now(),
                            output=action.output(run, intake.context))
        self.runs.save(run, f"Close attempt on run {run.id}")
        return run

    def abort(self, run_id: str, reason: str) -> ActionRun:
        """Close a running run with an error, saying why."""
        if not isinstance(reason, str) or not reason.strip():
            raise ActionError("Aborting an action run needs a reason")
        _action, run = self._running(run_id)
        run.data.update(state=CLOSED, exit=EXIT_ERROR, closed_at=self._now(),
                        reason=reason.strip())
        self.runs.save(run, f"Abort run {run.id}")
        return run


ACTION_RECORD_TYPES = (ActionRun,)

__all__ = [
    "ACTIONS_WORKFLOW_SHIP", "ACTION_RECORD_TYPES", "Action", "ActionError", "ActionRun",
    "ActionRunStore", "ActionsWorkflow", "CLOSED", "EXIT_ERROR", "EXIT_OK",
    "RUNNING", "RUN_REFERENCE_TYPE", "SkillLink", "StepAction", "StepRunner",
    "action_types", "register_action", "resolve_action",
]
