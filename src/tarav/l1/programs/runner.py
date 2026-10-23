"""Checked movement between token-bound Action occurrences in a trusted graph."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import secrets
from uuid import uuid4

from filelock import FileLock

from tarav.l0._core.git_repository import git_result
from tarav.l0.kernel import Ship, entity
from tarav.l1.actions import ActionRun, ActionRunStore, LOOP, close_run, register_action, tape
from tarav.l1.checks import CheckSuite
from tarav.l1.records import RecordRegistry

from .runs import ActiveAction, ProgramRun
from .actions import ProgramExecutionAction, NodeAction, EdgeAction, Transition
from .workflow import ProgramsWorkflow


class ProgramError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _evidence(suite):
    return {"passed": suite.complete and suite.clean(), "complete": suite.complete, "results": [
        {"check": str(entity(type(r.check)).name), "status": r.status, "reason": r.reason,
         "pois": [p.records.to_record() for p in r.pois()]} for r in suite.results]}


def validate_definition(program):
    """Only inspect trusted declarations; never import a path from run data."""
    if not isinstance(program.initial, tuple) or not program.initial:
        raise ProgramError("Program.initial must be a nonempty tuple of NodeAction classes")
    if not isinstance(program.terminal, tuple):
        raise ProgramError("Program.terminal must be a tuple of NodeAction classes")
    if not isinstance(program.graph, tuple) or any(not isinstance(e, Transition) for e in program.graph):
        raise ProgramError("Program.graph must be a tuple of Transition declarations")
    definitions, keys = {}, set()

    def add(cls, base):
        if not isinstance(cls, type) or not issubclass(cls, base):
            raise ProgramError(f"Program graph role requires a {base.__name__} class")
        identity = entity(cls).id
        if identity in definitions and definitions[identity] is not cls:
            raise ProgramError("Two Action classes declare the same identity")
        definitions[identity] = cls
        register_action(cls)

    for cls in (*program.initial, *program.terminal):
        add(cls, NodeAction)
    for edge in program.graph:
        key = (entity(edge.source).id, entity(edge.action).id)
        if key in keys:
            raise ProgramError("A Program graph repeats a source/edge connection")
        keys.add(key)
        add(edge.source, NodeAction)
        add(edge.action, EdgeAction)
        add(edge.target, NodeAction)
    return definitions


# tarav.breadcrumb 45f4ac2834d5
# tarav.breadcrumb 6d1061989ec1
class ProgramRunner:
    def __init__(self, program, *, project=None, registry=None):
        from . import TaravProgram

        if not isinstance(program, type) or not issubclass(program, TaravProgram):
            raise ProgramError("A runner requires a trusted Program class")
        self.program = program
        self.definitions = validate_definition(program)
        self.registry = registry if registry is not None else RecordRegistry()
        self.store = self.registry.for_workflow(ProgramsWorkflow)
        self.actions = ActionRunStore(self.registry)
        self.project = deepcopy(project) if project is not None else None
        register_action(ProgramExecutionAction)

    def _lock(self):
        return FileLock(str(self.store.root) + ".programs.lock")

    def role(self, occurrence):
        cls = self.definitions.get(occurrence.action)
        if cls is None:
            raise ProgramError("The current Program no longer declares this Action")
        return "node" if issubclass(cls, NodeAction) else "edge"

    def load(self, identity):
        identity = str(Ship(identity))
        run = self.store.load(identity)
        if not isinstance(run, ProgramRun) or str(run.id) != identity:
            raise ProgramError("Program run identity or Type mismatch")
        if run.typed.program != entity(self.program).id:
            raise ProgramError("Run belongs to another Program class")
        if self.project is not None and run.typed.project != self.project:
            raise ProgramError("Run belongs to another Project")
        snapshots = [ActionRun.records.from_record(item) for item in run.typed.actions]
        ids = [str(item.id) for item in snapshots]
        active_ids = [str(item.id) for item in run.typed.active]
        if (len(ids) != len(set(ids)) or identity not in ids or len(active_ids) != len(set(active_ids))
                or bool(active_ids) != (run.typed.phase == "running")):
            raise ProgramError("Program Action occurrences are inconsistent")
        for occurrence in run.typed.active:
            role = self.role(occurrence)
            snapshot = next((item for item in snapshots if item.id == occurrence.id), None)
            if (snapshot is None or snapshot.state != "running" or snapshot.data["project"] != run.typed.project
                    or snapshot.data["action"] != str(entity(self.definitions[occurrence.action]).name)):
                raise ProgramError("Active Action snapshot is inconsistent")
            if role == "node" and (occurrence.source is not None or occurrence.target is not None):
                raise ProgramError("A node occurrence cannot carry an edge connection")
            if role == "edge" and not any(
                entity(e.source).id == occurrence.source and entity(e.action).id == occurrence.action
                and entity(e.target).id == occurrence.target for e in self.program.graph
            ):
                raise ProgramError("The active edge connection is no longer declared")
        return run

    def by_token(self, token):
        if not isinstance(token, str) or len(parts := token.split(".")) != 3:
            raise ProgramError("A current Program Action token is required")
        try:
            run = self.load(parts[0])
        except (OSError, ValueError) as exc:
            raise ProgramError(f"Program token cannot be resolved: {exc}") from exc
        occurrence = next((item for item in run.typed.active if str(item.id) == parts[1]), None)
        if occurrence is None or not token.isascii() or not secrets.compare_digest(token, occurrence.token):
            raise ProgramError("Stale or incorrect Program Action token")
        return run, occurrence

    def _save(self, run):
        run.typed.updated_at = _now()
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
            if retained.returncode or retained.stdout != self.actions.map.path(key).read_bytes():
                changed.append(key)
        self.actions.commit(changed, f"Project Program {run.id} actions")

    @staticmethod
    def _action(run, identity):
        return ActionRun.records.from_record(next(a for a in run.typed.actions if a["id"] == str(identity)))

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

    def _new(self, run, cls, *, source=None, target=None):
        identity = Ship(str(uuid4()))
        occurrence = ActiveAction(id=identity, action=entity(cls).id,
                                  token=f"{run.id}.{identity}.{secrets.token_hex(24)}",
                                  source=source, target=target)
        snapshot = self._open_action(str(identity), cls, run.typed.project,
                                     program_run=str(run.id), parent=str(run.id), role=self.role(occurrence),
                                     prompt=cls.prompt, source=str(source) if source else None,
                                     target=str(target) if target else None)
        self._keep_action(run, snapshot)
        return occurrence

    def _available(self, run, occurrence):
        if self.role(occurrence) != "node":
            return ()
        selected = tuple(self.program(id=run.id).available(run, occurrence))
        if any(edge not in self.program.graph or entity(edge.source).id != occurrence.action for edge in selected):
            raise ProgramError("Availability can only select declared outgoing connections")
        if len(selected) != len(set(selected)):
            raise ProgramError("Availability repeats a connection")
        return selected

    def frame(self, run):
        return {"run": str(run.id), "program": str(run.typed.program), "project": run.typed.project,
                "phase": run.typed.phase, "active": [
                    {**item.model_dump(mode="json"), "role": self.role(item),
                     "name": str(entity(self.definitions[item.action]).name),
                     "record": self._action(run, item.id).records.to_record(),
                     "available": [{"action": str(entity(e.action).id), "name": str(entity(e.action).name),
                                    "target": str(entity(e.target).id), "prompt": e.action.prompt}
                                   for e in self._available(run, item)]} for item in run.typed.active],
                "data": deepcopy(run.typed.data)}

    def _suite(self, run, occurrence, operation):
        return CheckSuite.of(self.program(id=run.id).checks(run, occurrence, operation=operation))

    def action_checks(self, token):
        run, occurrence = self.by_token(token)
        return self._suite(run, occurrence, "status")

    def context(self, occurrence, operation):
        return {"occurrence": str(occurrence.id), "action": str(occurrence.action),
                "role": self.role(occurrence), "operation": operation}

    def status(self, token):
        run, occurrence = self.by_token(token)
        checks = self.action_checks(token).run()
        self.by_token(token)
        return {**self.frame(run), "context": self.context(occurrence, "status"),
                "action_checks": _evidence(checks), "coherent": checks.complete and checks.clean()}

    def _gates(self, contexts):
        suites = [(occ, op, self._suite(run, occ, op)) for run, occ, op in contexts]
        whole = CheckSuite([suite for _, _, suite in suites]).run()
        return {"passed": whole.complete and whole.clean(), "contexts": [
            {**self.context(occ, op), **_evidence(suite)} for occ, op, suite in suites]}

    def start(self, *, data=None):
        if (not isinstance(self.project, dict) or set(self.project) != {"id", "name", "root"}
                or not isinstance(self.project["name"], str) or not self.project["name"].strip()
                or not isinstance(self.project["root"], str)):
            raise ProgramError("Start requires a Project descriptor with id, name and root")
        Ship(self.project["id"])
        if not Path(self.project["root"]).is_absolute():
            raise ProgramError("A Program run requires an absolute Project root")
        identity, at = Ship(str(uuid4())), _now()
        run = ProgramRun.records.from_record({
            "type": str(entity(ProgramRun).name), "id": str(identity), "program": str(entity(self.program).id),
            "project": self.project, "active": [], "phase": "running", "data": {} if data is None else data,
            "actions": [], "history": [], "created_at": at, "updated_at": at})
        self._keep_action(run, self._open_action(str(identity), ProgramExecutionAction, self.project,
                                               program=str(entity(self.program).id)))
        run.typed.active = [self._new(run, cls) for cls in self.program.initial]
        evidence = self._gates([(run, item, "enter") for item in run.typed.active])
        if not evidence["passed"]:
            raise ProgramError(f"Initial Action entry checks are not fulfilled: {evidence}")
        for item in run.typed.active:
            self._available(run, item)
        run.typed.history.append({"kind": "started", "at": at, "checks": evidence,
                                  "active": [item.model_dump(mode="json") for item in run.typed.active]})
        self.store.create()
        with self._lock():
            self._save(run)
        return self.frame(run)

    def choose(self, token, action):
        with self._lock():
            run, occurrence = self.by_token(token)
            if self.role(occurrence) != "node":
                raise ProgramError("Choose an edge only from a current NodeAction token")
            choices = [edge for edge in self._available(run, occurrence)
                       if action in (str(entity(edge.action).id), str(entity(edge.action).name))]
            if len(choices) != 1:
                raise ProgramError("Action is not an available outgoing connection")
            edge = choices[0]
            return self._move(run, occurrence, edge.action,
                              source=entity(edge.source).id, target=entity(edge.target).id)

    def step(self, token, *, data=None):
        with self._lock():
            run, occurrence = self.by_token(token)
            if data is not None:
                if not isinstance(data, dict):
                    raise ProgramError("Program input data must be a JSON object")
                values = run.records.to_record()
                values["data"].update(data)
                run = ProgramRun.records.from_record(values)
            if self.role(occurrence) == "node":
                if occurrence.action not in {entity(cls).id for cls in self.program.terminal}:
                    raise ProgramError("Choose an EdgeAction, or complete a declared terminal NodeAction")
                return self._move(run, occurrence, None)
            return self._move(run, occurrence, self.definitions[occurrence.target])

    def _move(self, run, occurrence, cls, *, source=None, target=None):
        candidate = ProgramRun.records.from_record(run.records.to_record())
        entered = self._new(candidate, cls, source=source, target=target) if cls else None
        candidate.typed.active = [entered if item.id == occurrence.id else item
                                  for item in candidate.typed.active if entered or item.id != occurrence.id]
        contexts = [(run, occurrence, "complete")]
        if entered:
            contexts.append((candidate, entered, "enter"))
            self._available(candidate, entered)
        evidence = self._gates(contexts)
        snapshot = self._action(run, occurrence.id)
        tape.attempt(snapshot, "completed", by=LOOP, at=_now(), passed=evidence["passed"],
                     results=evidence["contexts"])
        if evidence["passed"]:
            close_run(self.definitions[occurrence.action](), snapshot, "completed", by=LOOP, at=_now())
            run = candidate
            if not run.typed.active:
                run.typed.phase = "completed"
                root = self._action(run, run.id)
                close_run(ProgramExecutionAction(), root, "finished", by=LOOP, at=_now())
                self._keep_action(run, root)
        self._keep_action(run, snapshot)
        run.typed.history.append({"kind": "moved" if evidence["passed"] else "blocked", "at": _now(),
                                  "from": str(occurrence.id), "to": str(entered.id) if entered and evidence["passed"] else None,
                                  "checks": evidence})
        self._save(run)
        return {**self.frame(run), "advanced": evidence["passed"], "checks": evidence}

    def recover(self, identity):
        with self._lock():
            run = self.load(identity)
            self._project_actions(run)
        return self.frame(run)
