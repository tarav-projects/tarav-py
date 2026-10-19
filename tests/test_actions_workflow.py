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
    GONE, GoneClosing, POIActionClosed, POIResolutionAction, action_id,
)
from tarav.l1.actions.project import ProjectActions
from tarav.l1.actions.blessing import (
    BLESSED, Blessing, BlessingInput, BlessingNotPermitted, BlessingWithoutReason,
)
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite, SituationCheck
from tarav.l1.operator_context import OperatorContext, OperatorContextStore
from tarav.l1.poi.actionable import BlessablePOI
from tarav.l1.records import RecordRegistry
from tarav.l1.project import TaravProject
from tarav.l3.check import report_project_checks
from tarav.l3.status import report_project_status
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

    def __init__(self, lamp: str, level: int, *, crash: bool = False) -> None:
        super().__init__(situation={"lamp": lamp, "level": level})
        self.lamp, self.level, self.crash = lamp, level, crash

    def _run(self) -> CheckResult:
        if self.crash:  # present in the suite, and it does not complete
            raise RuntimeError(f"{self.lamp} cannot be read")
        if self.level == 0:
            return CheckResult(self, status="completed")
        return CheckResult(self, status="completed", pois=(self.poi(
            LampOn, message=f"{self.lamp} is on at {self.level}"),))


HOME = {"id": "home", "name": "home", "root": "/home"}
SHED = {"id": "shed", "name": "shed", "root": "/shed"}


def lamp_suite(crash=(), **levels) -> CheckSuite:
    """One lamp check per lamp, some of them crashing."""
    return CheckSuite([*(LampCheck(lamp, level) for lamp, level in levels.items()),
                       *(LampCheck(lamp, 0, crash=True) for lamp in crash)])


for _action in (FlagStep, TwoExitStep):
    register_action(_action)


def _attempts(run):
    """The attempts at an exit on a run's tape."""
    return [entry for entry in run.data["tape"]
            if entry["type"] == "Tarav.Actions.Tape.ClosingAttempt"]


class _ByPOI:
    """Find the action of a POI in the registry, whichever Project it is registered under."""

    def __init__(self, runs) -> None:
        self.runs = runs

    def of(self, poi):
        return self.runs.find(str(action_id(poi)))


class Stores:
    def __init__(self, root, records):
        self.root = root
        registry = RecordRegistry(root, records)
        self.contexts = OperatorContextStore(registry)
        self.runs = ActionRunStore(registry)
        self.sessions = [None]
        self.runner = StepRunner(runs=self.runs, contexts=self.contexts,
                                 session=lambda: self.sessions[-1])
        self.pois = _ByPOI(self.runs)

    def update(self, owner, checks):
        """Hand a Project's actions one run of its checks."""
        return ProjectActions(owner, self.runs).update(checks)

    def lamps(self, owner=HOME, crash=(), **levels):
        """One run of a Project's checks, one check per lamp, handed to its actions."""
        return self.update(owner, lamp_suite(crash, **levels).run())


@pytest.fixture
def stores(tmp_path):
    return Stores(tmp_path / "records", create_runtime().records)


def test_the_runtime_knows_the_workflows_and_the_poi_action():
    runtime = create_runtime()
    assert entity(runtime.workflows.get("Tarav.Workflow.Actions")).name == "Tarav.Workflow.Actions"
    assert entity(runtime.workflows.get("Tarav.Workflow.OperatorContext")).name == "Tarav.Workflow.OperatorContext"
    from tarav.l1.actions import action_types
    assert action_types()["Tarav.Actions.POI.Resolution"] is POIResolutionAction


def test_a_taken_object_carries_the_hash_of_what_was_read(stores):
    # tarav.breadcrumb 721c8b57e1ad
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
    # tarav.breadcrumb 21a75ed1831e
    context = OperatorContext.new(ready=True, note="hello")
    key = stores.contexts.put(context)
    run = stores.runner.start(FlagStep, key)
    assert (run.state, run.exit) == (RUNNING, None)

    _, result = stores.runner.operate(str(run.id), "note")
    assert result == {"noted": "hello"}
    with pytest.raises(ActionError):
        stores.runner.operate(str(run.id), "unknown")

    still = stores.runner.close(str(run.id))
    assert still.state == RUNNING and _attempts(still)[-1]["passed"] is False

    stores.contexts.put(OperatorContext(context.id, created_at=context.created_at,
                                        ready=True, done=True))
    closed = stores.runner.close(str(run.id))
    assert (closed.state, closed.exit, closed.data["output"]) == (CLOSED, "done", {"done": True})
    record = closed.closing_record()  # every closing leaves a typed record
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
    # tarav.breadcrumb 6ea37587042b
    stores.sessions.append({"provider": "claude-code", "session_id": "one"})
    run = stores.runner.start(FlagStep, stores.contexts.put(OperatorContext.new(ready=True)))
    stores.runner.operate(str(run.id), "note")
    stores.sessions.append({"provider": "codex", "session_id": "two"})
    run, _ = stores.runner.operate(str(run.id), "note")
    assert [(item["provider"], item["session_id"]) for item in run.data["sessions"]] == [
        ("claude-code", "one"), ("codex", "two")]


def test_a_step_with_several_exits_closes_by_the_one_that_is_met(stores, tmp_path):
    # tarav.breadcrumb f52d8915de2f
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
    assert stores.runs.load(str(by_loop.id)).closing_record()["by"] == "loop"
    assert stores.runner.close(str(by_hand.id)).data["output"] == {"by": "done"}
    assert {run.exit for run in stores.runs.list(state=CLOSED)} == {"arrived", "done"}


def test_a_poi_opens_its_action_and_raising_it_again_lands_on_the_same_one(stores):
    # tarav.breadcrumb 085585c2b442
    poi = LampCheck("hall", 3).run().pois()[0]
    first = stores.lamps(hall=3, porch=0)
    assert (first["opened"], first["gone"], first["signals"]) == (1, 0, [])
    run = stores.pois.of(poi)
    assert run.id == action_id(poi) and run.state == RUNNING
    assert run.data["action"] == "Tarav.Actions.POI.Resolution"
    assert run.data["project"] == HOME
    assert run.data["event"]["poi"]["id"] == poi.identity
    assert axes(run) == {"situation": "present", "action": "open", "closing": None}

    again = stores.lamps(hall=3)
    assert (again["opened"], again["reopened"], again["actions"]) == (0, 0, 1)
    twice = stores.update(HOME, CheckSuite(
        [LampCheck("hall", 3), LampCheck("den", 1), LampCheck("den", 1)]).run())
    assert (twice["opened"], twice["actions"]) == (1, 2)  # raised twice in one run: one action
    assert twice["project"] == HOME and len(stores.runs.list()) == 2
    assert len(ProjectActions(HOME, stores.runs).list()) == 2
    assert ProjectActions(SHED, stores.runs).list() == []


def test_checks_that_no_longer_produce_a_poi_close_its_action(stores):
    # tarav.breadcrumb 05f443cee465
    poi = LampCheck("hall", 3).run().pois()[0]
    stores.lamps(hall=3, porch=2)
    result = stores.lamps(hall=0, porch=2)
    assert result["gone"] == 1
    run = stores.pois.of(poi)
    assert (run.state, run.exit) == (CLOSED, GONE)
    record = run.closing_record()
    assert (record["type"], record["by"], record["project"]) == (
        "Tarav.Actions.POI.Gone", "project", HOME)
    assert isinstance(run.closing(), GoneClosing)
    assert axes(run) == {"situation": "absent", "action": "closed", "closing": "gone"}
    assert [type(signal) for signal in result["signals"]] == [POIActionClosed]
    signal = result["signals"][0]
    assert signal.closed == {"action": str(run.id), "exit": GONE, "poi": poi.identity}
    assert signal.project == HOME and signal.records.to_record()["closed"] == signal.closed
    assert len(stores.runs.list(state=RUNNING)) == 1  # the porch lamp's


def test_a_situation_that_returns_reopens_the_same_action(stores):
    # tarav.breadcrumb 205846dc556e
    poi = LampCheck("hall", 3).run().pois()[0]
    stores.lamps(hall=3)
    stores.lamps(hall=0)
    back = stores.lamps(hall=3)
    assert (back["opened"], back["reopened"]) == (0, 1)
    run = stores.pois.of(poi)
    assert (run.state, run.exit, run.closed_at, run.closing_record()) == (
        RUNNING, None, None, None)
    # the closing it reopened from stays on its tape
    assert [item["type"].rsplit(".", 1)[-1] for item in run.data["tape"]] == [
        "Opened", "Closed", "Reopened"]
    assert run.data["tape"][1]["closing"]["exit"] == GONE
    assert len(stores.runs.list()) == 1
    history = subprocess.run(
        ["git", "log", "--format=%s", "--", f"records/{run.id}.json"],
        cwd=stores.runs.map.root, capture_output=True, text=True, check=True).stdout.splitlines()
    name = "Update the actions of home"
    assert history == [f"{name}: 1 reopened", f"{name}: 1 gone", f"{name}: 1 opened"]


def test_a_changed_situation_closes_the_old_action_and_opens_another(stores):
    old = LampCheck("hall", 3).run().pois()[0]
    new = LampCheck("hall", 7).run().pois()[0]
    stores.lamps(hall=3)
    result = stores.lamps(hall=7)
    assert (result["opened"], result["gone"]) == (1, 1)  # the checks no longer produce the old POI
    assert stores.pois.of(old).exit == GONE and stores.pois.of(new).state == RUNNING


def test_a_check_that_is_present_and_failed_leaves_its_action_and_says_so(stores):
    # tarav.breadcrumb 5adbc5645414
    poi = LampCheck("hall", 3).run().pois()[0]
    stores.lamps(hall=3)

    crashed = stores.lamps(crash=("hall",))  # the check is there; it did not complete
    assert (crashed["gone"], crashed["updated"]) == (0, 1)
    assert axes(stores.pois.of(poi)) == {
        "situation": "check failed", "action": "open", "closing": None}
    assert stores.lamps(crash=("hall",))["updated"] == 0  # nothing new to say

    gone = stores.lamps()  # no check of that kind is there any more: it is gone
    assert gone["gone"] == 1 and stores.pois.of(poi).exit == GONE


def test_each_project_updates_its_own_actions_from_its_own_checks(stores):
    # tarav.breadcrumb 7835dc20420d
    hall = LampCheck("hall", 3).run().pois()[0]
    bench = LampCheck("bench", 2).run().pois()[0]
    stores.lamps(HOME, hall=3)
    stores.lamps(SHED, bench=2)
    assert stores.pois.of(hall).data["project"] == HOME
    assert stores.pois.of(bench).data["project"] == SHED

    # the shed's run closes the shed's action and leaves the home's alone
    alone = stores.lamps(SHED, bench=0)
    assert (alone["gone"], alone["project"]) == (1, SHED)
    assert stores.pois.of(bench).exit == GONE and stores.pois.of(hall).state == RUNNING

    # the home's run says nothing about the shed
    stores.lamps(SHED, bench=2)
    assert stores.lamps(HOME, hall=3)["gone"] == 0
    assert stores.pois.of(bench).state == RUNNING


def test_an_action_belongs_to_the_project_whose_checks_produce_its_poi(stores):
    # tarav.breadcrumb 78e2e229759d
    bench = LampCheck("bench", 2).run().pois()[0]
    stores.lamps(HOME, bench=2)  # first produced by the home's checks
    assert stores.pois.of(bench).data["project"] == HOME
    moved = stores.lamps(SHED, bench=2)
    assert (moved["opened"], moved["gone"], moved["updated"]) == (0, 0, 1)
    assert stores.pois.of(bench).data["project"] == SHED and stores.pois.of(bench).state == RUNNING
    assert stores.lamps(HOME)["gone"] == 0  # it is not the home's any more


def test_starting_and_refreshing_are_separate_and_write_nothing_by_themselves(stores):
    # tarav.breadcrumb 1b3481cce255
    home = ProjectActions(HOME, stores.runs)
    checks = lamp_suite(hall=3).run()
    started = home.start(checks)
    assert [run.state for run in started.values()] == [RUNNING] and not stores.runs.exists()
    changes, update = home.refresh(checks, registered=started)
    assert changes == {} and update.signals == []  # a new action has nothing to add

    home.update(checks)
    assert home.start(checks) == {}  # already registered here
    changes, update = home.refresh(lamp_suite(hall=0).run())
    assert [change for _, change in changes.values()] == [GONE]
    assert [type(signal) for signal in update.signals] == [POIActionClosed]
    assert home.list()[0].state == RUNNING  # nothing was written


def test_an_action_type_without_a_rule_ignores_the_checks(stores):
    # tarav.breadcrumb 749768306516
    context = stores.contexts.put(OperatorContext.new(ready=True))
    run = stores.runner.start(FlagStep, context)
    run.data["project"] = HOME
    stores.runs.save(run, "Register the step under the home")
    result = stores.lamps(HOME, hall=3)
    assert (result["opened"], result["updated"], result["gone"]) == (1, 0, 0)
    assert stores.runs.load(str(run.id)).state == RUNNING
    assert len(ProjectActions(HOME, stores.runs).list()) == 2


class RoomSuite(CheckSuite):
    """The lamps of one room: a suite with an identity, bound to the room by its key."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b7e3a1c8-5d92-4f06-8a4b-1c6e9d2f7053"),
                          name="Tarav.Test.Actions.RoomSuite", workflow=ACTIONS_WORKFLOW_SHIP)


class AtticSuite(RoomSuite):
    """A room that is slow to check, so it is not part of the routine run."""

    routine = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("c8f4b2d9-6ea3-4017-9b5c-2d7f0e3a8164"),
                          name="Tarav.Test.Actions.AtticSuite", workflow=ACTIONS_WORKFLOW_SHIP)


def house(hall: int, attic: int | None, crash=()) -> CheckSuite:
    """A hall lamp checked by the house itself, and an attic with a suite of its own."""
    rooms = [] if attic is None else [
        RoomSuite([LampCheck("attic", attic, crash="attic" in crash)], key="attic")]
    return CheckSuite([LampCheck("hall", hall), CheckSuite(rooms)])


def without_rooms(item) -> bool:
    return not isinstance(item, RoomSuite)


# tarav.breadcrumb 79d19e4065cd
def test_only_a_detector_that_ran_can_say_a_situation_is_gone(stores):
    hall = LampCheck("hall", 3).run().pois()[0]
    attic = LampCheck("attic", 2).run().pois()[0]
    stores.update(HOME, house(3, 2).run())
    room = {"type": "Tarav.Test.Actions.RoomSuite", "key": "attic"}
    assert stores.pois.of(hall).data["event"]["suites"] == []  # the house itself detected it
    assert stores.pois.of(attic).data["event"]["suites"] == [room]

    # both lamps are off, but the attic was left out: only the hall's detector ran
    partial = stores.update(HOME, house(0, 0).run(select=without_rooms))
    assert (partial["gone"], partial["updated"]) == (1, 1)
    assert stores.pois.of(hall).exit == GONE
    assert axes(stores.pois.of(attic)) == {
        "situation": "not run", "action": "open", "closing": None}
    assert stores.update(HOME, house(0, 0).run(select=without_rooms))["updated"] == 0

    # the attic's check crashed: its suite ran and still cannot say
    crashed = stores.update(HOME, house(0, 0, crash=("attic",)).run())
    assert crashed["gone"] == 0
    assert axes(stores.pois.of(attic))["situation"] == "check failed"

    # the attic ran to its end without the POI: gone
    assert stores.update(HOME, house(0, 0).run())["gone"] == 1
    assert stores.pois.of(attic).exit == GONE


# tarav.breadcrumb d7307e455da5
def test_a_suite_that_is_no_longer_yielded_closes_its_actions(stores):
    attic = LampCheck("attic", 2).run().pois()[0]
    stores.update(HOME, house(0, 2).run())
    assert stores.pois.of(attic).state == RUNNING

    # the house ran to its end and has no attic any more: the nearest detector that ran says so
    removed = stores.update(HOME, house(0, None).run())
    assert removed["gone"] == 1 and stores.pois.of(attic).exit == GONE

    # a POI that moves under another suite takes its new chain with it
    stores.update(HOME, house(0, 2).run())
    moved = stores.update(HOME, CheckSuite([RoomSuite([LampCheck("attic", 2)], key="loft")]).run())
    assert (moved["opened"], moved["gone"], moved["updated"]) == (0, 0, 1)
    assert stores.pois.of(attic).data["event"]["suites"][0]["key"] == "loft"


def test_a_run_that_nobody_hands_over_changes_nothing(stores):
    # tarav.breadcrumb 43eea1c80003
    momentary = CheckSuite([LampCheck("hall", 3)]).run()
    assert [type(poi) for poi in momentary.pois()] == [LampOn]
    assert not stores.runs.exists()


# tarav.breadcrumb 12324a92e406
# tarav.breadcrumb a99171087407
def test_a_blessed_action_stays_closed_while_its_poi_is_still_raised(stores):
    poi = LampCheck("hall", 3).run().pois()[0]
    stores.lamps(hall=3)
    run_id = str(action_id(poi))

    with pytest.raises(ActionError):  # an operator's exit needs an operator's input
        stores.runner.close(run_id, exit=BLESSED)
    with pytest.raises(ActionError):  # gone comes from a run of the suite, not from an operator
        stores.runner.close(run_id, stores.contexts.put(BlessingInput.new(reason="x")), exit=GONE)

    empty = stores.contexts.put(BlessingInput.new(reason="  "))
    refused = stores.runner.close(run_id, empty, exit=BLESSED)
    assert refused.state == RUNNING and refused.closing_record() is None
    assert _attempts(refused)[-1]["results"][0]["pois"][0]["type"] == entity(BlessingWithoutReason).name

    stores.sessions.append({"provider": "claude-code", "session_id": "one"})
    support = [{"type": "Example.Source.Reference", "locator": {"path": "house-rules.md"}}]
    reason = stores.contexts.put(BlessingInput.new(
        reason="The hall lamp stays on at night.", support=support))
    blessed = stores.runner.close(run_id, reason, exit=BLESSED)
    assert (blessed.state, blessed.exit) == (CLOSED, BLESSED)
    record = blessed.closing_record()
    assert (record["type"], record["reason"], record["support"]) == (
        "Tarav.Blessings.Blessing", "The hall lamp stays on at night.", support)
    assert record["actor"]["session_id"] == "one" and record["poi"]["id"] == poi.identity
    home = ProjectActions(HOME, stores.runs)  # how it stands is asked of the Project
    blessing = home.blessing(poi)
    assert isinstance(blessing, Blessing) and str(blessing.id) == record["id"]
    assert (home.standing(poi), home.of(poi).id) == ("blessed", action_id(poi))
    assert ProjectActions(SHED, stores.runs).of(poi) is None  # not the shed's

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
    assert stores.pois.of(poi).closing_record()["id"] == record["id"]


# tarav.breadcrumb 95f611786d83
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

    home = ProjectActions(HOME, stores.runs)
    first, second = home.blessing(plain), home.blessing(backed)
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


def test_an_action_keeps_the_record_of_its_poi_and_reads_its_types_from_the_code(stores):
    # tarav.breadcrumb 312c3b09cec0
    from tarav.l1.actions.views import ActionResolver
    from tarav.l1.context.query import ContextQueryService

    poi = LampCheck("hall", 3).run().pois()[0]
    stores.lamps(hall=3)
    event = stores.pois.of(poi).data["event"]
    assert event["poi"] == poi.records.to_record() and "source" not in event
    assert event["poi"]["check"] == entity(LampCheck).name

    service = ContextQueryService()
    service.register_resolver("action", ActionResolver(lambda: stores.runs))
    run = service.find(poi.identity[:12])
    assert run.id == action_id(poi) and run.data["action"] == "Tarav.Actions.POI.Resolution"


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
    """A provider of checks that is not a Project."""

    def __init__(self, *checks: Check) -> None:
        self._checks = checks

    @property
    def checks(self):
        return CheckSuite(self._checks)


class _Home:
    """A Project as far as checks and actions go: it composes them as a Project does."""

    def __init__(self, root: Path, *checks, members=()) -> None:
        self.id, self.name, self.root = root.name, root.name, root
        self._checks, self._members = checks, tuple(members)

    class _Checks:
        def __init__(self, home) -> None:
            self.home = home

        def own(self):
            return CheckSuite(self.home._checks)

        def suite(self):
            return CheckSuite([self.own(), *(member.checks.suite()
                                             for member in self.home.members())])

        def run(self, **options):
            return self.suite().run(**options)

    @property
    def checks(self):
        return self._Checks(self)

    def members(self):
        return self._members

    actions = TaravProject.actions
    status = TaravProject.status


@pytest.fixture
def registry(tmp_path, monkeypatch):
    from tarav.l3.runtime import create_runtime, set_runtime

    monkeypatch.setenv("TARAV_RECORDS", str(tmp_path / "records"))
    set_runtime(create_runtime())
    yield tmp_path / "records"
    set_runtime(None)


# tarav.breadcrumb 44282e11e5c1
def test_the_status_command_updates_each_projects_actions(tmp_path, registry, capsys):
    from tarav.l1.actions import ActionRunStore

    assert report_project_status(_Home(tmp_path, LampCheck("hall", 3), _Flags(True))) == 1
    out = capsys.readouterr().out.splitlines()
    # what is open comes first, then what this run changed, each change with its id
    assert out[0] == f"{tmp_path.name}: 2 open actions"
    assert out[1] == "2 checks ran, all completed."
    assert "Changed in this run: 2 opened" in out
    lamp = LampCheck("hall", 3).run().pois()[0]
    assert f"  opened    LampOn  hall is on at 3  [{str(action_id(lamp))[:13]}]" in out
    assert out[-1] == "Open one:   tarav context --id <action-id>"
    assert any(line.startswith(f"  {tmp_path.name}  2  ") and "LampOn 1" in line for line in out)
    assert out[-2] == f"List them:  tarav action list --project {tmp_path}"
    assert "Checks by type" not in "\n".join(out)
    runs = ActionRunStore().list(project_root=str(tmp_path))
    assert {run.state for run in runs} == {"running"} and len(runs) == 2
    assert {run.data["project"]["root"] for run in runs} == {str(tmp_path)}

    # a check that crashes says nothing about what it raised: only the lamp's action closes
    assert report_project_status(
        _Home(tmp_path, LampCheck("hall", 0), _Flags(True, crash=True)), json_output=True) == 1
    acted = json.loads(capsys.readouterr().out)["actions"]
    assert (acted["opened"], acted["gone"]) == (0, 1)
    assert [project["root"] for project in acted["projects"]] == [str(tmp_path)]
    assert [signal["type"] for signal in acted["closed"]] == ["Tarav.Actions.POI.Closed"]

    # the flags are fine now: the checks no longer produce that POI either
    assert report_project_status(_Home(tmp_path, LampCheck("hall", 0), _Flags(False)),
                                 json_output=True) == 0
    assert json.loads(capsys.readouterr().out)["actions"]["gone"] == 1
    assert {run.exit for run in ActionRunStore().list(project_root=str(tmp_path))} == {"gone"}

    # a container asks its member to do the same for itself: the member's action is its own
    child = _Home(tmp_path / "child", LampCheck("bench", 2))
    assert report_project_status(_Home(tmp_path, LampCheck("hall", 0), members=(child,)),
                                 json_output=True) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["checks"]["checks"] == 2  # one result over both Projects
    assert [project["name"] for project in report["actions"]["projects"]] == [
        tmp_path.name, "child"]
    assert [(project["name"], project["open"]) for project in report["projects"]] == [
        (tmp_path.name, 0), ("child", 1)]
    assert [(change["change"], change["project"]) for change in report["changes"]] == [
        ("opened", "child")]
    # the check report is there in full, and says nothing about actions
    assert report["report"]["items"][0]["pois"] == 1
    assert "standing" not in report["report"]["items"][0]
    assert len(ActionRunStore().list(project_root=str(child.root), state="running")) == 1
    # a run on the child alone updates that same action
    assert report_project_status(_Home(child.root, LampCheck("bench", 0)), json_output=True) == 0
    assert json.loads(capsys.readouterr().out)["actions"]["gone"] == 1


# tarav.breadcrumb 168d36cc70f0
def test_the_routine_run_leaves_slow_suites_out_and_all_runs_them(tmp_path, registry, capsys):
    from tarav.l1.actions import ActionRunStore

    def home(hall: int, attic: int):
        return _Home(tmp_path, LampCheck("hall", hall),
                     AtticSuite([LampCheck("attic", attic)], key="attic"))

    attic = str(action_id(LampCheck("attic", 2).run().pois()[0]))
    assert report_project_status(home(3, 2)) == 1
    out = capsys.readouterr().out
    assert "1 checks ran, all completed." in out
    assert f"Not run: AtticSuite ({tmp_path.name}). Run everything with --all." in out
    assert ActionRunStore().find(attic) is None  # nothing is known about the attic yet

    assert report_project_status(home(3, 2), everything=True, json_output=True) == 1
    report = json.loads(capsys.readouterr().out)
    assert (report["checks"]["checks"], report["checks"]["not_run"]) == (2, [])
    assert ActionRunStore().load(attic).state == "running"

    # the lamp is off, but a routine run does not look: the action stays open,
    # and an open action is what keeps the status from being settled
    assert report_project_status(home(0, 0), json_output=True) == 1
    report = json.loads(capsys.readouterr().out)
    assert [(item["type"], item["key"], item["project"]) for item in
            report["checks"]["not_run"]] == [
        ("Tarav.Test.Actions.AtticSuite", "attic", tmp_path.name)]
    assert report["changes"] == [dict(report["changes"][0], change="gone")]  # the hall's
    assert (report["actions"]["gone"], ActionRunStore().load(attic).state) == (1, "running")
    assert ActionRunStore().load(attic).data["situation"]["state"] == "not run"

    assert report_project_status(home(0, 0), everything=True, json_output=True) == 0
    assert json.loads(capsys.readouterr().out)["actions"]["gone"] == 1
    assert ActionRunStore().load(attic).exit == "gone"

    # the check command filters the same way and touches no action
    assert report_project_checks(home(3, 2)) == 1
    assert "Not run: Tarav.Test.Actions.AtticSuite. Run everything" in capsys.readouterr().out
    assert report_project_checks(home(3, 2), everything=True, json_output=True) == 1
    assert json.loads(capsys.readouterr().out)["summary"]["pois"] == 2


# tarav.breadcrumb 6f3eab2f5865
def test_the_check_command_only_runs_the_checks(tmp_path, registry, capsys):
    from tarav.l1.actions import ActionRunStore

    home = _Home(tmp_path, LampCheck("hall", 3), members=(
        _Home(tmp_path / "child", LampCheck("bench", 2)),))
    assert report_project_checks(home, json_output=True) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["pois"] == 2 and "actions" not in report
    assert "standing" not in report["items"][0]
    assert report_project_checks(home) == 1
    assert "POI actions" not in capsys.readouterr().out
    assert not ActionRunStore().exists()


def test_a_poi_that_is_not_a_failure_does_not_make_the_run_unclean(registry, capsys):
    class Fine(Check):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(target=cls, id=TypeShip("9e484d4c-8c0d-46fe-ba05-8d6c6e7ec7ef"),
                              name="Tarav.Test.Actions.FineOnly", workflow=ACTIONS_WORKFLOW_SHIP)

        def _run(self) -> CheckResult:
            return CheckResult(self, status="completed", pois=[
                CheckPOI(self, "all is fine", situation={"case": "fine"}, failure=False)])

    assert report_project_checks(_Project(Fine())) == 0
    assert "1 checks ran, all completed. 1 POIs." in capsys.readouterr().out


def test_a_poi_that_does_not_allow_a_blessing_is_not_blessed(tmp_path, registry, capsys):
    # tarav.breadcrumb d5f905bd09bf
    from tarav.l1.actions import ActionRunStore
    from tarav.l1.operator_context import OperatorContextStore as Contexts

    flags = _Flags(True).run().pois()[0]  # a plain CheckPOI
    lamp = LampCheck("hall", 3).run().pois()[0]  # a blessable one
    home = _Home(tmp_path, _Flags(True), LampCheck("hall", 3))
    assert report_project_status(home) == 1
    capsys.readouterr()
    runner = StepRunner(runs=ActionRunStore(), contexts=Contexts(), session=lambda: None)
    reason = Contexts().put(BlessingInput.new(reason="Known and accepted."))

    refused = runner.close(str(action_id(flags)), reason, exit=BLESSED)
    assert refused.state == RUNNING
    assert _attempts(refused)[-1]["results"][0]["pois"][0]["type"] == entity(BlessingNotPermitted).name

    assert runner.close(str(action_id(lamp)), reason, exit=BLESSED).exit == BLESSED
    assert report_project_status(home) == 1  # the plain finding is still open
    out = capsys.readouterr().out
    assert f"{tmp_path.name}: 1 open action" in out and "Changed in this run: nothing" in out
    assert "  1  POI 1  (1 blessed)" in out  # the open one by Type, the blessed one counted

    # all that is raised is blessed; the checks no longer produce the flags POI, so it is gone
    assert report_project_status(_Home(tmp_path, LampCheck("hall", 3))) == 0
    assert ActionRunStore().load(str(action_id(flags))).exit == GONE
    assert ActionRunStore().load(str(action_id(lamp))).exit == BLESSED


def test_commands_print_a_summary_by_default_and_the_full_result_as_json(
        tmp_path, registry, capsys):
    # tarav.breadcrumb 2153aeae924e
    import argparse

    from tarav.l1.actions.commands import register_action_commands
    from tarav.l1.operator_context.commands import register_operator_context_commands

    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers()
    register_action_commands(commands)
    register_operator_context_commands(commands)

    def run(*words):
        args = parser.parse_args(words)
        code = args.handler(args)
        return code, capsys.readouterr().out

    lamp = LampCheck("hall", 3).run().pois()[0]
    assert report_project_status(_Home(tmp_path, LampCheck("hall", 3))) == 1
    capsys.readouterr()
    key = str(action_id(lamp))

    code, text = run("action", "list")
    assert code == 0 and text.splitlines()[0].endswith(": 1 open")
    assert f"  {key}  open, situation present  Tarav.Test.Actions.LampOn: hall is on at 3" in text
    code, dumped = run("action", "list", "--json")
    row = json.loads(dumped)["actions"][0]  # the same result, in full
    assert (row["id"], row["axes"]["action"], row["poi"]["id"]) == (key, "open", lamp.identity)

    _, placed = run("operator-context", "put", "--type", "Tarav.Blessings.Input",
                    "--data", '{"reason": " "}', "--json")
    code, text = run("action", "close", "--id", key, "--exit", "blessed",
                     "--context", json.loads(placed)["id"])
    assert code == 1 and "is still running: the exit blessed was refused." in text
    assert "Tarav.Blessings.WithoutReason: The blessing input gives no reason" in text

    _, text = run("operator-context", "put", "--type", "Tarav.Blessings.Input",
                  "--data", '{"reason": "Stays on at night."}')
    assert text.startswith("Placed Tarav.Blessings.Input ")
    context = text.split()[-1]
    assert '  reason: "Stays on at night."' in run("operator-context", "show", "--id", context)[1]
    code, text = run("action", "close", "--id", key, "--exit", "blessed", "--context", context)
    assert code == 0 and f"Action {key} closed by the exit blessed." in text
    assert "Closing record: Tarav.Blessings.Blessing" in text and "reason: Stays on at night." in text

    _, text = run("action", "show", "--id", key)
    assert "closed (blessed), situation present: Tarav.Test.Actions.LampOn" in text
    shown = json.loads(run("action", "show", "--id", key, "--json")[1])
    assert shown["closing"]["reason"] == "Stays on at night."
    assert shown["summary"]["axes"]["closing"] == "blessed"
    assert "exit blessed: by operator, leaves Tarav.Blessings.Blessing" in run("action", "types")[1]


def test_an_action_shows_its_poi_as_it_is_raised_now(stores):
    class Counted(LampCheck):
        """The same lamp, seen with a detail that is not part of its situation."""

        def __init__(self, lamp, level, seen):
            super().__init__(lamp, level)
            self.seen = seen

        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(target=cls, id=TypeShip("d9a5c3e0-7fb4-4128-8c6d-3e8a1f0b9275"),
                              name="Tarav.Test.Actions.Counted", workflow=ACTIONS_WORKFLOW_SHIP)

        def _run(self) -> CheckResult:
            return CheckResult(self, status="completed", pois=(LampOn(
                self, f"{self.lamp} is on, seen {self.seen} times",
                situation=self.situation.to_json_value(), details={"seen": self.seen}),))

    def raised(seen):
        return stores.update(HOME, CheckSuite([Counted("hall", 3, seen)]).run())

    first = raised(1)
    key = next(iter(run.id for run in stores.runs.list()))
    assert first["opened"] == 1
    again = raised(2)  # the same situation, other words and details
    assert (again["opened"], again["updated"], again["changes"]) == (0, 1, [])
    shown = stores.runs.load(str(key)).data["event"]["poi"]
    assert shown["message"] == "hall is on, seen 2 times" and shown["details"] == {"seen": 2}
    assert raised(2)["updated"] == 0  # nothing new to say


def _commit_all(repo: Path, message: str) -> str:
    """Commit every change of a test repository and return the commit."""
    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", message)
    return git("rev-parse", "HEAD")


# tarav.breadcrumb e37bdaa213b9
def test_an_action_logs_the_git_state_of_its_repositories_at_its_changes(stores, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    (repo / "house.md").write_text("lamps\n")
    first = _commit_all(repo, "one")
    repo = repo.resolve()
    root = str(repo)

    def lamps(**levels):
        return stores.update(HOME, CheckSuite([LampCheck(lamp, level) for lamp, level
                                               in levels.items()], repositories=(repo,)).run())

    poi = LampCheck("hall", 3).run().pois()[0]

    def log():
        return [(entry["type"].rsplit(".", 1)[-1].lower(), entry.get("exit"),
                 entry["repositories"][root]["commit"], entry["repositories"][root]["clean"])
                for entry in stores.pois.of(poi).data["tape"] if "repositories" in entry]

    (repo / "draft.md").write_text("draft\n")  # opened while the repository is not clean
    lamps(hall=3)
    assert log() == [("opened", None, first, False)]

    second = _commit_all(repo, "two")  # still open, now clean: logged once
    assert lamps(hall=3)["updated"] == 1
    assert lamps(hall=3)["updated"] == 0
    assert log()[1:] == [("clean", None, second, True)]

    (repo / "draft.md").write_text("fixed\n")  # gone while not clean
    lamps(hall=0)
    assert log()[2:] == [("closed", "gone", second, False)]
    third = _commit_all(repo, "three")  # the first clean state after closing
    lamps(hall=0)
    lamps(hall=0)
    assert log()[3:] == [("clean", None, third, True)]

    # reopened while clean: that entry is already the clean one of its phase
    lamps(hall=3)
    lamps(hall=3)
    assert log()[4:] == [("reopened", None, third, True)]

    # a blessing is taken outside a run: it reads the repository when it closes
    (repo / "draft.md").write_text("again\n")
    reason = stores.contexts.put(BlessingInput.new(reason="The hall lamp stays on."))
    stores.runner.close(str(action_id(poi)), reason, exit=BLESSED)
    assert log()[5:] == [("closed", BLESSED, third, False)]


def test_an_action_whose_checks_declare_no_repository_logs_nothing(stores):
    stores.lamps(hall=3)
    run = stores.pois.of(LampCheck("hall", 3).run().pois()[0])
    assert [set(entry) for entry in run.data["tape"]] == [{"type", "at"}]

