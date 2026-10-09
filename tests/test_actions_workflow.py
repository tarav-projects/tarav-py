"""Step actions over the Operator Context."""

from __future__ import annotations

import pytest

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.actions import (
    ACTIONS_WORKFLOW_SHIP, CLOSED, EXIT_ERROR, EXIT_OK, RUNNING,
    ActionError, ActionRunStore, StepAction, StepRunner, register_action,
)
from tarav.l1.checks import CheckPOI, CheckResult, SituationCheck
from tarav.l1.operator_context import OperatorContext, OperatorContextStore
from tarav.l1.records import RecordRegistry
from tarav.l2.actions.blessing import BlessingInput
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


class FlagStep(StepAction):
    """Opens when `ready` is set and closes when `done` is set."""

    operations = ("note",)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("c94e1f7b-6a28-4d53-b1e9-2f8a7c6d5e04"),
                          name="Tarav.Test.Actions.FlagStep", workflow=ACTIONS_WORKFLOW_SHIP)

    def opening_checks(self, run, context):
        return (FlagCheck(context, "ready"),)

    def closing_checks(self, run, context):
        return (FlagCheck(context, "done"),)

    def operate(self, name, run, context):
        return {"noted": context.fields.get("note")}

    def output(self, run, context):
        return {"done": True}


register_action(FlagStep)


class Stores:
    def __init__(self, root, records, session=lambda: None):
        registry = RecordRegistry(root, records)
        self.contexts = OperatorContextStore(registry)
        self.runs = ActionRunStore(registry)
        self.sessions = [session()]
        self.runner = StepRunner(runs=self.runs, contexts=self.contexts,
                                 session=lambda: self.sessions[-1])


@pytest.fixture
def stores(tmp_path):
    return Stores(tmp_path / "records", create_runtime().records)


def test_the_runtime_knows_the_workflows():
    runtime = create_runtime()
    assert entity(runtime.workflows.get("actions")).name == "Tarav.Workflow.Actions"
    assert entity(runtime.workflows.get("operator-context")).name == "Tarav.Workflow.OperatorContext"


def test_a_taken_object_carries_the_hash_of_what_was_read(stores):
    # tarav.breadcrumb 65c65cd244f2a56628df5570ce669f722c4ce073cd2422b4b5425c33a72e21bd
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


def test_a_step_closes_only_when_its_closing_tests_pass(stores):
    # tarav.breadcrumb c28fc3550aa16ddb3fcc94a85148439c2b74d18aa74397fbffc45aeaef40189f
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
    assert (closed.state, closed.exit, closed.data["output"]) == (CLOSED, EXIT_OK, {"done": True})
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
    # tarav.breadcrumb 17f6435403c8beffb1ff20f2cdeb934354350c655c3d19ccad10c6bb09c0dd37
    stores.sessions.append({"provider": "claude-code", "session_id": "one"})
    run = stores.runner.start(FlagStep, stores.contexts.put(OperatorContext.new(ready=True)))
    stores.runner.operate(str(run.id), "note")
    stores.sessions.append({"provider": "codex", "session_id": "two"})
    run, _ = stores.runner.operate(str(run.id), "note")
    assert [(item["provider"], item["session_id"]) for item in run.data["sessions"]] == [
        ("claude-code", "one"), ("codex", "two")]
