"""In-process facade tests — the acceptance rule: a python script must be able
to drive any iterante workflow via `import iterante` alone, never the CLI."""

import pytest

from agentos.iterante import runtime


@pytest.fixture
def project_dir(tmp_path):
    missions = tmp_path / ".agentos" / "missions" / "demo"
    missions.mkdir(parents=True)
    (missions / "mission.py").write_text("""
from agentos import iterante

def setup(ctx):
    ctx.state["step_count"] = 0

def step(ctx):
    ctx.state["step_count"] = ctx.state.get("step_count", 0) + 1
    count = ctx.state["step_count"]
    if count >= 3:
        ctx.call = iterante.calls.completed()
    else:
        ctx.call = iterante.calls.task(id=f"step-{count}", title=f"Step {count}")
""")
    return tmp_path


def test_full_mission_in_process(project_dir):
    # init → first turn
    f = runtime.init("demo", cwd=project_dir)
    assert f["call"]["title"] == "Step 1"
    assert f["call"]["type"] == "task"
    t1 = f["token"]

    # submit → advance, token rotates (same prefix)
    f2 = runtime.submit(t1, cwd=project_dir)
    assert f2["call"]["title"] == "Step 2"
    assert f2["token"] != t1
    assert f2["token"][:4] == t1[:4]

    # submit → completed (terminal)
    f3 = runtime.submit(f2["token"], cwd=project_dir)
    assert f3["call"]["type"] == "completed"


def test_completed_run_is_idempotent(project_dir):
    # drive to completion
    f = runtime.init("demo", cwd=project_dir)
    f = runtime.submit(f["token"], cwd=project_dir)
    f = runtime.submit(f["token"], cwd=project_dir)
    assert f["call"]["type"] == "completed"
    done_tick = f["tick"]

    # re-engaging a completed run re-renders the same terminal frame, no advance
    again = runtime.submit(f["token"], cwd=project_dir)
    assert again["call"]["type"] == "completed"
    assert again["tick"] == done_tick

    # request on a completed run also returns the terminal frame
    r = runtime.request(f["token"], cwd=project_dir)
    assert r["call"]["type"] == "completed"
    assert r["tick"] == done_tick


def test_request_is_read_only_in_process(project_dir):
    f = runtime.init("demo", cwd=project_dir)
    r = runtime.request(f["token"], cwd=project_dir)
    assert r["call"]["title"] == "Step 1"
    # request does not advance — token unchanged
    assert r["token"] == f["token"]


def test_dev_step_does_not_persist_in_process(project_dir):
    f = runtime.dev_step(mission="demo", cwd=project_dir)
    assert f["call"]["title"] == "Step 1"
