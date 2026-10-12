"""Typed Actions and their recorded runs.

An Action Type is a definition and an ActionRun is one instance of it, as a
program and a process are. The base Action prescribes almost nothing. A
StepAction closes a piece of an operator's work into one step: an opening
test, the work, and one or more exits, each with its own tests. Closing a
run leaves a record whose Type the exit names.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar
from uuid import uuid4

from tarav.l0.kernel import (
    FileRecord, Ship, TaravClass, TaravEntity, TaravType, TypeShip, entity,
)
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite
from tarav.l1.poi import IdentifiedPOI
from tarav.l1.operator_context import Intake, OperatorContext, OperatorContextStore
from tarav.l1.records import RecordRegistry

from .workflow import ACTIONS_WORKFLOW_SHIP, ActionsWorkflow

RUNNING, CLOSED = "running", "closed"
EXIT_ERROR = "error"
OPERATOR, LOOP, PROJECT = "operator", "loop", "project"
OPEN = "open"
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


# tarav.breadcrumb b8628a0e0a514433769345b9a4179f65f995d09f4057318e3af577edafd1bfbd
class Closing(TaravEntity, FileRecord):
    """The record a closing path leaves on its run: which exit, when, and taken by whom.

    A subtype adds what its path knows. The run keeps the record of its
    current closing; earlier ones are in the registry's Git history.
    """

    class RecordInterface(TaravEntity.RecordInterface):
        run: str
        exit: str
        at: str
        by: str

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3c1e8a54-7b2d-4f96-a0c5-e9d6b4f17a23"),
                          name="Tarav.Actions.Closing", workflow=ACTIONS_WORKFLOW_SHIP)

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

    @classmethod
    def fields(cls, action: "StepAction", run: "ActionRun",
               context: OperatorContext | None) -> dict:
        """What this Type adds to the base record when its path is taken."""
        return {}

    @classmethod
    def reopens(cls, record: dict | None, poi: object) -> bool:
        """Does raising the action's POI again reopen an action closed this way?"""
        return False

    class Records(TaravEntity.Records):
        def record_example(self) -> dict[str, object]:
            return {"type": entity(self._owner).name,
                    "id": "8d5b2f70-4e19-4c3a-b6a8-1f7c9e0d3b52",
                    "run": "4a9af366-b093-4ba0-aedd-6d71a3f2bbd0", "exit": "done",
                    "at": "2026-10-11T00:00:00+00:00", "by": OPERATOR}


# tarav.breadcrumb 172bd4f5f4e23e808f5494a5f027e73f698c95cde8cb01634728d6d12ff891df
# tarav.breadcrumb 617b0622a666a1e907b34944e42378b34d9fdff085f1af740f310d6cbe468309
@dataclass(frozen=True)
class Exit:
    """One way a step can close: who may take it, and the Type of the record it leaves.

    An operator takes an exit with a command, the loop when the exit's tests
    pass, and the action's Project when its checks no longer produce what the
    action follows.
    """

    name: str
    by: tuple[str, ...] = (OPERATOR,)
    closing: type[Closing] = Closing

    def __post_init__(self) -> None:
        if not self.name or self.name == EXIT_ERROR:
            raise ValueError("An exit needs a name other than 'error'")
        if not self.by or set(self.by) - {OPERATOR, LOOP, PROJECT}:
            raise ValueError("An exit is taken by an operator, the loop or a Project")
        if not isinstance(self.closing, type) or not issubclass(self.closing, Closing):
            raise TypeError("An exit names a Closing Type")


@dataclass
class ChecksUpdate:
    """A suite of a Project's checks that ran, as it is handed to that Project's actions.

    `memo` is for an Action Type to keep what it worked out from the results,
    so it does that once for all its actions. `signals` collects the POIs an
    action raises about what it did.
    """

    checks: CheckSuite
    project: dict
    at: str
    signals: list = field(default_factory=list)
    memo: dict = field(default_factory=dict)


# tarav.breadcrumb 6d5ab498c22e8990eeb3104cce5e7dca21024f8aa62fc4e951e0c9f14056ff20
class Action(TaravType):
    """Root of every Action Type. It prescribes only the link to its instructions."""

    skill: ClassVar[SkillLink | None] = None

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("5b7deb17-f328-4470-87ea-a17ef370e92f"),
                          name="Tarav.Actions.Action", workflow=ACTIONS_WORKFLOW_SHIP)

    @classmethod
    def on_checks(cls, run: "ActionRun", update: ChecksUpdate) -> str | None:
        """What one registered action does with a run of its Project's checks.

        It may ignore the results, change its status or close itself. It
        changes `run` in place and names the change; None says nothing changed.
        """
        return None


# tarav.breadcrumb 9653fbc6c09471fe85885cd12a4a103d86fba2aba9efab0ac507c2dd94cd3942
# tarav.breadcrumb 211a93166d7c38a5177f8e8030e591f12be1bd619048d46bf285556f282d24e1
class StepAction(Action):
    """One step of work between an opening test and its exits.

    The input is an Operator Context object of `InputType`. The tests are
    Checks. `operations` name what this step lets the operator do through the
    run while it is running; a domain write placed there is under the action.
    `exits` are the ways the step can close, as a program has several exit
    paths; each says who may take it.
    """

    InputType: ClassVar[type[OperatorContext]] = OperatorContext
    operations: ClassVar[tuple[str, ...]] = ()
    exits: ClassVar[tuple[Exit, ...]] = (Exit("done"),)

    @classmethod
    def exit_named(cls, name: str) -> Exit:
        for candidate in cls.exits:
            if candidate.name == name:
                return candidate
        raise ActionError(f"{entity(cls).name} has no exit {name!r}")

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a3b2fd7f-0a5b-489a-90d7-f3ee98904bbc"),
                          name="Tarav.Actions.Step", workflow=ACTIONS_WORKFLOW_SHIP)

    def opening_checks(self, run: "ActionRun", context: OperatorContext) -> Iterable[Check]:
        return ()

    def exit_checks(self, name: str, run: "ActionRun",
                    context: OperatorContext | None) -> Iterable[Check]:
        """The tests of one exit. The loop asks without an operator's input."""
        return ()

    def operate(self, name: str, run: "ActionRun", context: OperatorContext) -> dict:
        raise ActionError(f"{entity(type(self)).name} has no operation {name!r}")

    def output(self, name: str, run: "ActionRun", context: OperatorContext | None) -> dict:
        """What the run keeps about the exit it closed by."""
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
        opened_at: str
        event: dict | None = None
        closing: dict | None = None
        situation: dict | None = None

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

    def closing(self) -> Closing | None:
        """The record of how this run closed, as an object of its Type."""
        record = self.data.get("closing")
        if record is None:
            return None
        action_type = resolve_action(self.data["action"])
        return action_type.exit_named(record["exit"]).closing.records.from_record(record)

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
            return data

        def record_example(self) -> dict[str, object]:
            return {
                "type": entity(self._owner).name,
                "id": "4a9af366-b093-4ba0-aedd-6d71a3f2bbd0",
                "action": "Tarav.Actions.Step", "state": RUNNING, "exit": None,
                "started_at": "2026-10-09T00:00:00+00:00",
                "opened_at": "2026-10-09T00:00:00+00:00", "closed_at": None,
                "project": None, "skill": None, "intakes": [], "sessions": [],
                "opening": {"passed": True, "results": []}, "operations": [],
                "closings": [], "output": None, "reason": None,
            }


class ActionRunStore:
    """The Actions partition of the Record Registry: one record per run."""

    def __init__(self, registry: RecordRegistry | None = None) -> None:
        self.map = (registry or RecordRegistry()).for_workflow(ActionsWorkflow)

    def write(self, run: ActionRun) -> str | None:
        """Write one run without committing; `commit` records a batch of them.

        Returns None when the stored record already says the same.
        """
        self.map.create()
        key = str(run.id)
        if self.map.path(key).is_file():
            if self.map.load(key).records.to_record() == run.records.to_record():
                return None
            self.map.replace(key, run)
        else:
            self.map.insert(key, run)
        return key

    def commit(self, keys: Iterable[str | None], message: str) -> None:
        keys = tuple(dict.fromkeys(key for key in keys if key is not None))
        if keys:
            self.map.commit(keys, message)

    def save(self, run: ActionRun, message: str) -> None:
        self.commit((self.write(run),), message)

    def exists(self) -> bool:
        """Has anything ever been written here? Reading never creates the registry."""
        return self.map.marker.is_file()

    def find(self, key: str) -> ActionRun | None:
        if not self.exists():
            return None
        return self.load(key) if self.map.path(key).is_file() else None

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
        if not self.exists():
            return []
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


def close_run(action: StepAction, run: ActionRun, exit: str, *, by: str, at: str,
              context: OperatorContext | None = None, extra: dict | None = None) -> dict:
    """Close a run through one exit and leave that exit's closing record on it."""
    closing_type = type(action).exit_named(exit).closing
    record = {"type": entity(closing_type).name, "id": str(uuid4()), "run": str(run.id),
              "exit": exit, "at": at, "by": by,
              **closing_type.fields(action, run, context), **(extra or {})}
    closing_type.records.from_record(record)
    run.data.update(state=CLOSED, exit=exit, closed_at=at,
                    output=action.output(exit, run, context), closing=record)
    return record


# tarav.breadcrumb 62e07db35eaffe474b99d33dde9b515e77434163e739c5cd378ad6848eca3465
def axes(run: ActionRun) -> dict[str, str | None]:
    """The status of a run as separate axes: the situation, the action, the closing.

    `situation` is what the last run of the Project's checks says, for a run
    that follows a POI: present, absent, or unknown because the suite above
    it did not run or a check under it failed. `closing` is the exit the run closed by; its record
    has the detail.
    """
    return {"situation": (run.data.get("situation") or {}).get("state"),
            "action": OPEN if run.state == RUNNING else CLOSED,
            "closing": run.exit}


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
            if not run.data["intakes"]:
                raise ActionError("This run has no operator input yet; name one with --context")
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
            "opened_at": self._now(), "closed_at": None, "project": None,
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

    def close(self, run_id: str, context_id: str | None = None, *,
              exit: str | None = None) -> ActionRun:
        """Take one exit as an operator. The run closes only when that exit's tests pass."""
        action, run = self._running(run_id)
        offered = [item for item in type(action).exits if OPERATOR in item.by]
        if exit is None:
            if len(offered) != 1:
                raise ActionError("This action has several exits; name one: "
                                  + ", ".join(item.name for item in offered))
            exit = offered[0].name
        if OPERATOR not in type(action).exit_named(exit).by:
            raise ActionError(f"Exit {exit!r} is not taken by an operator")
        intake = self._take(action, run, context_id, f"exit {exit}")
        passed, rows = _results(action.exit_checks(exit, run, intake.context))
        run.data["closings"].append({"at": self._now(), "exit": exit, "by": OPERATOR,
                                     "passed": passed, "results": rows})
        if passed:
            close_run(action, run, exit, by=OPERATOR, at=self._now(), context=intake.context)
        self.runs.save(run, f"Exit {exit} attempted on run {run.id}")
        return run

    # tarav.breadcrumb ba6c7adbc1a559e7a2e2c49ed9032edd4edf4ae1565ab448b5bc9018932e2496
    def sweep(self) -> list[ActionRun]:
        """Ask every running run whether an exit the loop may take is met; close those.

        An exit with no tests for the loop cannot close itself and is left.
        """
        closed, keys = [], []
        for run in self.runs.list(state=RUNNING):
            action_type = resolve_action(run.data["action"])
            if not issubclass(action_type, StepAction):
                continue
            action = action_type()
            for item in action_type.exits:
                if LOOP not in item.by:
                    continue
                checks = tuple(action.exit_checks(item.name, run, None))
                if not checks:
                    continue
                passed, rows = _results(checks)
                if not passed:
                    continue
                run.data["closings"].append({"at": self._now(), "exit": item.name, "by": LOOP,
                                             "passed": True, "results": rows})
                close_run(action, run, item.name, by=LOOP, at=self._now())
                keys.append(self.runs.write(run))
                closed.append(run)
                break
        self.runs.commit(keys, f"Sweep closed {len(keys)} action run(s)")
        return closed

    def abort(self, run_id: str, reason: str) -> ActionRun:
        """Close a running run with an error, saying why."""
        if not isinstance(reason, str) or not reason.strip():
            raise ActionError("Aborting an action run needs a reason")
        _action, run = self._running(run_id)
        run.data.update(state=CLOSED, exit=EXIT_ERROR, closed_at=self._now(),
                        reason=reason.strip())
        self.runs.save(run, f"Abort run {run.id}")
        return run


ACTION_RECORD_TYPES = (ActionRun, Closing)

__all__ = [
    "ACTIONS_WORKFLOW_SHIP", "ACTION_RECORD_TYPES", "Action", "ActionError", "ActionRun",
    "ActionRunStore", "ActionsWorkflow", "CLOSED", "ChecksUpdate", "Closing", "EXIT_ERROR",
    "Exit", "LOOP", "OPEN", "OPERATOR", "PROJECT", "RUNNING", "RUN_REFERENCE_TYPE", "SkillLink", "StepAction",
    "StepRunner", "action_types", "axes", "close_run", "register_action", "resolve_action",
]
