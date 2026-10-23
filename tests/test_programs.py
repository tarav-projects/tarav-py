"""Checked Program arrivals, explicit action work and durable token continuity."""

from pathlib import Path
from uuid import uuid4

import pytest

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.actions import ActionError, StepRunner
from tarav.l1.checks import CheckPOI, CheckResult, CheckSuite, SituationCheck
from tarav.l1.programs import (
    ProgramError, ProgramRun, State, StateAction, TaravProgram, Transition,
)
from tarav.l1.programs.workflow import PROGRAMS_WORKFLOW_SHIP
from tarav.l3.runtime import create_runtime


def identity(cls, suffix, name):
    return TaravClass(target=cls, id=TypeShip(f"00000000-0000-0000-0000-{suffix:012d}"),
                      name="Tests.Programs." + name, workflow=PROGRAMS_WORKFLOW_SHIP)


class ProductTextCheck(SituationCheck):
    @classmethod
    def class_entity(cls):
        return identity(cls, 8001, "ProductText.Check")

    def __init__(self, run, expected):
        super().__init__(situation={"run": str(run.id), "expected": expected})
        self.path = Path(run.typed.project["root"]) / "product.txt"
        self.expected = expected
        self.run_context = run

    def _run(self):
        if self.run_context.typed.data.get("unavailable"):
            return CheckResult(self, status="incomplete", reason="Product temporarily unavailable")
        matched = self.path.exists() and self.path.read_text() == self.expected
        return CheckResult(self, status="completed", pois=[] if matched else [self.poi(
            CheckPOI, message=f"Product must contain {self.expected}")])


class Ready(State):
    @classmethod
    def class_entity(cls):
        return identity(cls, 8002, "Ready")


class Written(State):
    @classmethod
    def class_entity(cls):
        return identity(cls, 8003, "Written")

    class Checks(State.Checks):
        def suite(self):
            return CheckSuite([ProductTextCheck(self.obj.run, "written")])


class Done(State):
    @classmethod
    def class_entity(cls):
        return identity(cls, 8004, "Done")

    class Checks(State.Checks):
        def suite(self):
            return CheckSuite([ProductTextCheck(self.obj.run, "done")])


class Write(StateAction):
    State = Written
    prompt = "Write the product before advancing."

    @classmethod
    def class_entity(cls):
        return identity(cls, 8005, "Write")


class Reset(StateAction):
    State = Ready

    @classmethod
    def class_entity(cls):
        return identity(cls, 8006, "Reset")


class Finish(StateAction):
    State = Done

    @classmethod
    def class_entity(cls):
        return identity(cls, 8007, "Finish")

    def prerequisites(self, run):
        return (ProductTextCheck(run, "done"),)


class ExampleProgram(TaravProgram):
    initial = Ready
    terminal = (Done,)
    graph = (Transition(Ready, Write), Transition(Written, Reset), Transition(Written, Finish))

    @classmethod
    def class_entity(cls):
        return identity(cls, 8008, "Example")

    def available(self, run):
        return tuple(edge for edge in super().available(run)
                     if edge.action is not Finish or run.typed.data.get("allow_finish", True))


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setenv("TARAV_RECORDS", str(tmp_path / "registry"))
    create_runtime(record_types=(ExampleProgram,))
    owner = {"id": str(uuid4()), "name": "Product", "root": str(tmp_path / "project")}
    Path(owner["root"]).mkdir()
    return ExampleProgram.runner(project=owner)


def product(runner, value):
    (Path(runner.project["root"]) / "product.txt").write_text(value)


def written(runner):
    first = runner.start()
    runner.choose(first["token"], str(entity(Write).id))
    product(runner, "written")
    return first, runner.step(first["token"])


# tarav.breadcrumb 33effb58adb2
def test_reaching_state_requires_its_checks_and_opens_real_project_actions(runner):
    assert not runner.store.root.exists()
    frame = runner.start()
    assert (frame["state"], frame["arrival"], frame["phase"]) == (str(entity(Ready).id), 0, "running")
    chosen = runner.choose(frame["token"], str(entity(Write).id))
    assert chosen["pending"]["opening"]["prompt"] == "Write the product before advancing."
    assert len(runner.actions.list(project_root=runner.project["root"])) == 2
    failed = runner.step(frame["token"])
    assert not failed["advanced"]
    assert failed["token"] == frame["token"]
    assert failed["checks"]["results"][0]["pois"][0]["message"] == "Product must contain written"
    assert runner.actions.load(chosen["pending"]["id"]).state == "running"
    product(runner, "written")
    reached = runner.step(frame["token"])
    assert reached["advanced"]
    assert reached["token"] != frame["token"]
    assert reached["state"] == str(entity(Written).id)
    action = runner.actions.load(chosen["pending"]["id"])
    assert action.state == "closed" and action.exit == "reached"
    assert action.closing_record()["state"] == str(entity(Written).id)
    assert runner.status(reached["token"])["coherent"]


# tarav.breadcrumb b5618bc96020
def test_status_reuses_state_conditions_detects_drift_and_never_rotates_token(runner):
    first, reached = written(runner)
    before = runner.store.path(reached["run"]).read_bytes()
    assert runner.status(reached["token"])["coherent"]
    product(runner, "changed after arrival")
    status = runner.status(reached["token"])
    assert not status["coherent"]
    assert status["token"] == reached["token"]
    assert runner.store.path(reached["run"]).read_bytes() == before
    with pytest.raises(ProgramError, match="incoherent"):
        runner.choose(reached["token"], str(entity(Reset).id))
    assert runner.store.path(reached["run"]).read_bytes() == before
    with pytest.raises(ProgramError, match="Stale"):
        runner.status(first["token"])


def test_cycle_arrival_issues_new_token_and_rejects_replay_without_writes(runner):
    first, reached = written(runner)
    runner.choose(reached["token"], str(entity(Reset).id))
    returned = runner.step(reached["token"])
    assert returned["state"] == first["state"]
    assert returned["arrival"] == 2
    assert returned["token"] not in (first["token"], reached["token"])
    before = runner.store.path(returned["run"]).read_bytes()
    for old in (first["token"], reached["token"]):
        with pytest.raises(ProgramError, match="Stale"):
            runner.choose(old, str(entity(Write).id))
    assert runner.store.path(returned["run"]).read_bytes() == before


def test_terminal_arrival_closes_parent_and_preserves_resume_data(runner):
    _, reached = written(runner)
    runner.choose(reached["token"], str(entity(Finish).id))
    product(runner, "done")
    final = ExampleProgram.step(reached["token"], data={"decision": "review complete"})
    assert final["advanced"] and final["phase"] == "completed"
    assert final["available"] == []
    assert all(a.state == "closed" for a in runner.actions.list(project_root=runner.project["root"]))
    reloaded = ExampleProgram.runner(project=runner.project).load(final["run"])
    assert reloaded.typed.data == {"decision": "review complete"}
    assert reloaded.typed.arrival == 2
    assert runner.status(final["token"])["coherent"]
    with pytest.raises(ProgramError, match="completed"):
        runner.choose(final["token"], str(entity(Reset).id))


def test_program_graph_and_availability_reject_illegal_answers(runner):
    first = runner.start(data={"allow_finish": False})
    with pytest.raises(ProgramError, match="available"):
        runner.choose(first["token"], str(entity(Finish).id))
    runner.choose(first["token"], str(entity(Write).id))
    with pytest.raises(ProgramError, match="pending"):
        runner.choose(first["token"], str(entity(Write).id))
    product(runner, "written")
    reached = runner.step(first["token"])
    assert [a["action"] for a in reached["available"]] == [str(entity(Reset).id)]
    with pytest.raises(ProgramError, match="available"):
        runner.choose(reached["token"], str(entity(Finish).id))


def test_incomplete_checks_cannot_issue_arrival_and_control_fields_are_not_input(runner):
    frame = runner.start()
    runner.choose(frame["token"], str(entity(Write).id))
    product(runner, "written")
    result = runner.step(frame["token"], data={"unavailable": True, "state": "pretend", "token": "forged"})
    assert not result["advanced"]
    assert result["token"] == frame["token"] and result["state"] == frame["state"]
    assert result["checks"]["results"][0]["status"] == "incomplete"
    success = runner.step(frame["token"], data={"unavailable": False})
    assert success["advanced"]
    with pytest.raises(ActionError, match="Only Step"):
        StepRunner(runs=runner.actions).start(Write, "not-an-operator-input")


def test_explicit_recovery_projects_authoritative_actions_without_new_token(runner):
    _, reached = written(runner)
    saved = runner.load(reached["run"])
    child_id = next(a["id"] for a in saved.typed.actions if a["id"] != reached["run"])
    runner.actions.map.path(child_id).unlink()
    before = runner.store.path(reached["run"]).read_bytes()
    recovered = runner.recover(reached["run"])
    assert recovered["token"] == reached["token"]
    assert runner.actions.load(child_id).state == "closed"
    assert runner.store.path(reached["run"]).read_bytes() == before


def test_wrong_program_or_project_cannot_use_a_run(runner):
    frame = runner.start()
    wrong_project = {**runner.project, "id": str(uuid4())}
    with pytest.raises(ProgramError, match="another Project"):
        ExampleProgram.runner(project=wrong_project).status(frame["token"])
    with pytest.raises(ProgramError, match="another Program"):
        TaravProgram.runner(project=runner.project).status(frame["token"])


def test_program_run_record_roundtrip_keeps_action_and_arrival_history(runner):
    _, reached = written(runner)
    run = runner.load(reached["run"])
    record = run.records.to_record()
    assert ProgramRun.records.from_record(record).records.to_record() == record
    assert [e["kind"] for e in record["history"]] == ["started", "selected", "checked", "arrived"]
