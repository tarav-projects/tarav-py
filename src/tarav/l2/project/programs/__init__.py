"""Project ownership, trusted Program selection and contextual status integration."""

from tarav.l0.kernel import NamespaceBase, Ship, TaravClass, TypeShip, entity
from tarav.l1.checks import CheckPOI, CheckResult, CheckSuite, SituationCheck, SuiteCheckpoint
from tarav.l1.programs import ProgramError, ProgramRun, TaravProgram
from tarav.l1.programs.runner import _evidence, validate_definition
from tarav.l1.programs.workflow import PROGRAMS_WORKFLOW_SHIP
from tarav.l1.programs.workflow import ProgramsWorkflow
from tarav.l1.project.status import ProjectStatus


class ProjectProgram(TaravProgram):
    """An extensible specialization for Programs declared in Project code."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("e8f21343-b1fb-4831-9fdb-20dd221ab15d"),
            name="Tarav.Project.Program",
            workflow=PROGRAMS_WORKFLOW_SHIP,
        )


# tarav.breadcrumb 8529428be02a
# tarav.breadcrumb a79131221bd8
class ProgramsManager(NamespaceBase):
    @property
    def owner(self):
        return self.obj.actions.project

    @property
    def store(self):
        return self.obj.records.registry.for_workflow(ProgramsWorkflow)

    def definitions(self):
        return tuple(cls for cls in self.obj.types.all()
                     if issubclass(cls, TaravProgram) and cls not in (TaravProgram, ProjectProgram))

    def prepare(self):
        for cls in self.definitions():
            validate_definition(cls)

    def resolve(self, identity):
        matches = [cls for cls in self.definitions()
                   if identity in (str(entity(cls).id), str(entity(cls).name))]
        if len(matches) != 1:
            raise ProgramError("Program must name one registered class owned by this Project")
        return matches[0]

    def runner(self, identity):
        return self.resolve(identity).runner(project=self.owner, registry=self.obj.records.registry)

    def for_run(self, identity):
        run = self.store.load(str(Ship(identity)))
        if not isinstance(run, ProgramRun) or run.typed.project != self.owner:
            raise ProgramError("Program run does not belong to this Project")
        return self.runner(str(run.typed.program))

    def for_token(self, token):
        if not isinstance(token, str) or len(token.split(".")) != 3:
            raise ProgramError("A current Program Action token is required")
        runner = self.for_run(token.split(".", 1)[0])
        runner.by_token(token)
        return runner

    def runs(self):
        if not self.store.marker.exists():
            return ()
        return tuple(run for name in self.store.names()
                     if isinstance(run := self.store.load(name), ProgramRun) and run.typed.project == self.owner)

    def suite(self, token=None):
        # Validate explicit context before the caller starts its normal status work.
        runner = self.for_token(token) if token is not None else None
        return ProgramProjectSuite(self, runner=runner, token=token)

    def status(self, token, *, select=None, on_result=None):
        contextual = self.suite(token)
        checks = CheckSuite([self.obj.checks.own(), contextual], name=self.obj.name).run(
            select=select, on_result=on_result)
        return ProjectStatus(self.obj, checks, self.obj.actions.update(checks),
                             tuple(member.actions.status(select=select, on_result=on_result)
                                   for member in self.obj.members()))


class ActionIncoherent(CheckPOI):
    """The selected Action's Program-defined status checks report a finding."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("ee00f95c-5b18-4523-b3a5-7e8087c253b9"),
                          name="Tarav.Programs.ActionIncoherent.POI", workflow=PROGRAMS_WORKFLOW_SHIP)


# tarav.breadcrumb 1faa49b6ceb8
# tarav.breadcrumb 25a1430500d4
class ProgramCoherenceCheck(SituationCheck):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("05b6ae65-3f3a-4a9a-93e6-3d35bc012263"),
                          name="Tarav.Programs.Coherence.Check", workflow=PROGRAMS_WORKFLOW_SHIP)

    def __init__(self, runner, token, occurrence_id, run_id=None):
        run = runner.by_token(token)[0] if token is not None else runner.load(run_id)
        super().__init__(situation={"program_run": str(run.id), "action_run": occurrence_id})
        self.occurrence_id, self.run_id = occurrence_id, str(run.id)
        self.runner, self.token = runner, token

    def _run(self):
        try:
            if self.token is None:
                run, selected = self.runner.load(self.run_id), None
            else:
                run, selected = self.runner.by_token(self.token)
            occurrence = next((item for item in run.typed.active if str(item.id) == self.occurrence_id), None)
            if occurrence is None:
                snapshot = next((item for item in run.typed.actions if item["id"] == self.occurrence_id), None)
                from tarav.l1.actions import ActionRun

                if snapshot is None or ActionRun.records.from_record(snapshot).state != "closed":
                    return CheckResult(self, status="incomplete", reason="Action occurrence cannot be resolved")
                return CheckResult(self, status="completed", pois=[])
            if selected is None or occurrence.id != selected.id:
                return CheckResult(self, status="incomplete", reason="Token does not select this active Action")
            checks = self.runner.action_checks(self.token).run()
            self.runner.by_token(self.token)
        except (OSError, ValueError, RuntimeError) as exc:
            return CheckResult(self, status="incomplete", reason=str(exc))
        if not checks.complete:
            return CheckResult(self, status="incomplete", reason="Program Action checks did not complete",
                               data={"action_checks": _evidence(checks)})
        return CheckResult(self, status="completed", pois=[] if checks.clean() else [self.poi(
            ActionIncoherent, message="Program-defined status checks fail for the selected Action",
            details={**self.runner.context(occurrence, "status"),
                     "checks": _evidence(checks)})])


class ProgramContextSuite(CheckSuite):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("3719593e-61d8-4f79-a5af-29f747c36ed2"),
                          name="Tarav.Programs.Context.Suite", workflow=PROGRAMS_WORKFLOW_SHIP)

    def __init__(self, runner, token, occurrence_id, run_id=None):
        self.runner, self.token = runner, token
        self.occurrence_id, self.run_id = occurrence_id, run_id
        super().__init__(key=occurrence_id, name="Program Action coherence",
                         checkpoint_types={"action": (ProgramCoherenceCheck,)})

    def produce(self):
        yield ProgramCoherenceCheck(self.runner, self.token, self.occurrence_id, self.run_id)
        yield SuiteCheckpoint("action")


class ProgramProjectSuite(CheckSuite):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("6208e883-378d-4b2d-815d-961348be8a14"),
                          name="Tarav.Project.Programs.Suite", workflow=PROGRAMS_WORKFLOW_SHIP)

    def __init__(self, manager, *, runner=None, token=None):
        self.manager, self.runner, self.token = manager, runner, token
        super().__init__(key=str(manager.obj.id), name="Project Programs")

    def produce(self):
        self.manager.prepare()
        if self.runner is not None:
            _, selected = self.runner.by_token(self.token)
            yield ProgramContextSuite(self.runner, self.token, str(selected.id))
            return
        # Closure is a recorded fact, independent of check policy. Ordinary
        # status may retire a closed occurrence's warning, but cannot assert
        # that another active occurrence's status checks passed.
        for stored in self.manager.runs():
            runner = self.manager.runner(str(stored.typed.program))
            run = runner.load(str(stored.id))
            active_ids = {str(item.id) for item in run.typed.active}
            for snapshot in run.typed.actions:
                if snapshot["id"] != str(run.id) and snapshot["id"] not in active_ids:
                    yield ProgramContextSuite(runner, None, snapshot["id"], str(run.id))


PROJECT_PROGRAM_RECORD_TYPES = (ActionIncoherent, ProgramCoherenceCheck, ProgramContextSuite, ProgramProjectSuite)

__all__ = ["ProjectProgram", "ProgramsManager", "PROJECT_PROGRAM_RECORD_TYPES"]
