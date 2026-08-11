"""Run state persistence — run.json load/save and mission.py snapshot."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import secrets
import shutil
from pathlib import Path

from agentos.iterante import locking

RUN_FILE = "run.json"
SNAPSHOT_FILE = "_mission-snap.py"

RUNTIME_ID_BYTES = 8
PREFIX_LEN = 4
SUFFIX_BYTES = 3  # 3 bytes -> 6 hex chars


def generate_runtime_id() -> str:
    return secrets.token_hex(RUNTIME_ID_BYTES)


def state_home() -> Path:
    """Base dir for iterante's out-of-repo run state.

    Defaults to ``~/.agentos`` so run internals live outside any project working
    tree (an agent in the repo can't stumble on them). ``ITERANTE_STATE_HOME``
    overrides it — the test seam, so suites never touch the real home.
    """
    env = os.environ.get("ITERANTE_STATE_HOME")
    return Path(env) if env else Path.home() / ".agentos"


def runs_root() -> Path:
    return state_home() / "iterante" / "runs"


def _mission_key(mission_dir: Path) -> str:
    """A tidy, collision-safe namespace bucket for a mission's runs.

    ``<mission_id>-<hash8>`` — the id alone collides across repos; the hash of
    the absolute mission dir disambiguates. Format is cosmetic; discovery does
    not depend on it (it scans + reads provenance).
    """
    digest = hashlib.sha256(str(mission_dir.resolve()).encode()).hexdigest()[:8]
    return f"{mission_dir.name}-{digest}"


def make_token(runtime_id: str) -> str:
    """Build a unified token: 4-char runtime prefix + 6-char random suffix."""
    return token_prefix(runtime_id) + secrets.token_hex(SUFFIX_BYTES)


def token_prefix(token: str) -> str:
    return token[:PREFIX_LEN]


def run_dir(mission_dir: Path, runtime_id: str) -> Path:
    return runs_root() / _mission_key(mission_dir) / runtime_id


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
    locking.record(snapshot)  # authorize the frozen mission code

    token = make_token(runtime_id)
    initial_state = {
        "runtime_id": runtime_id,
        "tick": 0,
        "state": {},
        "args": mission_args or {},
        "call": None,
        "phase": "init",
        "token": token,
        # Provenance — the run is self-describing wherever it lives, so discovery
        # recovers the mission location without relying on the dir structure.
        "provenance": {
            "mission_dir": str(mission_dir.resolve()),
            "mission_id": mission_dir.name,
            "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        },
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
    locking.record(run_file)  # legal write: re-authorize the new run state
