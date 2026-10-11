"""Step actions over the Operator Context, and the actions that follow POIs."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.actions import (
    ACTIONS_WORKFLOW_SHIP, CLOSED, EXIT_ERROR, LOOP, RUNNING,
    ActionError, ActionRunStore, Closing, Exit, StepAction, StepRunner, axes, register_action,
)
from tarav.l1.actions.pois import (
    GONE, GoneClosing, POIActionClosed, POIActions, POIResolutionAction, action_id,
)
from tarav.l1.actions.suites import Suite
from tarav.l1.actions.blessing import (
    BLESSED, Blessing, BlessingInput, BlessingNotPermitted, BlessingWithoutReason,
)
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite, SituationCheck
from tarav.l1.operator_context import OperatorContext, OperatorContextStore
from tarav.l1.poi.actionable import BlessablePOI
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


class LampOn(CheckPOI, BlessablePOI):
    """A lamp was found on."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2e39f51f-fa0c-4804-a117-387a2a8bc57e"),
                          name="Tarav.Test.Actions.LampOn", workflow=ACTIONS_WORKFLOW_SHIP)


class LampCheck(SituationCheck):
    """Is a lamp on? What is found is its level."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("4d4c3dba-d65d-41c4-8f20-b77cfe1fec2e"),
                          name="Tarav.Test.Actions.LampCheck", workflow=ACTIONS_WORKFLOW_SHIP)

    def __init__(self, lamp: str, level: int) -> None:
        super().__init__(situation={"lamp": lamp, "level": level})
        self.lamp, self.level = lamp, level

    def _run(self) -> CheckResult:
        if self.level == 0:
            return CheckResult(self, status="completed")
        return CheckResult(self, status="completed", pois=(self.poi(
            LampOn, message=f"{self.lamp} is on at {self.level}"),))


class LampSuite(Suite):
    """Whatever the lamp checks examine in one home."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7c0e5d2a-9b41-4f63-8e17-a3d6f4b20c95"),
                          name="Tarav.Test.Actions.LampSuite", workflow=ACTIONS_WORKFLOW_SHIP)


class OtherSuite(Suite):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("1d8f3b6e-2a75-4c90-b4e2-6f9a0c7d5e31"),
                          name="Tarav.Test.Actions.OtherSuite", workflow=ACTIONS_WORKFLOW_SHIP)


HOME = {"id": "home", "name": "home", "root": "/home"}


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
        self.suite = LampSuite(self.runs)

    def lamps(self, **levels):
        """Run one check per lamp as one run of the lamp suite on the home."""
        return self.suite.settle(
            [poi for lamp, level in levels.items() for poi in LampCheck(lamp, level).run().pois()],
            target=HOME)


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
        stores.contexts.take(key, expected=BlessingInput)


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
    record = closed.data["closing"]  # every closing leaves a typed record
    assert (record["type"], record["exit"], record["by"]) == ("Tarav.Actions.Closing", "done", "operator")
    assert type(closed.closing()) is Closing and record["run"] == str(closed.id)
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
    assert stores.runs.load(str(by_loop.id)).data["closing"]["by"] == "loop"
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
    assert run.data["suite"] == LampSuite.reference() and run.data["project"] == HOME
    assert run.data["event"]["poi"]["id"] == poi.identity
    assert axes(run) == {"situation": "present", "action": "open", "closing": None}

    again = stores.lamps(hall=3)
    assert (again["opened"], again["reopened"], again["actions"]) == (0, 0, 1)
    twice = stores.lamps(hall=3, den=1, **{"den ": 0})  # raised once more with another: no new one
    assert (twice["opened"], twice["actions"]) == (1, 2)
    same = stores.suite.settle([*LampCheck("den", 1).run().pois(), *LampCheck("den", 1).run().pois(),
                                poi], target=HOME)
    assert (same["opened"], same["actions"]) == (0, 2)  # raised twice in one run: one action
    assert len(stores.runs.list()) == 2


def test_a_suite_that_no_longer_detects_a_situation_closes_its_action(stores):
    # tarav.breadcrumb 05f443cee465f2b2678f7b9e493826763320279641a49bdd4c29fe0c5da458be
    poi = LampCheck("hall", 3).run().pois()[0]
    stores.lamps(hall=3, porch=2)
    result = stores.lamps(hall=0, porch=2)
    assert result["gone"] == 1
    run = stores.pois.of(poi)
    assert (run.state, run.exit) == (CLOSED, GONE)
    record = run.data["closing"]
    assert (record["type"], record["by"], record["suite"]) == (
        "Tarav.Actions.POI.Gone", "suite", LampSuite.reference())
    assert isinstance(run.closing(), GoneClosing)
    assert axes(run) == {"situation": "absent", "action": "closed", "closing": "gone"}
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
    assert (run.state, run.exit, run.data["closed_at"], run.data["closing"]) == (
        RUNNING, None, None, None)
    assert len(stores.runs.list()) == 1
    history = subprocess.run(
        ["git", "log", "--format=%s", "--", f"records/{run.id}.json"],
        cwd=stores.runs.map.root, capture_output=True, text=True, check=True).stdout.splitlines()
    name = "Tarav.Test.Actions.LampSuite"
    assert history == [f"{name}: 1 reopened", f"{name}: 1 gone", f"{name}: 1 opened"]


def test_a_changed_situation_closes_the_old_action_and_opens_another(stores):
    old = LampCheck("hall", 3).run().pois()[0]
    new = LampCheck("hall", 7).run().pois()[0]
    stores.lamps(hall=3)
    result = stores.lamps(hall=7)
    assert (result["opened"], result["gone"]) == (1, 1)  # the suite no longer produces the old POI
    assert stores.pois.of(old).exit == GONE and stores.pois.of(new).state == RUNNING


# tarav.breadcrumb b2bbf6a3a52b40d51395a1fe67bdf556bac546b5b6381a4330111ab13c9c5568
def test_a_suite_closes_only_what_it_manages_and_only_after_a_whole_run(stores):
    # tarav.breadcrumb fdeb5b5f0f31b1e52981ec3757158708056ec008206b28f29ff1f0a45673f664
    poi = LampCheck("hall", 3).run().pois()[0]
    stores.lamps(hall=3)

    crashed = stores.suite.settle([], target=HOME, incomplete=("Tarav.Test.Actions.LampCheck",))
    assert crashed["gone"] == 0  # the check that raised it did not complete: it says nothing
    assert stores.suite.settle([], target=HOME, complete=False)["gone"] == 0  # not a whole run
    assert stores.suite.settle([], target={**HOME, "root": "/elsewhere"})["gone"] == 0
    assert OtherSuite(stores.runs).settle([], target=HOME)["gone"] == 0  # not its action
    seen = OtherSuite(stores.runs).settle([poi], target=HOME)
    assert (seen["opened"], seen["updated"], seen["actions"]) == (0, 0, 1)  # seen, left as it is
    assert stores.pois.of(poi).data["suite"] == LampSuite.reference()
    assert stores.pois.of(poi).state == RUNNING

    assert stores.suite.settle([], target=HOME)["gone"] == 1
    assert [run.id for run in stores.suite.managed(HOME)] == [action_id(poi)]


# tarav.breadcrumb 12324a92e406d21751c0840926d26105666df6f9f701313bce82a9a25b15922e
# tarav.breadcrumb a9917108740744d28b1b59bccbf468521cfe730fe919232973e8064aece194d0
def test_a_blessed_action_stays_closed_while_its_poi_is_still_raised(stores):
    poi = LampCheck("hall", 3).run().pois()[0]
    stores.lamps(hall=3)
    run_id = str(action_id(poi))

    with pytest.raises(ActionError):  # an operator's exit needs an operator's input
        stores.runner.close(run_id, exit=BLESSED)
    with pytest.raises(ActionError):  # gone is the suite's to take, not an operator's
        stores.runner.close(run_id, stores.contexts.put(BlessingInput.new(reason="x")), exit=GONE)

    empty = stores.contexts.put(BlessingInput.new(reason="  "))
    refused = stores.runner.close(run_id, empty, exit=BLESSED)
    assert refused.state == RUNNING and refused.data["closing"] is None
    assert refused.data["closings"][-1]["results"][0]["pois"][0]["type"] == entity(BlessingWithoutReason).name

    stores.sessions.append({"provider": "claude-code", "session_id": "one"})
    support = [{"type": "Example.Source.Reference", "locator": {"path": "house-rules.md"}}]
    reason = stores.contexts.put(BlessingInput.new(
        reason="The hall lamp stays on at night.", support=support))
    blessed = stores.runner.close(run_id, reason, exit=BLESSED)
    assert (blessed.state, blessed.exit) == (CLOSED, BLESSED)
    record = blessed.data["closing"]
    assert (record["type"], record["reason"], record["support"]) == (
        "Tarav.Blessings.Blessing", "The hall lamp stays on at night.", support)
    assert record["actor"]["session_id"] == "one" and record["poi"]["id"] == poi.identity
    blessing = stores.pois.blessing(poi)
    assert isinstance(blessing, Blessing) and str(blessing.id) == record["id"]
    assert stores.pois.blessing_standing(poi) == {"status": "blessed", "blessing": record["id"]}

    again = stores.lamps(hall=3)  # the situation still exists: the blessing holds
    assert (again["opened"], again["reopened"]) == (0, 0)
    assert axes(stores.pois.of(poi)) == {
        "situation": "present", "action": "closed", "closing": "blessed"}
    away = stores.lamps(hall=0)  # the situation goes: the axis says so, the closing stays
    assert (away["gone"], away["updated"]) == (0, 1)
    assert axes(stores.pois.of(poi)) == {
        "situation": "absent", "action": "closed", "closing": "blessed"}
    assert stores.lamps(hall=3)["reopened"] == 0
    assert axes(stores.pois.of(poi))["situation"] == "present"
    assert stores.pois.of(poi).data["closing"]["id"] == record["id"]


# tarav.breadcrumb 95f611786d834315821c4e6a7296150d2caa44f8a0fa25208e71fae43f2b3225
def test_a_blessing_declares_assertions_and_scores_stay_with_the_scorer(stores, tmp_path):
    from tarav.l2.blessings import BlessingAcceptanceAssertion, BlessingGroundsAssertion
    from tarav.l2.scoring.repository import ScoringRepository

    plain, backed = LampCheck("hall", 3).run().pois()[0], LampCheck("den", 1).run().pois()[0]
    stores.lamps(hall=3, den=1)
    support = [{"type": "Example.Source.Reference", "locator": {"path": "house-rules.md"}}]
    stores.runner.close(str(action_id(plain)), stores.contexts.put(
        BlessingInput.new(reason="Accepted.")), exit=BLESSED)
    stores.runner.close(str(action_id(backed)), stores.contexts.put(
        BlessingInput.new(reason="The rules allow it.", support=support)), exit=BLESSED)

    first, second = stores.pois.blessing(plain), stores.pois.blessing(backed)
    assert list(first.assertions) == ["main"] and list(second.assertions) == ["main", "grounds"]
    main = second.assertions["main"]
    assert isinstance(main, BlessingAcceptanceAssertion)
    assert isinstance(second.assertions["grounds"], BlessingGroundsAssertion)
    assert main.records.to_record()["subject_ref"]["blessing_id"] == str(second.id)
    assert first.assertions["main"].id != main.id  # another blessing, another assertion
    vector = second.score_vector(ScoringRepository(tmp_path / "scores"))
    assert {label: row["status"] for label, row in vector.items()} == {
        "main": "unassessed", "grounds": "unassessed"}
    assert "score" not in second.records.to_record()


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
        "standing", "poi", "managed-by", "closing", "closings", "acting", "history", "reported"]
    standing = service.open(IdentityContextQuery(
        str(action_id(poi)), view=POI_ACTION_VIEW, path=["standing"]))
    value = standing.target.records.to_record()["value"]
    assert value["standing"] == "open" and value["axes"]["situation"] == "present"


class _Flags(Check):
    """Raises one POI when flagged. Its POI's Type does not allow a blessing."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b21f7c50-6e3a-4d19-8a72-0c5d9e4f1b36"),
                          name="Tarav.Test.Actions.Flags", workflow=ACTIONS_WORKFLOW_SHIP)

    def __init__(self, flagged: bool, *, crash: bool = False) -> None:
        super().__init__()
        self.flagged, self.crash = flagged, crash

    def _run(self) -> CheckResult:
        if self.crash:
            raise RuntimeError("the flags could not be read")
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
def test_the_check_command_settles_the_projects_suite(tmp_path, registry, capsys):
    from tarav.l1.actions import ActionRunStore
    from tarav.l1.project.suite import ProjectsSuite

    assert report_project_checks(_Home(tmp_path, LampCheck("hall", 3), _Flags(True))) == 1
    assert "POI actions: 2 raised now; 2 opened, 0 reopened, 0 closed as gone." in \
        capsys.readouterr().out
    runs = ActionRunStore().list(project_root=str(tmp_path))
    assert {run.state for run in runs} == {"running"} and len(runs) == 2
    assert {run.data["suite"]["name"] for run in runs} == {"Tarav.Project.Suite"}

    # a check that crashes says nothing about what it raised: only the lamp's action closes
    assert report_project_checks(
        _Home(tmp_path, LampCheck("hall", 0), _Flags(True, crash=True)), json_output=True) == 1
    acted = json.loads(capsys.readouterr().out)["actions"]
    assert (acted["opened"], acted["gone"], acted["suite"]) == (0, 1, ProjectsSuite.reference())
    assert [signal["type"] for signal in acted["closed"]] == ["Tarav.Actions.POI.Closed"]

    # the flags are fine now: the suite no longer produces that POI either
    assert report_project_checks(_Home(tmp_path, LampCheck("hall", 0), _Flags(False)),
                                 json_output=True) == 0
    assert json.loads(capsys.readouterr().out)["actions"]["gone"] == 1
    assert {run.exit for run in ActionRunStore().list(project_root=str(tmp_path))} == {"gone"}

    # another Project's run does not touch these actions, and skipping leaves them alone
    other = tmp_path / "other"
    assert report_project_checks(_Home(other, LampCheck("hall", 0)), json_output=True) == 0
    capsys.readouterr()
    assert report_project_checks(_Home(tmp_path, LampCheck("hall", 3)), actions="skip") == 1
    assert "POI actions" not in capsys.readouterr().out
    assert {run.exit for run in ActionRunStore().list(project_root=str(tmp_path))} == {"gone"}


def test_a_poi_that_is_not_a_failure_does_not_make_the_run_unclean(registry, capsys):
    class Fine(Check):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(target=cls, id=TypeShip("9e484d4c-8c0d-46fe-ba05-8d6c6e7ec7ef"),
                              name="Tarav.Test.Actions.FineOnly", workflow=ACTIONS_WORKFLOW_SHIP)

        def _run(self) -> CheckResult:
            return CheckResult(self, status="completed", pois=[
                CheckPOI(self, "all is fine", situation={"case": "fine"}, failure=False)])

    assert report_project_checks(_Project(Fine()), actions="skip") == 0
    assert "1 checks, 0 incomplete, 1 POIs" in capsys.readouterr().out


def test_a_poi_that_does_not_allow_a_blessing_is_not_blessed(tmp_path, registry, capsys):
    # tarav.breadcrumb d5f905bd09bfb1b361caa0a2bcb681d8695d155576ca37d7e5466a33c4555cad
    from tarav.l1.actions import ActionRunStore
    from tarav.l1.operator_context import OperatorContextStore as Contexts

    flags = _Flags(True).run().pois()[0]  # a plain CheckPOI
    lamp = LampCheck("hall", 3).run().pois()[0]  # a blessable one
    home = _Home(tmp_path, _Flags(True), LampCheck("hall", 3))
    assert report_project_checks(home) == 1
    capsys.readouterr()
    runner = StepRunner(runs=ActionRunStore(), contexts=Contexts(), session=lambda: None)
    reason = Contexts().put(BlessingInput.new(reason="Known and accepted."))

    refused = runner.close(str(action_id(flags)), reason, exit=BLESSED)
    assert refused.state == RUNNING
    assert refused.data["closings"][-1]["results"][0]["pois"][0]["type"] == entity(BlessingNotPermitted).name

    assert runner.close(str(action_id(lamp)), reason, exit=BLESSED).exit == BLESSED
    assert report_project_checks(home) == 1  # the plain finding is still open
    assert "(0 open, 1 blessed)" in capsys.readouterr().out

    # all that is raised is blessed; the suite no longer produces the flags POI, so it is gone
    assert report_project_checks(_Home(tmp_path, LampCheck("hall", 3))) == 0
    assert ActionRunStore().load(str(action_id(flags))).exit == GONE
    assert ActionRunStore().load(str(action_id(lamp))).exit == BLESSED
