"""Program-owned check policy and durable, token-bound Action graph movement."""

from pathlib import Path
from uuid import uuid4

import pytest

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.actions import ActionError, StepRunner
from tarav.l1.checks import CheckPOI, CheckResult, CheckSuite, SituationCheck
from tarav.l1.programs import (
    EdgeAction, NodeAction, ProgramError, ProgramRun, TaravProgram, Transition,
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
        self.expected, self.run_context = expected, run

    def _run(self):
        if self.run_context.typed.data.get("unavailable"):
            return CheckResult(self, status="incomplete", reason="Product temporarily unavailable")
        matched = self.path.exists() and self.path.read_text() == self.expected
        return CheckResult(self, status="completed", pois=[] if matched else [self.poi(
            CheckPOI, message=f"Product must contain {self.expected}")])


class Ready(NodeAction):
    @classmethod
    def class_entity(cls):
        return identity(cls, 8002, "Ready")


class Written(NodeAction):
    @classmethod
    def class_entity(cls):
        return identity(cls, 8003, "Written")


class Done(NodeAction):
    @classmethod
    def class_entity(cls):
        return identity(cls, 8004, "Done")


class Write(EdgeAction):
    prompt = "Write the product before completing this edge."

    @classmethod
    def class_entity(cls):
        return identity(cls, 8005, "Write")


class Reset(EdgeAction):
    @classmethod
    def class_entity(cls):
        return identity(cls, 8006, "Reset")


class Finish(EdgeAction):
    @classmethod
    def class_entity(cls):
        return identity(cls, 8007, "Finish")


class ExampleProgram(TaravProgram):
    initial = (Ready,)
    terminal = (Done,)
    graph = (Transition(Ready, Write, Written), Transition(Written, Reset, Ready), Transition(Written, Finish, Done))

    @classmethod
    def class_entity(cls):
        return identity(cls, 8008, "Example")

    def available(self, run, occurrence):
        return tuple(edge for edge in super().available(run, occurrence)
                     if edge.action is not Finish or run.typed.data.get("allow_finish", True))

    def checks(self, run, occurrence, *, operation):
        requirements = {
            (entity(Ready).id, "status"): "ready",
            (entity(Written).id, "status"): "written",
            (entity(Done).id, "status"): "done",
            (entity(Done).id, "complete"): "done",
            (entity(Write).id, "status"): "working",
            (entity(Write).id, "complete"): run.typed.data.get("edge_requirement", "written"),
            (entity(Finish).id, "complete"): "done",
        }
        if run.typed.data.get("require_initial"):
            requirements[entity(Ready).id, "enter"] = "ready"
        if run.typed.data.get("certify_departure"):
            requirements[entity(Ready).id, "complete"] = "ready"
        if run.typed.data.get("require_edge_entry"):
            requirements[entity(Write).id, "enter"] = "entry"
        if run.typed.data.get("require_target_entry"):
            requirements[entity(Written).id, "enter"] = "entry"
        expected = requirements.get((occurrence.action, operation))
        return CheckSuite([ProductTextCheck(run, expected)] if expected else ())


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setenv("TARAV_RECORDS", str(tmp_path / "registry"))
    create_runtime(record_types=(ExampleProgram,))
    owner = {"id": str(uuid4()), "name": "Product", "root": str(tmp_path / "project")}
    Path(owner["root"]).mkdir()
    return ExampleProgram.runner(project=owner)


def active(frame):
    assert len(frame["active"]) == 1
    return frame["active"][0]


def product(runner, value):
    (Path(runner.project["root"]) / "product.txt").write_text(value)


def written(runner, *, data=None):
    first = runner.start(data=data)
    edge = runner.choose(active(first)["token"], str(entity(Write).id))
    product(runner, "written")
    return first, edge, runner.step(active(edge)["token"])


# tarav.breadcrumb 3390348e9ef9
# tarav.breadcrumb 306f5da86be2
def test_node_edge_node_are_real_actions_with_distinct_occurrences_and_tokens(runner):
    first = runner.start()
    node = active(first)
    assert node["role"] == "node" and node["action"] == str(entity(Ready).id)
    assert len(runner.actions.list(project_root=runner.project["root"], state="running")) == 2
    edge_frame = runner.choose(node["token"], str(entity(Write).id))
    edge = active(edge_frame)
    assert edge["role"] == "edge" and edge["token"] != node["token"] and edge["id"] != node["id"]
    assert edge["record"]["opening"]["prompt"] == "Write the product before completing this edge."
    assert runner.actions.load(node["id"]).exit == "completed"
    with pytest.raises(ProgramError, match="Stale"):
        runner.step(node["token"])
    failed = runner.step(edge["token"])
    assert failed["advanced"] is False and active(failed)["token"] == edge["token"]
    assert failed["checks"]["contexts"][0]["role"] == "edge"
    assert failed["checks"]["contexts"][0]["operation"] == "complete"
    product(runner, "written")
    reached = runner.step(edge["token"])
    assert reached["advanced"] is True and active(reached)["action"] == str(entity(Written).id)
    assert active(reached)["token"] not in (node["token"], edge["token"])
    assert runner.actions.load(edge["id"]).exit == "completed"
    assert runner.actions.load(active(reached)["id"]).state == "running"


# tarav.breadcrumb cabd179042ad
def test_program_selects_different_checks_for_node_edge_and_lifecycle(runner):
    first = runner.start(data={"edge_requirement": "edge-ok"})
    node = active(first)
    assert runner.status(node["token"])["coherent"] is False
    # Node status is not an engine-mandated departure requirement.
    edge = active(runner.choose(node["token"], str(entity(Write).id)))
    product(runner, "working")
    before = runner.store.path(first["run"]).read_bytes()
    report = runner.status(edge["token"])
    assert report["coherent"] is True
    assert report["context"] == {"occurrence": edge["id"], "action": str(entity(Write).id),
                                  "role": "edge", "operation": "status"}
    assert runner.store.path(first["run"]).read_bytes() == before
    product(runner, "edge-ok")
    reached = runner.step(edge["token"])
    assert reached["advanced"] is True
    # The Program has not selected Written's status checks as entry checks.
    assert runner.status(active(reached)["token"])["coherent"] is False


def test_program_can_require_fresh_departure_or_edge_entry_certification(runner):
    first = runner.start(data={"certify_departure": True, "require_edge_entry": True})
    token = active(first)["token"]
    blocked = runner.choose(token, str(entity(Write).id))
    assert blocked["advanced"] is False and active(blocked)["token"] == token
    assert [c["passed"] for c in blocked["checks"]["contexts"]] == [False, False]
    product(runner, "ready")
    blocked = runner.choose(token, str(entity(Write).id))
    assert [c["passed"] for c in blocked["checks"]["contexts"]] == [True, False]
    # Both requirements are deliberately incompatible: the engine does not
    # silently discard one to make the connection usable.
    assert active(blocked)["action"] == str(entity(Ready).id)
    source_only = runner.start(data={"certify_departure": True})
    allowed = runner.choose(active(source_only)["token"], str(entity(Write).id))
    assert allowed["advanced"] is True
    edge_only = runner.start(data={"require_edge_entry": True})
    product(runner, "entry")
    assert runner.choose(active(edge_only)["token"], str(entity(Write).id))["advanced"] is True


def test_failed_target_entry_and_incomplete_completion_keep_the_edge_token(runner):
    first = runner.start(data={"require_target_entry": True})
    edge = active(runner.choose(active(first)["token"], str(entity(Write).id)))
    product(runner, "written")
    blocked = runner.step(edge["token"])
    assert [c["passed"] for c in blocked["checks"]["contexts"]] == [True, False]
    assert active(blocked)["token"] == edge["token"]
    incomplete = runner.step(edge["token"], data={"unavailable": True, "state": "pretend", "token": "forged"})
    assert incomplete["advanced"] is False
    assert incomplete["checks"]["contexts"][0]["complete"] is False
    reached = runner.step(edge["token"], data={"unavailable": False, "require_target_entry": False})
    assert reached["advanced"] is True and active(reached)["token"] != "forged"
    assert "state" not in reached and reached["data"]["state"] == "pretend"


def test_cycle_revisits_action_type_with_a_new_occurrence_and_rejects_replay(runner):
    first, edge, reached = written(runner)
    reset = runner.choose(active(reached)["token"], str(entity(Reset).id))
    returned = runner.step(active(reset)["token"])
    assert active(returned)["action"] == active(first)["action"]
    assert active(returned)["id"] != active(first)["id"]
    before = runner.store.path(first["run"]).read_bytes()
    for old in (active(first), active(edge), active(reached), active(reset)):
        with pytest.raises(ProgramError, match="Stale"):
            runner.choose(old["token"], str(entity(Write).id))
    assert runner.store.path(first["run"]).read_bytes() == before


def test_terminal_node_is_an_action_and_completion_closes_the_parent(runner):
    _, _, reached = written(runner)
    finish = runner.choose(active(reached)["token"], str(entity(Finish).id))
    product(runner, "done")
    arrived = runner.step(active(finish)["token"])
    assert arrived["phase"] == "running" and active(arrived)["action"] == str(entity(Done).id)
    product(runner, "drift")
    assert runner.step(active(arrived)["token"])["advanced"] is False
    product(runner, "done")
    final = ExampleProgram.step(active(arrived)["token"], data={"decision": "review complete"})
    assert final["phase"] == "completed" and final["active"] == []
    assert all(a.state == "closed" for a in runner.actions.list(project_root=runner.project["root"]))
    assert runner.load(final["run"]).typed.data == {"decision": "review complete"}
    with pytest.raises(ProgramError, match="Stale"):
        runner.status(active(arrived)["token"])


def test_active_collection_preserves_other_branches_and_their_tokens(runner):
    class Parallel(ExampleProgram):
        initial = (Done, Done)

        @classmethod
        def class_entity(cls):
            return identity(cls, 8009, "Parallel")

    parallel = Parallel.runner(project=runner.project)
    product(runner, "done")
    first = parallel.start()
    left, right = first["active"]
    assert left["id"] != right["id"] and left["token"] != right["token"]
    remaining = parallel.step(left["token"])
    assert remaining["phase"] == "running" and active(remaining)["token"] == right["token"]
    assert parallel.actions.load(first["run"]).state == "running"
    assert parallel.status(right["token"])["coherent"] is True
    assert parallel.step(right["token"])["phase"] == "completed"


def test_graph_token_role_program_and_project_guards_fail_without_writes(runner):
    first = runner.start(data={"allow_finish": False})
    node = active(first)
    before = runner.store.path(first["run"]).read_bytes()
    for operation in (lambda: runner.choose(node["token"], str(entity(Finish).id)),
                      lambda: runner.step(node["token"]),
                      lambda: runner.status(node["token"] + "é"),
                      lambda: ExampleProgram.runner(project={**runner.project, "id": str(uuid4())}).status(node["token"]),
                      lambda: TaravProgram.runner().status(node["token"])):
        with pytest.raises(ProgramError):
            operation()
    assert runner.store.path(first["run"]).read_bytes() == before
    edge = active(runner.choose(node["token"], str(entity(Write).id)))
    before = runner.store.path(first["run"]).read_bytes()
    with pytest.raises(ProgramError, match="NodeAction"):
        runner.choose(edge["token"], str(entity(Reset).id))
    assert runner.store.path(first["run"]).read_bytes() == before
    with pytest.raises(ActionError, match="Only Step"):
        StepRunner(runs=runner.actions).start(Write, "not-an-operator-input")


def test_failed_initial_entry_or_undeclared_availability_does_not_create_storage(runner):
    with pytest.raises(ProgramError, match="Initial Action"):
        runner.start(data={"require_initial": True})
    assert not runner.store.root.exists()

    class Undeclared(ExampleProgram):
        @classmethod
        def class_entity(cls):
            return identity(cls, 8010, "Undeclared")

        def available(self, run, occurrence):
            return (Transition(Ready, Finish, Done),)

    with pytest.raises(ProgramError, match="declared"):
        Undeclared.runner(project=runner.project).start()
    assert not runner.store.root.exists()


def test_roundtrip_and_recovery_preserve_occurrences_and_history(runner):
    _, _, reached = written(runner)
    run = runner.load(reached["run"])
    record = run.records.to_record()
    assert ProgramRun.records.from_record(record).records.to_record() == record
    assert [e["kind"] for e in record["history"]] == ["started", "moved", "moved"]
    runner.actions.map.path(active(reached)["id"]).unlink()
    before = runner.store.path(reached["run"]).read_bytes()
    assert active(runner.recover(reached["run"]))["token"] == active(reached)["token"]
    assert runner.actions.load(active(reached)["id"]).state == "running"
    assert runner.store.path(reached["run"]).read_bytes() == before
    legacy = {**record, "state": str(entity(Ready).id), "token": "legacy", "pending": None, "arrival": 0}
    legacy.pop("active")
    with pytest.raises(ValueError):
        ProgramRun.records.from_record(legacy)


def test_concurrent_consumption_permits_exactly_one_move(runner):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    first = runner.start()
    barrier = Barrier(2)

    def advance():
        barrier.wait(timeout=5)
        try:
            return runner.choose(active(first)["token"], str(entity(Write).id))["advanced"]
        except ProgramError as exc:
            assert "Stale" in str(exc)
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: advance(), range(2)))
    assert sorted(results) == [False, True]
    assert len(runner.load(first["run"]).typed.history) == 2


def test_interrupted_projection_recovers_from_the_authoritative_active_collection(runner, monkeypatch):
    project_actions = runner._project_actions

    def interrupted(run):
        raise OSError("interrupted projection")

    monkeypatch.setattr(runner, "_project_actions", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        runner.start()
    identity, = runner.store.names()
    retained = runner.load(identity).records.to_record()
    assert runner.actions.list(project_root=runner.project["root"]) == []
    monkeypatch.setattr(runner, "_project_actions", project_actions)
    recovered = runner.recover(identity)
    assert active(recovered)["token"] == retained["active"][0]["token"]
    assert runner.load(identity).records.to_record() == retained
    assert len(runner.actions.list(project_root=runner.project["root"], state="running")) == 2
