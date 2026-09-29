"""Behavior tests for Mission.Env subprocess execution."""

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tarav.l1.iterante.runtime import _run_turn
from tarav.l1.iterante.state import create_run

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def secondary_venv(tmp_path_factory):
    """A second venv with `iterante` installed, to prove cross-interpreter execution."""
    venv = tmp_path_factory.mktemp("secondary") / "venv"
    subprocess.run(["uv", "venv", str(venv)], check=True, capture_output=True)
    py = venv / "bin" / "python"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(py), "-e", str(PROJECT_ROOT)],
        check=True, capture_output=True,
    )
    return venv

PID_MISSION = """
    import os, sys
    from tarav.l1 import iterante
    def step(ctx):
        ctx.state["pid"] = os.getpid()
        ctx.state["executable"] = sys.executable
        ctx.state["prefix"] = sys.prefix
        ctx.call = iterante.calls.task(id="t", title="t")
"""


def _write_mission(mission_dir: Path, body: str) -> None:
    mission_dir.mkdir(parents=True, exist_ok=True)
    (mission_dir / "mission.py").write_text(textwrap.dedent(body))


def test_turn_runs_in_subprocess_not_in_caller(tmp_path):
    mission_dir = tmp_path / "demo"
    _write_mission(mission_dir, PID_MISSION)
    _, _, rd = create_run(mission_dir)

    result = _run_turn(rd=rd, mission_dir=mission_dir)

    # the turn executed in a launched subprocess, not the caller (test) process
    assert result["state"]["pid"] != os.getpid()
    assert result["call"]["title"] == "t"


def test_default_env_uses_caller_interpreter(tmp_path):
    mission_dir = tmp_path / "demo"
    _write_mission(mission_dir, PID_MISSION)
    _, _, rd = create_run(mission_dir)

    result = _run_turn(rd=rd, mission_dir=mission_dir)

    # default env (no mission.json) resolves to the CLI's own interpreter
    assert result["state"]["executable"] == sys.executable


def test_declared_interpreter_path_runs_in_that_env(tmp_path, secondary_venv):
    mission_dir = tmp_path / "demo"
    _write_mission(mission_dir, PID_MISSION)
    py = secondary_venv / "bin" / "python"
    (mission_dir / "mission.json").write_text(json.dumps({"env": str(py)}))
    _, _, rd = create_run(mission_dir)

    result = _run_turn(rd=rd, mission_dir=mission_dir)

    # the turn ran under the declared interpreter, not the caller's
    assert result["state"]["executable"] != sys.executable
    assert Path(result["state"]["prefix"]) == secondary_venv.resolve()


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv required for uv-project env")
def test_uv_project_env_runs_in_project_venv(tmp_path):
    proj = tmp_path / "envproj"
    proj.mkdir()
    (proj / "pyproject.toml").write_text(textwrap.dedent(f"""
        [project]
        name = "mission-env"
        version = "0.0.0"
        requires-python = ">=3.12"
        dependencies = ["tarav"]

        [tool.uv.sources]
        tarav = {{ path = "{PROJECT_ROOT}", editable = true }}
    """))
    mission_dir = tmp_path / "demo"
    _write_mission(mission_dir, PID_MISSION)
    (mission_dir / "mission.json").write_text(json.dumps({"env": str(proj)}))
    _, _, rd = create_run(mission_dir)

    result = _run_turn(rd=rd, mission_dir=mission_dir)

    # the turn ran in the uv project's own venv
    assert result["state"]["executable"] != sys.executable
    assert Path(result["state"]["prefix"]) == (proj / ".venv").resolve()


def test_env_without_iterante_fails_fast(tmp_path):
    bare = tmp_path / "bare"
    subprocess.run(["uv", "venv", str(bare)], check=True, capture_output=True)
    py = bare / "bin" / "python"
    mission_dir = tmp_path / "demo"
    _write_mission(mission_dir, PID_MISSION)
    (mission_dir / "mission.json").write_text(json.dumps({"env": str(py)}))

    from tarav.l1.iterante.env import ensure_iterante_importable

    with pytest.raises(SystemExit) as ei:
        ensure_iterante_importable(mission_dir)

    # actionable error naming both the missing dependency and the offending env
    msg = str(ei.value)
    assert "iterante" in msg
    assert str(py) in msg
