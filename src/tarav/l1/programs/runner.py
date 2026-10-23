"""Checked, token-bound advancement over explicitly registered Program classes."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import secrets
from uuid import uuid4

from filelock import FileLock

from tarav.l0._core.git_repository import git_result
from tarav.l0.kernel import Ship, entity
from tarav.l1.actions import ActionRun, ActionRunStore, LOOP, close_run, register_action, tape
from tarav.l1.records import RecordRegistry

from .runs import ProgramRun
from .states import ProgramExecutionAction, State, Transition
from .workflow import ProgramsWorkflow


class ProgramError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _evidence(suite):
    return {"passed": suite.clean(), "results": [
        {"check": str(entity(type(r.check)).name), "status": r.status, "reason": r.reason,
         "pois": [p.records.to_record() for p in r.pois()]} for r in suite.results]}


def validate_definition(program):
    """Inspect only trusted class declarations, never import a path from run data."""
    if not isinstance(program.initial, type) or not issubclass(program.initial, State):
        raise ProgramError("Program.initial must be a State class")
    if not isinstance(program.graph, tuple) or any(not isinstance(e, Transition) for e in program.graph):
        raise ProgramError("Program.graph must be a tuple of Transition declarations")
    states = {entity(program.initial).id: program.initial}
    keys = set()
    for edge in program.graph:
        key = (entity(edge.source).id, entity(edge.action).id)
        if key in keys:
            raise ProgramError("A Program graph repeats a source/action connection")
        keys.add(key)
        for state in (edge.source, edge.action.State):
            identity = entity(state).id
            if identity in states and states[identity] is not state:
                raise ProgramError("Two State classes declare the same identity")
            states[identity] = state
        register_action(edge.action)
    for state in program.terminal:
        if not isinstance(state, type) or not issubclass(state, State):
            raise ProgramError("Program.terminal must contain State classes")
        identity = entity(state).id
        if identity in states and states[identity] is not state:
            raise ProgramError("Two State classes declare the same identity")
        states[identity] = state
    return states


# tarav.breadcrumb e1d9a6eaa3a0
class ProgramRunner:
    def __init__(self, program, *, project=None, registry=None):
        from . import TaravProgram

        if not isinstance(program, type) or not issubclass(program, TaravProgram):
            raise ProgramError("A runner requires a trusted Program class")
        self.program = program
        self.states = validate_definition(program)
        self.registry = registry if registry is not None else RecordRegistry()
        self.store = self.registry.for_workflow(ProgramsWorkflow)
        self.actions = ActionRunStore(self.registry)
        self.project = deepcopy(project) if project is not None else None
        register_action(ProgramExecutionAction)

    def _lock(self):
        return FileLock(str(self.store.root) + ".programs.lock")

    def load(self, identity):
        identity = str(Ship(identity))
        run = self.store.load(identity)
        if not isinstance(run, ProgramRun) or str(run.id) != identity:
            raise ProgramError("Program run identity or Type mismatch")
        if run.typed.program != entity(self.program).id:
            raise ProgramError("Run belongs to another Program class")
        if self.project is not None and run.typed.project != self.project:
            raise ProgramError("Run belongs to another Project")
        if run.typed.state not in self.states:
            raise ProgramError("The current Program definition no longer declares this State")
        ids = [item["id"] for item in run.typed.actions]
        if len(ids) != len(set(ids)) or identity not in ids or (run.typed.pending and run.typed.pending not in ids):
            raise ProgramError("Program action snapshots are inconsistent")
        for item in run.typed.actions:
            ActionRun.records.from_record(item)
        return run

    def by_token(self, token):
        if not isinstance(token, str) or "." not in token:
            raise ProgramError("A current Program state token is required")
        try:
            run = self.load(token.split(".", 1)[0])
        except (OSError, ValueError) as exc:
            raise ProgramError(f"Program token cannot be resolved: {exc}") from exc
        if not secrets.compare_digest(token, run.typed.token):
            raise ProgramError("Stale or incorrect Program state token")
        return run

    @staticmethod
    def _token(identity):
        return str(identity) + "." + secrets.token_hex(24)

    def _save(self, run):
        run.typed.updated_at = _now()
        # This Record is authoritative. Projections can be recovered explicitly.
        if self.store.path(str(run.id)).exists():
            self.store.replace(str(run.id), run)
        else:
            self.store.insert(str(run.id), run)
        self.store.commit((str(run.id),), f"Program {run.id}: {run.typed.history[-1]['kind']}")
        self._project_actions(run)

    def _project_actions(self, run):
        keys = [self.actions.write(ActionRun.records.from_record(item)) for item in run.typed.actions]
        changed = []
        for key in (key for key in keys if key is not None):
            retained = git_result(self.actions.map.root, "show", f"HEAD:records/{key}.json")
            # Recovery can restore bytes already in HEAD, requiring no new commit.
            if retained.returncode or retained.stdout != self.actions.map.path(key).read_bytes():
                changed.append(key)
        self.actions.commit(changed, f"Project Program {run.id} actions")

    @staticmethod
    def _action(run, identity):
        return ActionRun.records.from_record(next(a for a in run.typed.actions if a["id"] == identity))

    @staticmethod
    def _keep_action(run, action):
        record = action.records.to_record()
        for index, item in enumerate(run.typed.actions):
            if item["id"] == record["id"]:
                run.typed.actions[index] = record
                return
        run.typed.actions.append(record)

    @staticmethod
    def _open_action(identity, action, project, **opening):
        return ActionRun(Ship(identity), {
            "action": str(entity(action).name), "project": deepcopy(project),
            "skill": action.skill.to_json() if action.skill else None,
            "intakes": [], "sessions": [], "opening": {"passed": True, "results": [], **opening},
            "operations": [], "output": None, "reason": None,
            "tape": [{"type": tape.OPENED, "at": _now()}]})

    def _available(self, run):
        if run.typed.phase == "completed" or run.typed.pending:
            return ()
        selected = tuple(self.program(id=run.id).available(run))
        if any(edge not in self.program.graph or entity(edge.source).id != run.typed.state for edge in selected):
            raise ProgramError("Availability can only select declared outgoing connections")
        if len(selected) != len(set(selected)):
            raise ProgramError("Availability repeats a connection")
        return selected

    def frame(self, run):
        pending = self._action(run, run.typed.pending) if run.typed.pending else None
        return {"run": str(run.id), "program": str(run.typed.program), "project": run.typed.project,
                "state": str(run.typed.state), "arrival": run.typed.arrival, "phase": run.typed.phase,
                "token": run.typed.token, "pending": pending.records.to_record() if pending else None,
                "available": [{"action": str(entity(e.action).id), "name": str(entity(e.action).name),
                               "target": str(entity(e.action.State).id), "prompt": e.action.prompt}
                              for e in self._available(run)], "data": deepcopy(run.typed.data)}

    def state_checks(self, token):
        run = self.by_token(token)
        return self.states[run.typed.state](run).checks.suite()

    def status(self, token):
        run = self.by_token(token)
        checks = self.state_checks(token).run()
        self.by_token(token)  # a concurrent arrival invalidates this contextual read
        return {**self.frame(run), "state_checks": _evidence(checks), "coherent": checks.clean()}

    def start(self, *, data=None):
        if (not isinstance(self.project, dict) or set(self.project) != {"id", "name", "root"}
                or not isinstance(self.project["name"], str) or not self.project["name"].strip()
                or not isinstance(self.project["root"], str)):
            raise ProgramError("Start requires a Project descriptor with id, name and root")
        Ship(self.project["id"])
        if not Path(self.project["root"]).is_absolute():
            raise ProgramError("A Program run requires an absolute Project root")
        identity = Ship(str(uuid4()))
        at = _now()
        run = ProgramRun.records.from_record({
            "type": str(entity(ProgramRun).name), "id": str(identity), "program": str(entity(self.program).id),
            "project": self.project, "state": str(entity(self.program.initial).id), "arrival": 0,
            "token": self._token(identity), "phase": "running", "pending": None,
            "data": {} if data is None else data, "actions": [], "history": [], "created_at": at, "updated_at": at})
        checks = self.program.initial(run).checks.suite().run()
        if not checks.clean():
            raise ProgramError(f"Initial State conditions are not fulfilled: {_evidence(checks)}")
        action = self._open_action(str(identity), ProgramExecutionAction, self.project,
                                   program=str(entity(self.program).id))
        self._keep_action(run, action)
        run.typed.history.append({"kind": "started", "at": at, "state": str(run.typed.state),
                                  "arrival": 0, "checks": _evidence(checks)})
        self._finish_if_terminal(run)
        self._available(run)  # validate author-supplied availability before creating storage
        self.store.create()
        with self._lock():
            self._save(run)
        return self.frame(run)

    def choose(self, token, action):
        with self._lock():
            run = self.by_token(token)
            if run.typed.pending or run.typed.phase == "completed":
                raise ProgramError("The Program has a pending action or is completed")
            if not self.state_checks(token).run().clean():
                raise ProgramError("The current State is incoherent; restore its conditions before choosing")
            choices = [edge for edge in self._available(run)
                       if action in (str(entity(edge.action).id), str(entity(edge.action).name))]
            if len(choices) != 1:
                raise ProgramError("Action is not an available outgoing connection")
            edge = choices[0]
            child = self._open_action(str(uuid4()), edge.action, run.typed.project,
                                      program_run=str(run.id), parent=str(run.id),
                                      source=str(run.typed.state), target=str(entity(edge.action.State).id),
                                      prompt=edge.action.prompt)
            run.typed.pending = str(child.id)
            self._keep_action(run, child)
            run.typed.history.append({"kind": "selected", "at": _now(), "action": str(child.id),
                                      "action_type": str(entity(edge.action).id)})
            self._save(run)
        return self.frame(run)

    # tarav.breadcrumb 3f01ad3bca9c
    def step(self, token, *, data=None):
        with self._lock():
            run = self.by_token(token)
            if not run.typed.pending or run.typed.phase != "running":
                raise ProgramError("Choose a StateAction before advancing")
            child = self._action(run, run.typed.pending)
            edges = [e for e in self.program.graph if entity(e.source).id == run.typed.state
                     and str(entity(e.action).name) == child.data["action"]]
            if len(edges) != 1:
                raise ProgramError("The pending action is no longer declared at this State")
            edge = edges[0]
            if data is not None:
                if not isinstance(data, dict):
                    raise ProgramError("Program input data must be a JSON object")
                candidate = run.records.to_record()
                candidate["data"].update(data)
                run = ProgramRun.records.from_record(candidate)
            # Prerequisites see the source context; destination conditions see the candidate arrival.
            candidate = ProgramRun.records.from_record(run.records.to_record())
            candidate.typed.state = entity(edge.action.State).id
            candidate.typed.arrival += 1
            checks = edge.action().checks(run, destination=candidate).run()
            evidence = _evidence(checks)
            passed = checks.clean()
            tape.attempt(child, "reached", by=LOOP, at=_now(), passed=passed, results=evidence["results"])
            run.typed.history.append({"kind": "checked", "at": _now(), "action": str(child.id),
                                      "passed": passed, "checks": evidence})
            if passed:
                candidate.typed.history = run.typed.history
                run = candidate
                close_run(edge.action(), child, "reached", by=LOOP, at=_now(), extra={
                    "program_run": str(run.id), "state": str(run.typed.state), "arrival": run.typed.arrival})
                run.typed.pending = None
                run.typed.token = self._token(run.id)
                run.typed.history.append({"kind": "arrived", "at": _now(), "state": str(run.typed.state),
                                          "arrival": run.typed.arrival, "action": str(child.id)})
                self._finish_if_terminal(run)
            self._keep_action(run, child)
            self._save(run)
        return {**self.frame(run), "advanced": passed, "checks": evidence}

    def _finish_if_terminal(self, run):
        if run.typed.state in {entity(state).id for state in self.program.terminal}:
            run.typed.phase = "completed"
            root = self._action(run, str(run.id))
            close_run(ProgramExecutionAction(), root, "finished", by=LOOP, at=_now())
            self._keep_action(run, root)

    def recover(self, identity):
        """Explicitly replay Action projections after an interrupted multi-store write."""
        with self._lock():
            run = self.load(identity)
            self._project_actions(run)
        return self.frame(run)
