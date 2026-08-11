"""Harness — the 8-phase turn lifecycle."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from types import ModuleType

from agentos.iterante import contract, locking
from agentos.iterante.ctx import Ctx
from agentos.iterante.state import (
    RUN_FILE,
    SNAPSHOT_FILE,
    load_run,
    make_token,
    runs_root,
    save_run,
    token_prefix,
)


class HarnessError(RuntimeError):
    pass


class AgentError(HarnessError):
    """An error the running agent is responsible for and should be prompted to
    correct (e.g. a wrong/missing token) — an agent-workflow error, not a
    machinery fault. Its message is about protocol, never about files, so it is
    surfaced to the agent rather than genericized. Subclasses `HarnessError`."""


def load_mission_module(path: Path) -> ModuleType:
    """Load a mission.py (or snapshot) as a Python module."""
    spec = importlib.util.spec_from_file_location("mission", path)
    if spec is None or spec.loader is None:
        raise HarnessError(f"Cannot load mission module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mission_dir_of(run_data: dict) -> Path:
    """The run's mission dir, recovered from its provenance (self-describing)."""
    return Path(run_data["provenance"]["mission_dir"])


def find_run_by_token(token: str, root: Path | None = None) -> tuple[Path, Path] | None:
    """Find a run by token, scanning the home runs root.

    Runs live under ``runs_root()/<key>/<runtime_id>``. Looks at runs whose
    runtime_id starts with the token's 4-char prefix, then matches the full
    token. Recovers mission_dir from provenance.

    Returns (mission_dir, run_dir) or None.
    """
    root = root if root is not None else runs_root()
    prefix = token_prefix(token)
    if not root.is_dir():
        return None
    for key_dir in root.iterdir():
        if not key_dir.is_dir():
            continue
        for rd in key_dir.iterdir():
            if not rd.is_dir() or not rd.name.startswith(prefix):
                continue
            try:
                run_data = load_run(rd)
            except FileNotFoundError:
                continue
            if run_data.get("token") == token:
                return _mission_dir_of(run_data), rd
    return None


def find_run_by_runtime_id(runtime_id: str, root: Path | None = None) -> tuple[Path, Path] | None:
    """Find a run by its runtime id, scanning the home runs root.

    Returns (mission_dir, run_dir) or None. Sibling of `find_run_by_token`.
    """
    root = root if root is not None else runs_root()
    if not root.is_dir():
        return None
    for key_dir in root.iterdir():
        if not key_dir.is_dir():
            continue
        rd = key_dir / runtime_id
        if rd.is_dir():
            return _mission_dir_of(load_run(rd)), rd
    return None


def execute_turn(
    *,
    rd: Path,
    mission_dir: Path,
    submit_result: dict | None = None,
    persist: bool = True,
    token: str | None = None,
) -> dict:
    """Run one full turn lifecycle.

    Phases: load state -> build ctx -> hooks (setup/step) -> validate -> persist -> return result.
    """
    # Phase 2: load state
    run_data = load_run(rd)

    # Validate token (skip for first turn — init handles it)
    if run_data["tick"] > 0:
        expected = run_data.get("token")
        if expected is not None:
            if token is None:
                raise AgentError(f"Token required. Use --token {expected}")
            if token != expected:
                raise AgentError(f"Wrong token. Expected: {expected}, got: {token}")

    # Validate the submission against the answered call's declared contract.
    # Opt-in: a call without an `expects` key skips validation (back-compat).
    is_first_turn = run_data["tick"] == 0
    prev_call = run_data.get("call")
    if not is_first_turn and isinstance(prev_call, dict) and "expects" in prev_call:
        try:
            contract.validate(prev_call["expects"], submit_result)
        except contract.ContractError as e:
            raise AgentError(str(e)) from e

    # Load snapshot
    snapshot_path = rd / SNAPSHOT_FILE
    if not snapshot_path.is_file():
        raise HarnessError(f"No {SNAPSHOT_FILE} in {rd}")
    module = load_mission_module(snapshot_path)

    # Phase 3: build ctx
    runtime_id = run_data["runtime_id"]
    env = {
        "mission_dir": str(mission_dir),
        "run_dir": str(rd),
        "runtime_id": runtime_id,
        "tick": run_data["tick"],
        "args": copy.deepcopy(run_data.get("args", {})),
    }
    input_data = {}
    if submit_result is not None:
        input_data["result"] = copy.deepcopy(submit_result)
    if run_data.get("call") is not None:
        input_data["previous_call"] = copy.deepcopy(run_data["call"])

    ctx = Ctx(env=env, state=run_data.get("state", {}), input=input_data)

    # Phase 4: hooks
    if is_first_turn and hasattr(module, "setup"):
        module.setup(ctx)

    if not hasattr(module, "step"):
        raise HarnessError("mission module has no step() function")
    module.step(ctx)

    # File.Locking: the step must not have touched the run's state files directly
    for locked in (rd / RUN_FILE, rd / SNAPSHOT_FILE):
        try:
            locking.verify(locked)
        except locking.LockViolation as e:
            raise HarnessError(f"File.Locking violation: {e}") from e

    # Phase 5: validate
    if ctx.call is None:
        raise HarnessError("step(ctx) must set ctx.call")
    if not isinstance(ctx.call, dict):
        raise HarnessError("ctx.call must be a dict")
    if "type" not in ctx.call:
        raise HarnessError("ctx.call must have a 'type' field")

    # Phase 6: persist
    next_tick = run_data["tick"] + 1
    next_phase = "completed" if ctx.call.get("type") == "completed" else "work"
    new_token = make_token(runtime_id)
    next_run_data = {
        "runtime_id": runtime_id,
        "tick": next_tick,
        "state": copy.deepcopy(ctx.state),
        "args": copy.deepcopy(run_data.get("args", {})),
        "call": copy.deepcopy(ctx.call),
        "phase": next_phase,
        "token": new_token,
        # provenance is immutable run metadata — carry it across turns so a
        # relocated run stays self-describing for discovery (state.create_run)
        "provenance": copy.deepcopy(run_data.get("provenance")),
    }
    if persist:
        save_run(rd, next_run_data)

    # Phase 7+8: render + emit handled by caller
    return {
        "call": ctx.call,
        "state": ctx.state,
        "tick": next_tick,
        "phase": next_phase,
        "runtime_id": runtime_id,
        "token": new_token,
    }
