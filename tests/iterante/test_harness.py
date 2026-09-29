"""Tests for the Harness turn lifecycle."""


import pytest

from tarav.l1.iterante.harness import (
    AgentError,
    HarnessError,
    execute_turn,
    find_run_by_runtime_id,
    find_run_by_token,
)
from tarav.l1.iterante.state import create_run, load_run


@pytest.fixture
def mission_dir(tmp_path):
    md = tmp_path / "test-mission"
    md.mkdir()
    return md


def write_mission(mission_dir, code):
    # every mission reaches capabilities via `import iterante`
    (mission_dir / "mission.py").write_text("from tarav.l1 import iterante\n" + code)


class TestExecuteTurn:
    def test_first_turn_calls_setup_and_step(self, mission_dir):
        write_mission(mission_dir, """
def setup(ctx):
    ctx.state["initialized"] = True

def step(ctx):
    ctx.call = iterante.calls.task(id="t1", title="First task")
""")
        _, _, rd = create_run(mission_dir)
        result = execute_turn(rd=rd, mission_dir=mission_dir)
        assert result["call"]["type"] == "task"
        assert result["call"]["id"] == "t1"
        assert result["state"]["initialized"] is True
        assert result["tick"] == 1

    def test_second_turn_skips_setup(self, mission_dir):
        write_mission(mission_dir, """
call_log = []

def setup(ctx):
    call_log.append("setup")
    ctx.state["setup_count"] = ctx.state.get("setup_count", 0) + 1

def step(ctx):
    call_log.append("step")
    ctx.state["step_count"] = ctx.state.get("step_count", 0) + 1
    ctx.call = iterante.calls.task(id="t1", title="Work")
""")
        _, _, rd = create_run(mission_dir)
        r1 = execute_turn(rd=rd, mission_dir=mission_dir)
        result = execute_turn(rd=rd, mission_dir=mission_dir, submit_result={"answer": "done"}, token=r1["token"])
        assert result["state"]["setup_count"] == 1
        assert result["state"]["step_count"] == 2
        assert result["tick"] == 2

    def test_step_only_mission(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.call = iterante.calls.freeform(id="f1", title="Hello")
""")
        _, _, rd = create_run(mission_dir)
        result = execute_turn(rd=rd, mission_dir=mission_dir)
        assert result["call"]["type"] == "freeform"

    def test_missing_step_raises(self, mission_dir):
        write_mission(mission_dir, """
def setup(ctx):
    pass
""")
        _, _, rd = create_run(mission_dir)
        with pytest.raises(HarnessError, match="no step"):
            execute_turn(rd=rd, mission_dir=mission_dir)

    def test_no_call_raises(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    pass  # forgot to set ctx.call
""")
        _, _, rd = create_run(mission_dir)
        with pytest.raises(HarnessError, match="must set ctx.call"):
            execute_turn(rd=rd, mission_dir=mission_dir)

    def test_invalid_call_raises(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.call = "not a dict"
""")
        _, _, rd = create_run(mission_dir)
        with pytest.raises(HarnessError, match="must be a dict"):
            execute_turn(rd=rd, mission_dir=mission_dir)

    def test_call_missing_type_raises(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.call = {"id": "t1", "title": "missing type"}
""")
        _, _, rd = create_run(mission_dir)
        with pytest.raises(HarnessError, match="must have a 'type'"):
            execute_turn(rd=rd, mission_dir=mission_dir)

    def test_state_persists_across_turns(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.state["counter"] = ctx.state.get("counter", 0) + 1
    ctx.call = iterante.calls.task(id="t1", title=f"Step {ctx.state['counter']}")
""")
        _, _, rd = create_run(mission_dir)
        r1 = execute_turn(rd=rd, mission_dir=mission_dir)
        result = execute_turn(rd=rd, mission_dir=mission_dir, submit_result={}, token=r1["token"])
        assert result["state"]["counter"] == 2

    def test_completed_sets_phase(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.call = iterante.calls.completed()
""")
        _, _, rd = create_run(mission_dir)
        result = execute_turn(rd=rd, mission_dir=mission_dir)
        assert result["phase"] == "completed"
        assert result["call"]["type"] == "completed"

    def test_persist_false_does_not_write(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.state["changed"] = True
    ctx.call = iterante.calls.task(id="t1", title="Dev step")
""")
        _, _, rd = create_run(mission_dir)
        original = load_run(rd)
        execute_turn(rd=rd, mission_dir=mission_dir, persist=False)
        after = load_run(rd)
        assert original == after

    def test_step_tampering_with_state_file_hard_fails(self, mission_dir):
        write_mission(mission_dir, """
import pathlib

def step(ctx):
    # rogue/buggy step reaches into the run dir and overwrites state directly
    (pathlib.Path(ctx.env.run_dir) / "run.json").write_text("tampered")
    ctx.call = iterante.calls.task(id="t1", title="Work")
""")
        _, _, rd = create_run(mission_dir)
        with pytest.raises(HarnessError, match="run.json"):
            execute_turn(rd=rd, mission_dir=mission_dir)

    def test_normal_turn_advances_authorized_version(self, mission_dir):
        from tarav.l1.iterante.locking import verify
        write_mission(mission_dir, """
def step(ctx):
    ctx.state["n"] = ctx.state.get("n", 0) + 1
    ctx.call = iterante.calls.task(id="t1", title="Work")
""")
        _, _, rd = create_run(mission_dir)
        execute_turn(rd=rd, mission_dir=mission_dir)
        verify(rd / "run.json")  # persisted state remains the authorized version

    def test_submit_result_available_in_input(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    result = getattr(ctx.input, 'result', None)
    ctx.state["got_result"] = result
    ctx.call = iterante.calls.task(id="t1", title="Next")
""")
        _, _, rd = create_run(mission_dir)
        r1 = execute_turn(rd=rd, mission_dir=mission_dir)
        result = execute_turn(rd=rd, mission_dir=mission_dir, submit_result={"answer": "yes"}, token=r1["token"])
        assert result["state"]["got_result"] == {"answer": "yes"}


class TestSubmitContract:
    def test_branch_rejects_out_of_enum_answer(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.call = iterante.calls.branch(id="b1", title="Q", answers=["left", "right"])
""")
        _, _, rd = create_run(mission_dir)
        r1 = execute_turn(rd=rd, mission_dir=mission_dir)
        with pytest.raises(AgentError, match="one of"):
            execute_turn(rd=rd, mission_dir=mission_dir, submit_result={"answer": "up"}, token=r1["token"])

    def test_branch_accepts_listed_answer(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.call = iterante.calls.branch(id="b1", title="Q", answers=["left", "right"])
""")
        _, _, rd = create_run(mission_dir)
        r1 = execute_turn(rd=rd, mission_dir=mission_dir)
        r2 = execute_turn(rd=rd, mission_dir=mission_dir, submit_result={"answer": "left"}, token=r1["token"])
        assert r2["tick"] == 2

    def test_none_contract_rejects_payload(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.call = iterante.calls.task(id="t1", title="Work", expects=None)
""")
        _, _, rd = create_run(mission_dir)
        r1 = execute_turn(rd=rd, mission_dir=mission_dir)
        with pytest.raises(AgentError, match="no payload"):
            execute_turn(rd=rd, mission_dir=mission_dir, submit_result={"data": {"k": 1}}, token=r1["token"])

    def test_none_contract_accepts_bare_submit(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.call = iterante.calls.task(id="t1", title="Work", expects=None)
""")
        _, _, rd = create_run(mission_dir)
        r1 = execute_turn(rd=rd, mission_dir=mission_dir)
        r2 = execute_turn(rd=rd, mission_dir=mission_dir, submit_result={}, token=r1["token"])
        assert r2["tick"] == 2

    def test_typed_contract_accepts_right_shape(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.call = iterante.calls.task(id="t1", title="Work", expects={"answer": "str"})
""")
        _, _, rd = create_run(mission_dir)
        r1 = execute_turn(rd=rd, mission_dir=mission_dir)
        r2 = execute_turn(rd=rd, mission_dir=mission_dir, submit_result={"answer": "hi"}, token=r1["token"])
        assert r2["tick"] == 2

    def test_call_without_expects_accepts_anything(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.call = iterante.calls.task(id="t1", title="Work")
""")
        _, _, rd = create_run(mission_dir)
        r1 = execute_turn(rd=rd, mission_dir=mission_dir)
        r2 = execute_turn(rd=rd, mission_dir=mission_dir, submit_result={"data": {"x": 1}}, token=r1["token"])
        assert r2["tick"] == 2


class TestUnifiedToken:
    def test_first_turn_returns_token(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.call = iterante.calls.task(id="t1", title="Work")
""")
        _, _, rd = create_run(mission_dir)
        result = execute_turn(rd=rd, mission_dir=mission_dir)
        assert "token" in result
        assert len(result["token"]) == 10  # 4 prefix + 6 suffix

    def test_wrong_token_rejected(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.call = iterante.calls.task(id="t1", title="Work")
""")
        _, _, rd = create_run(mission_dir)
        execute_turn(rd=rd, mission_dir=mission_dir)
        with pytest.raises(HarnessError, match="Wrong token"):
            execute_turn(rd=rd, mission_dir=mission_dir, submit_result={}, token="wrong12345")

    def test_missing_token_rejected(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.call = iterante.calls.task(id="t1", title="Work")
""")
        _, _, rd = create_run(mission_dir)
        execute_turn(rd=rd, mission_dir=mission_dir)
        with pytest.raises(HarnessError, match="Token required"):
            execute_turn(rd=rd, mission_dir=mission_dir, submit_result={})

    def test_token_rotates_on_submit(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.call = iterante.calls.task(id="t1", title="Work")
""")
        _, _, rd = create_run(mission_dir)
        r1 = execute_turn(rd=rd, mission_dir=mission_dir)
        r2 = execute_turn(rd=rd, mission_dir=mission_dir, submit_result={}, token=r1["token"])
        assert r2["token"] != r1["token"]
        # Same prefix (same runtime)
        assert r2["token"][:4] == r1["token"][:4]

    def test_token_persisted_in_run_json(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.call = iterante.calls.task(id="t1", title="Work")
""")
        _, _, rd = create_run(mission_dir)
        result = execute_turn(rd=rd, mission_dir=mission_dir)
        run_data = load_run(rd)
        assert run_data["token"] == result["token"]


class TestFindRunByToken:
    def test_finds_run(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.call = iterante.calls.task(id="t1", title="Work")
""")
        _, token, rd = create_run(mission_dir)
        # discovery scans the home runs root and recovers mission_dir from provenance
        result = find_run_by_token(token)
        assert result is not None
        found_mission, found_rd = result
        assert found_rd == rd
        assert found_mission == mission_dir.resolve()

    def test_returns_none_for_unknown(self, mission_dir):
        result = find_run_by_token("xxxx000000")
        assert result is None


class TestFindRunByRuntimeId:
    def test_finds_run(self, mission_dir):
        write_mission(mission_dir, """
def step(ctx):
    ctx.call = iterante.calls.task(id="t1", title="Work")
""")
        runtime_id, _, rd = create_run(mission_dir)
        result = find_run_by_runtime_id(runtime_id)
        assert result is not None
        found_mission, found_rd = result
        assert found_rd == rd
        assert found_mission == mission_dir.resolve()

    def test_returns_none_for_unknown(self, mission_dir):
        assert find_run_by_runtime_id("nope000000") is None
