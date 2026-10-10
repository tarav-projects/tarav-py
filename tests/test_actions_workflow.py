"""Step actions over the Operator Context, and the actions that follow POIs."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.actions import (
    ACTIONS_WORKFLOW_SHIP, CLOSED, EXIT_ERROR, LOOP, RUNNING,
    ActionError, ActionRunStore, Exit, StepAction, StepRunner, register_action,
)
from tarav.l1.actions.pois import (
    DISMISSED, GONE, DismissalInput, DismissalNotPermitted, DismissalWithoutReason,
    POIActionClosed,
    POIActions, POIResolutionAction, action_id,
)
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite, ClearPOI, SituationCheck
from tarav.l1.operator_context import OperatorContext, OperatorContextStore
from tarav.l1.poi.actionable import DismissablePOI
from tarav.l1.records import RecordRegistry
from tarav.l3.check import report_project_checks
from tarav.l3.runtime import create_runtime


class FlagMissing(CheckPOI):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("0b6f3f5e-5c1a-4d0e-9d3b-7a1c2e4f6a80"),
                          name="Tarav.Test.Actions.FlagMissing", workflow=ACTIONS_WORKFLOW_SHIP)


class FlagCheck(SituationCheck):
    """Passes when the input's named field is true."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("5d2c8a17-3e94-4b6f-8f20-91c4d7e5b3a6"),
                          name="Tarav.Test.Actions.FlagCheck", workflow=ACTIONS_WORKFLOW_SHIP)

    def __init__(self, context: OperatorContext, field: str) -> None:
        super().__init__(situation={"context": str(context.id), "field": field})
        self.value = context.fields.get(field)
        self.field = field

    def _run(self) -> CheckResult:
        if self.value is True:
            return CheckResult(self, status="completed")
        return CheckResult(self, status="completed",
                           pois=(self.poi(FlagMissing, message=f"{self.field} is not set"),))


class FileCheck(SituationCheck):
    """Passes when a file exists."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("217f4b4f-1bd1-4df7-819c-f0d0bd767223"),
                          name="Tarav.Test.Actions.FileCheck", workflow=ACTIONS_WORKFLOW_SHIP)

    def __init__(self, path: str) -> None:
        super().__init__(situation={"path": path})
        self.path = Path(path)

    def _run(self) -> CheckResult:
        if self.path.exists():
            return CheckResult(self, status="completed")
        return CheckResult(self, status="completed",
                           pois=(self.poi(FlagMissing, message=f"{self.path.name} is absent"),))


class FlagStep(StepAction):
    """Opens when `ready` is set and closes by its one exit when `done` is set."""

    operations = ("note",)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("c94e1f7b-6a28-4d53-b1e9-2f8a7c6d5e04"),
                          name="Tarav.Test.Actions.FlagStep", workflow=ACTIONS_WORKFLOW_SHIP)

    def opening_checks(self, run, context):
        return (FlagCheck(context, "ready"),)

    def exit_checks(self, name, run, context):
        return (FlagCheck(context, "done"),)

    def operate(self, name, run, context):
        return {"noted": context.fields.get("note")}

    def output(self, name, run, context):
        return {"done": True}


class TwoExitStep(StepAction):
    """Closes by `done` when an operator says so, or by `arrived` when a file appears."""

    exits = (Exit("done"), Exit("arrived", by=(LOOP,)))

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6d76462d-4a3a-4857-b9a0-56e0f331d2b1"),
                          name="Tarav.Test.Actions.TwoExitStep", workflow=ACTIONS_WORKFLOW_SHIP)

    def exit_checks(self, name, run, context):
        if name == "arrived":
            return (FileCheck(run.data["intakes"][0]["record"]["waits_for"]),)
        return (FlagCheck(context, "done"),)

    def output(self, name, run, context):
        return {"by": name}


class LampOn(CheckPOI, DismissablePOI):
    """A lamp was found on."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2e39f51f-fa0c-4804-a117-387a2a8bc57e"),
                          name="Tarav.Test.Actions.LampOn", workflow=ACTIONS_WORKFLOW_SHIP)


class LampCheck(SituationCheck):
    """Is a lamp on? What is found is its level; what is examined is the lamp."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("4d4c3dba-d65d-41c4-8f20-b77cfe1fec2e"),
                          name="Tarav.Test.Actions.LampCheck", workflow=ACTIONS_WORKFLOW_SHIP)

    def __init__(self, lamp: str, level: int, *, named: bool = True) -> None:
        super().__init__(situation={"lamp": lamp, "level": level})
        self.lamp, self.level, self.named = lamp, level, named

    @property
    def subject_key(self):
        return {"lamp": self.lamp} if self.named else None

    def _run(self) -> CheckResult:
        if self.level == 0:
            return CheckResult(self, status="completed", pois=(self.clear(),))
        return CheckResult(self, status="completed", pois=(self.poi(
            LampOn, message=f"{self.lamp} is on at {self.level}"),))


for _action in (FlagStep, TwoExitStep):
    register_action(_action)


class Stores:
    def __init__(self, root, records):
        self.root = root
        registry = RecordRegistry(root, records)
        self.contexts = OperatorContextStore(registry)
        self.runs = ActionRunStore(registry)
        self.sessions = [None]
        self.runner = StepRunner(runs=self.runs, contexts=self.contexts,
                                 session=lambda: self.sessions[-1])
        self.pois = POIActions(self.runs)

    def lamps(self, **levels):
        """Run one check per lamp and hand every POI over."""
        return self.pois.observe(
            poi for lamp, level in levels.items() for poi in LampCheck(lamp, level).run().pois())


@pytest.fixture
def stores(tmp_path):
    return Stores(tmp_path / "records", create_runtime().records)


def test_the_runtime_knows_the_workflows_and_the_poi_action():
    runtime = create_runtime()
    assert entity(runtime.workflows.get("actions")).name == "Tarav.Workflow.Actions"
    assert entity(runtime.workflows.get("operator-context")).name == "Tarav.Workflow.OperatorContext"
    from tarav.l1.actions import action_types
    assert action_types()["Tarav.Actions.POI.Resolution"] is POIResolutionAction


def test_a_taken_object_carries_the_hash_of_what_was_read(stores):
    # tarav.breadcrumb 721c8b57e1adbd42e01cb5267892243a59aef78bb1cd62942c2268bc46a3ea80
    context = OperatorContext.new(project={"id": "p", "root": "/p"}, note="one")
    key = stores.contexts.put(context)
    first = stores.contexts.take(key)
    assert first.record["note"] == "one" and first.context.project == {"id": "p", "root": "/p"}
    assert stores.contexts.take(key).hash == first.hash
    assert stores.contexts.put(context) == key  # placing the same object again changes nothing

    stores.contexts.put(OperatorContext(context.id, created_at=context.created_at, note="two"))
    assert stores.contexts.take(key).hash != first.hash
    assert stores.contexts.names() == (key,)
    with pytest.raises(TypeError):
        stores.contexts.take(key, expected=DismissalInput)


def test_a_failed_opening_test_leaves_a_closed_run(stores):
    key = stores.contexts.put(OperatorContext.new())
    run = stores.runner.start(FlagStep, key)
    assert (run.state, run.exit) == (CLOSED, EXIT_ERROR)
    assert run.data["opening"]["results"][0]["pois"][0]["type"] == "Tarav.Test.Actions.FlagMissing"
    assert [item.id for item in stores.runs.list(exit=EXIT_ERROR)] == [run.id]
    with pytest.raises(ActionError):
        stores.runner.close(str(run.id))


def test_a_step_closes_only_when_its_exit_tests_pass(stores):
    # tarav.breadcrumb 21a75ed1831ee17e871b40284505d161a5ec01268617686b1cdfaee269fcb2d8
    context = OperatorContext.new(ready=True, note="hello")
    key = stores.contexts.put(context)
    run = stores.runner.start(FlagStep, key)
    assert (run.state, run.exit) == (RUNNING, None)

    _, result = stores.runner.operate(str(run.id), "note")
    assert result == {"noted": "hello"}
    with pytest.raises(ActionError):
        stores.runner.operate(str(run.id), "unknown")

    still = stores.runner.close(str(run.id))
    assert still.state == RUNNING and still.data["closings"][-1]["passed"] is False

    stores.contexts.put(OperatorContext(context.id, created_at=context.created_at,
                                        ready=True, done=True))
    closed = stores.runner.close(str(run.id))
    assert (closed.state, closed.exit, closed.data["output"]) == (CLOSED, "done", {"done": True})
    hashes = [intake["hash"] for intake in closed.data["intakes"]]
    assert len(hashes) == 4 and hashes[0] == hashes[2] != hashes[3]
    assert stores.runs.list(state=RUNNING) == []


def test_a_running_step_can_be_aborted_with_a_reason(stores):
    run = stores.runner.start(FlagStep, stores.contexts.put(OperatorContext.new(ready=True)))
    with pytest.raises(ActionError):
        stores.runner.abort(str(run.id), " ")
    aborted = stores.runner.abort(str(run.id), "not needed")
    assert (aborted.exit, aborted.data["reason"]) == (EXIT_ERROR, "not needed")


def test_sessions_that_work_on_a_run_are_appended(stores):
    # tarav.breadcrumb 6ea37587042bdf2185f50448fabf14db76767a2736c27dcfca860f11931ef249
    stores.sessions.append({"provider": "claude-code", "session_id": "one"})
    run = stores.runner.start(FlagStep, stores.contexts.put(OperatorContext.new(ready=True)))
    stores.runner.operate(str(run.id), "note")
    stores.sessions.append({"provider": "codex", "session_id": "two"})
    run, _ = stores.runner.operate(str(run.id), "note")
    assert [(item["provider"], item["session_id"]) for item in run.data["sessions"]] == [
        ("claude-code", "one"), ("codex", "two")]


def test_a_step_with_several_exits_closes_by_the_one_that_is_met(stores, tmp_path):
    # tarav.breadcrumb f52d8915de2fb1003a5e67d356044d5d47bdb09a0353e48ce12413df8d4e5987
    flag = tmp_path / "arrived"
    by_loop = stores.runner.start(TwoExitStep, stores.contexts.put(
        OperatorContext.new(waits_for=str(flag))))
    by_hand = stores.runner.start(TwoExitStep, stores.contexts.put(
        OperatorContext.new(waits_for=str(tmp_path / "never"), done=True)))

    with pytest.raises(ActionError):  # the loop's exit is not an operator's to take
        stores.runner.close(str(by_loop.id), exit="arrived")
    assert stores.runner.sweep() == []  # nothing is met yet

    flag.write_text("here", encoding="utf-8")
    assert [run.id for run in stores.runner.sweep()] == [by_loop.id]
    assert stores.runs.load(str(by_loop.id)).exit == "arrived"
    assert stores.runner.close(str(by_hand.id)).data["output"] == {"by": "done"}
    assert {run.exit for run in stores.runs.list(state=CLOSED)} == {"arrived", "done"}


def test_a_poi_opens_its_action_and_raising_it_again_lands_on_the_same_one(stores):
    # tarav.breadcrumb 085585c2b4426856a37dbd5cc22cd9c1a70800b3b32d0406aefcc2676dbbc3ac
    poi = LampCheck("hall", 3).run().pois()[0]
    first = stores.lamps(hall=3, porch=0)
    assert (first["opened"], first["gone"], first["signals"]) == (1, 0, [])
    run = stores.pois.of(poi)
    assert run.id == action_id(poi) and run.state == RUNNING
    assert run.data["action"] == "Tarav.Actions.POI.Resolution"
    assert run.data["subject"] == {"lamp": "hall"}
    assert run.data["event"]["poi"]["id"] == poi.identity

    again = stores.lamps(hall=3)
    assert (again["opened"], again["reopened"], again["actions"]) == (0, 0, 1)
    twice = stores.pois.observe([*LampCheck("den", 1).run().pois(), *LampCheck("den", 1).run().pois()])
    assert (twice["opened"], twice["actions"]) == (1, 1)  # raised twice in one batch: one action
    assert len(stores.runs.list()) == 2


def test_a_clear_check_closes_the_action_and_says_so(stores):
    # tarav.breadcrumb 05f443cee465f2b2678f7b9e493826763320279641a49bdd4c29fe0c5da458be
    poi = LampCheck("hall", 3).run().pois()[0]
    stores.lamps(hall=3, porch=2)
    result = stores.lamps(hall=0, porch=2)
    assert result["gone"] == 1
    run = stores.pois.of(poi)
    assert (run.state, run.exit) == (CLOSED, GONE)
    assert [type(signal) for signal in result["signals"]] == [POIActionClosed]
    assert result["signals"][0].evidence == {"action": str(run.id), "exit": GONE, "poi": poi.identity}
    assert len(stores.runs.list(state=RUNNING)) == 1  # the porch lamp's


def test_a_situation_that_returns_reopens_the_same_action(stores):
    # tarav.breadcrumb 205846dc556e5de648b84fa4ab4133f4228dc2fe0b03cd271450f578cbb4b7a1
    poi = LampCheck("hall", 3).run().pois()[0]
    stores.lamps(hall=3)
    stores.lamps(hall=0)
    back = stores.lamps(hall=3)
    assert (back["opened"], back["reopened"]) == (0, 1)
    run = stores.pois.of(poi)
    assert (run.state, run.exit, run.data["closed_at"]) == (RUNNING, None, None)
    assert len(stores.runs.list()) == 1
    history = subprocess.run(
        ["git", "log", "--format=%s", "--", f"records/{run.id}.json"],
        cwd=stores.runs.map.root, capture_output=True, text=True, check=True).stdout.splitlines()
    assert history == ["POI actions: 1 reopened", "POI actions: 1 gone", "POI actions: 1 opened"]


def test_a_changed_situation_closes_the_old_action_and_opens_another(stores):
    old = LampCheck("hall", 3).run().pois()[0]
    new = LampCheck("hall", 7).run().pois()[0]
    stores.lamps(hall=3)
    result = stores.lamps(hall=7)
    assert (result["opened"], result["gone"]) == (1, 0)  # a finding closes nothing by itself
    assert stores.pois.of(old).state == RUNNING and stores.pois.of(new).state == RUNNING

    stores.lamps(hall=0)
    assert stores.pois.of(old).exit == GONE and stores.pois.of(new).exit == GONE


def test_a_dismissed_action_stays_closed_while_its_poi_is_still_raised(stores):
    # tarav.breadcrumb fdeb5b5f0f31b1e52981ec3757158708056ec008206b28f29ff1f0a45673f664
    poi = LampCheck("hall", 3).run().pois()[0]
    stores.lamps(hall=3)
    run_id = str(action_id(poi))

    with pytest.raises(ActionError):  # an operator's exit needs an operator's input
        stores.runner.close(run_id, exit=DISMISSED)
    with pytest.raises(ActionError):  # gone is not an operator's to take
        stores.runner.close(run_id, stores.contexts.put(DismissalInput.new(reason="x")), exit=GONE)

    empty = stores.contexts.put(DismissalInput.new(reason="  "))
    refused = stores.runner.close(run_id, empty, exit=DISMISSED)
    assert refused.state == RUNNING
    assert refused.data["closings"][-1]["results"][0]["pois"][0]["type"] == entity(DismissalWithoutReason).name

    stores.sessions.append({"provider": "claude-code", "session_id": "one"})
    reason = stores.contexts.put(DismissalInput.new(reason="The hall lamp stays on at night."))
    dismissed = stores.runner.close(run_id, reason, exit=DISMISSED)
    assert (dismissed.state, dismissed.exit) == (CLOSED, DISMISSED)
    assert dismissed.data["output"]["reason"] == "The hall lamp stays on at night."
    assert dismissed.data["output"]["by"]["session_id"] == "one"

    again = stores.lamps(hall=3)
    assert (again["opened"], again["reopened"]) == (0, 0)
    assert stores.pois.of(poi).exit == DISMISSED
    stores.lamps(hall=0)
    assert stores.pois.of(poi).exit == DISMISSED  # a dismissal is not rewritten as gone
    assert {run.exit for run in stores.runs.list(state=CLOSED)} == {DISMISSED}


def test_a_check_without_a_subject_closes_nothing(stores):
    poi = LampCheck("attic", 2, named=False).run().pois()[0]
    stores.pois.observe(LampCheck("attic", 2, named=False).run().pois())
    clear = LampCheck("attic", 0, named=False).run().pois()
    assert [type(item) for item in clear] == [ClearPOI] and clear[0].failure is False
    assert stores.pois.observe(clear)["gone"] == 0
    assert stores.pois.of(poi).state == RUNNING


def test_a_poi_action_opens_as_context_by_the_poi_identity(stores):
    from tarav.l1.actions.views import POI_ACTION_VIEW, POIActionContext, POIActionResolver
    from tarav.l1.context.query import ContextQueryService, IdentityContextQuery

    poi = LampCheck("hall", 3).run().pois()[0]
    stores.lamps(hall=3)
    service = ContextQueryService()
    service.register_resolver("poi-action", POIActionResolver(lambda: stores.runs))
    service.register_view(POI_ACTION_VIEW, POIActionContext)

    answer = service.open(IdentityContextQuery(poi.identity[:12], view=POI_ACTION_VIEW))
    assert answer.subject.id == action_id(poi)
    assert [entry.name for entry in answer.target.ls()] == [
        "standing", "poi", "check", "dismissal", "closings", "acting", "history", "reported"]
    standing = service.open(IdentityContextQuery(
        str(action_id(poi)), view=POI_ACTION_VIEW, path=["standing"]))
    assert standing.target.records.to_record()["value"]["standing"] == "open"


class _Flags(Check):
    """Raises one POI when flagged. It cannot say which check it is."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b21f7c50-6e3a-4d19-8a72-0c5d9e4f1b36"),
                          name="Tarav.Test.Actions.Flags", workflow=ACTIONS_WORKFLOW_SHIP)

    def __init__(self, flagged: bool) -> None:
        super().__init__()
        self.flagged = flagged

    def _run(self) -> CheckResult:
        if not self.flagged:
            return CheckResult(self, status="completed")
        return CheckResult(self, status="completed", pois=[
            CheckPOI(self, "something is off", situation={"case": "flagged"})])


class _Project:
    def __init__(self, *checks: Check) -> None:
        self._checks = checks

    @property
    def checks(self):
        return CheckSuite(self._checks)


class _Lamp(Check):
    """Raises a POI when a lamp is on. It names the lamp as what it examines."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("91b6e531-2e89-4ccc-98f5-310200850b6e"),
                          name="Tarav.Test.Actions.Lamp", workflow=ACTIONS_WORKFLOW_SHIP)

    def __init__(self, lamp: str, level: int) -> None:
        super().__init__()
        self.lamp, self.level = lamp, level

    @property
    def subject_key(self):
        return {"lamp": self.lamp}

    def _run(self) -> CheckResult:
        if not self.level:
            return CheckResult(self, status="completed")
        return CheckResult(self, status="completed", pois=[CheckPOI(
            self, f"{self.lamp} is on", situation={"lamp": self.lamp, "level": self.level})])


class _Home:
    """A Project-like provider with the identity the check command hands on."""

    def __init__(self, root: Path, *checks: Check) -> None:
        self.id, self.name, self.root, self._checks = "home", "home", root, checks

    @property
    def checks(self):
        return CheckSuite(self._checks)


@pytest.fixture
def registry(tmp_path, monkeypatch):
    from tarav.l3.runtime import create_runtime, set_runtime

    monkeypatch.setenv("TARAV_RECORDS", str(tmp_path / "records"))
    set_runtime(create_runtime())
    yield tmp_path / "records"
    set_runtime(None)


# tarav.breadcrumb 44282e11e5c1d9d9198c44b17465611161f7dc5d0d810bf6be4f99f62e029e89
def test_the_check_command_hands_its_run_to_the_actions_workflow(
        tmp_path, registry, capsys):
    from tarav.l1.actions import ActionRunStore

    assert report_project_checks(_Home(tmp_path, _Lamp("hall", 3), _Flags(True))) == 1
    assert "POI actions: 2 raised now; 2 opened, 0 reopened, 0 closed as gone." in \
        capsys.readouterr().out
    runs = ActionRunStore().list(project_root=str(tmp_path))
    assert {run.state for run in runs} == {"running"} and len(runs) == 2

    # the lamp is off and the unnamed check finds nothing: both situations are gone
    assert report_project_checks(_Home(tmp_path, _Lamp("hall", 0), _Flags(False)),
                                 json_output=True) == 0
    acted = json.loads(capsys.readouterr().out)["actions"]
    assert (acted["opened"], acted["gone"]) == (0, 2)
    assert sorted(signal["type"] for signal in acted["closed"]) == [
        "Tarav.Actions.POI.Closed", "Tarav.Actions.POI.Closed"]
    assert {run.exit for run in ActionRunStore().list(project_root=str(tmp_path))} == {"gone"}

    # another Project's run does not touch these actions, and skipping leaves them alone
    other = tmp_path / "other"
    assert report_project_checks(_Home(other, _Lamp("hall", 0)), json_output=True) == 0
    capsys.readouterr()
    assert report_project_checks(_Home(tmp_path, _Lamp("hall", 3)), actions="skip") == 1
    assert "POI actions" not in capsys.readouterr().out
    assert {run.exit for run in ActionRunStore().list(project_root=str(tmp_path))} == {"gone"}


def test_a_poi_that_is_not_a_failure_does_not_make_the_run_unclean(registry, capsys):
    class Clear(Check):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(target=cls, id=TypeShip("9e484d4c-8c0d-46fe-ba05-8d6c6e7ec7ef"),
                              name="Tarav.Test.Actions.ClearOnly", workflow=ACTIONS_WORKFLOW_SHIP)

        def _run(self) -> CheckResult:
            return CheckResult(self, status="completed", pois=[self.clear()])

    assert report_project_checks(_Project(Clear()), actions="skip") == 0
    assert "1 checks, 0 incomplete, 1 POIs" in capsys.readouterr().out


def test_a_poi_that_does_not_allow_dismissal_is_not_dismissed(tmp_path, registry, capsys):
    # tarav.breadcrumb d5f905bd09bfb1b361caa0a2bcb681d8695d155576ca37d7e5466a33c4555cad
    from tarav.l1.actions import ActionRunStore
    from tarav.l1.operator_context import OperatorContextStore as Contexts

    flags = _Flags(True).run().pois()[0]  # a plain CheckPOI
    lamp = LampCheck("hall", 3).run().pois()[0]  # a dismissable one
    home = _Home(tmp_path, _Flags(True), LampCheck("hall", 3))
    assert report_project_checks(home) == 1
    capsys.readouterr()
    runner = StepRunner(runs=ActionRunStore(), contexts=Contexts(), session=lambda: None)
    reason = Contexts().put(DismissalInput.new(reason="Known and accepted."))

    refused = runner.close(str(action_id(flags)), reason, exit=DISMISSED)
    assert refused.state == RUNNING
    assert refused.data["closings"][-1]["results"][0]["pois"][0]["type"] == entity(DismissalNotPermitted).name

    assert runner.close(str(action_id(lamp)), reason, exit=DISMISSED).exit == DISMISSED
    assert report_project_checks(home) == 1  # the plain finding is still open
    assert "(0 open, 0 blessed, 1 dismissed)" in capsys.readouterr().out

    assert report_project_checks(_Home(tmp_path, LampCheck("hall", 3))) == 0  # all that is raised is dismissed
    # the check that did not run this time says nothing: its action stays open
    assert ActionRunStore().load(str(action_id(flags))).state == RUNNING
