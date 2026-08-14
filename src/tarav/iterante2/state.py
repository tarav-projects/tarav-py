# $kw: --from Run.Snapshot
"""Run state persistence — run.json load/save and mission.py snapshot."""

from __future__ import annotations

import json
import secrets
import shutil
from pathlib import Path

from tarav.iterante2 import locking

RUN_FILE = "run.json"
SNAPSHOT_FILE = "_mission-snap.py"

RUNTIME_ID_BYTES = 8
PREFIX_LEN = 4
SUFFIX_BYTES = 3


def generate_runtime_id() -> str:
    return secrets.token_hex(RUNTIME_ID_BYTES)


def make_token(runtime_id: str) -> str:
    """Build a unified token: 4-char runtime prefix + 6-char random suffix."""
    return token_prefix(runtime_id) + secrets.token_hex(SUFFIX_BYTES)


def token_prefix(token: str) -> str:
    return token[:PREFIX_LEN]


def run_dir(mission_dir: Path, runtime_id: str) -> Path:
    return mission_dir / "runs" / runtime_id


def create_run(mission_dir: Path, mission_args: dict | None = None) -> tuple[str, str, Path]:
    """Create a new run directory, snapshot mission.py, initialize run.json.

    Returns (runtime_id, token, run_directory).
    """
    runtime_id = generate_runtime_id()
    rd = run_dir(mission_dir, runtime_id)
    rd.mkdir(parents=True, exist_ok=False)

    mission_py = mission_dir / "mission.py"
    if not mission_py.is_file():
        raise FileNotFoundError(f"No mission.py found in {mission_dir}")
    snapshot = rd / SNAPSHOT_FILE
    shutil.copy2(mission_py, snapshot)
    locking.record(snapshot)

    token = make_token(runtime_id)
    initial_state = {
        "runtime_id": runtime_id,
        "tick": 0,
        "state": {},
        "args": mission_args or {},
        "call": None,
        "phase": "init",
        "token": token,
    }
    save_run(rd, initial_state)
    return runtime_id, token, rd


def load_run(rd: Path) -> dict:
    run_file = rd / RUN_FILE
    if not run_file.is_file():
        raise FileNotFoundError(f"No {RUN_FILE} in {rd}")
    return json.loads(run_file.read_text())


def save_run(rd: Path, data: dict) -> None:
    run_file = rd / RUN_FILE
    run_file.write_text(json.dumps(data, indent=2) + "\n")
    locking.record(run_file)
