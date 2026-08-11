# $kw: --from Iterante.Runtime
"""iterante runtime — the reusable workflow surface.

This is the library facade any caller drives: `init`, `request`, `submit`,
`resume`, `dev_step` run a full iterante workflow in-process via `import iterante`
alone. The CLI is just one caller (see `cli.py` / `runtime.main`).

The runtime runs in the caller's env (CLI ENV); it resolves the per-mission
Mission.Env and launches the in-env turn executor (`iterante._runner`) there.
Env-crossing is the runtime's job — callers never see it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from agentos.iterante._runner import FRAME_SENTINEL, parse_error
from agentos.iterante.env import ensure_iterante_importable, resolve_launch_prefix
from agentos.iterante.errors import BYPASS_ENV, dev_bypass, record_fatal
from agentos.iterante.harness import find_run_by_runtime_id, find_run_by_token
from agentos.iterante.render import render_frame
from agentos.iterante.state import create_run, load_run



def _missions_roots(cwd: Path | None = None) -> list[Path]:
    """Roots under which mission directories live, relative to a working dir."""
    base = Path(cwd) if cwd is not None else Path.cwd()
    return [base / ".agentos" / "missions", base]


def _find_mission_dir(mission_id: str, cwd: Path | None = None) -> Path:
    for root in _missions_roots(cwd):
        if (root / mission_id / "mission.py").is_file():
            return root / mission_id


    raise SystemExit(f"Mission not found: {mission_id}")


def _resolve_token(token: str, cwd: Path | None = None) -> tuple[Path, Path]:
    """Find run directory by unified token. Returns (mission_dir, run_dir).

    Run state lives in the home runs root, so resolution is cwd-independent.
    """
    result = find_run_by_token(token)
    if result:
        return result
    raise SystemExit(f"No run found for token: {token}")


def _resolve_runtime_id(runtime_id: str, cwd: Path | None = None) -> tuple[Path, Path]:
    result = find_run_by_runtime_id(runtime_id)
    if result:
        return result
    raise SystemExit(f"Runtime not found: {runtime_id}")




def _run_turn(*, rd: Path, mission_dir: Path, submit_result: dict | None = None,
              persist: bool = True, token: str | None = None) -> dict:
    """Run one turn by launching the in-env executor in the resolved Mission.Env.

    The runtime never imports the mission — it launches `iterante._runner` in the
    resolved env and parses the sentinel-marked JSON frame from its stdout.
    """
    argv = [
        *resolve_launch_prefix(mission_dir),
        "-m", "agentos.iterante._runner",
        "--run-dir", str(rd),
        "--mission-dir", str(mission_dir),
    ]
    if token is not None:
        argv += ["--token", token]
    if submit_result is not None:
        argv += ["--submit", json.dumps(submit_result)]
    if not persist:
        argv.append("--no-persist")

    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        msg = parse_error(proc.stderr)
        raise SystemExit(msg or f"turn failed (exit {proc.returncode})")

    frame = None
    for line in proc.stdout.splitlines():
        if line.startswith(FRAME_SENTINEL):
            frame = json.loads(line[len(FRAME_SENTINEL):])
        elif line:
            print(line)
    if frame is None:
        raise SystemExit("runner produced no frame")
    return frame


def parse_args(value: str | None) -> dict:
    """Parse a mission-args JSON object string (used by the CLI arg layer)."""
    if value is None:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError as e:
        raise SystemExit(f"invalid --args JSON: {e}") from e
    if not isinstance(data, dict):
        raise SystemExit("--args must be a JSON object")
    return data




def init(mission: str, args: dict | None = None, *, cwd: Path | None = None) -> dict:
    """Create a run and execute its first turn. Returns the frame."""
    mission_dir = _find_mission_dir(mission, cwd)
    ensure_iterante_importable(mission_dir)
    _, _, rd = create_run(mission_dir, mission_args=args or {})
    frame = _run_turn(rd=rd, mission_dir=mission_dir)
    return {**frame, "mission_id": mission}


def resume(runtime_id: str, *, cwd: Path | None = None) -> dict:
    """Reopen an existing run by runtime id (no turn executed)."""
    mission_dir, rd = _resolve_runtime_id(runtime_id, cwd)
    run_data = load_run(rd)
    return {
        "runtime_id": run_data["runtime_id"],
        "token": run_data["token"],
        "mission_id": mission_dir.name,
    }


def _terminal_frame(mission_dir: Path, run_data: dict) -> dict:
    """The stored completion frame, re-rendered as-is."""
    return {
        "call": run_data["call"],
        "token": run_data["token"],
        "tick": run_data["tick"],
        "mission_id": mission_dir.name,
    }


def request(token: str, *, cwd: Path | None = None) -> dict:
    """Show the current call for a run (read-only; no advance)."""
    mission_dir, rd = _resolve_token(token, cwd)
    run_data = load_run(rd)
    if run_data.get("call") is None:
        raise SystemExit("No active call for this runtime.")
    return _terminal_frame(mission_dir, run_data)


def submit(token: str, *, answer: str | None = None, data: dict | None = None,
           cwd: Path | None = None) -> dict:
    """Submit a result and advance one turn. Returns the next frame."""
    mission_dir, rd = _resolve_token(token, cwd)
    run_data = load_run(rd)


    if run_data.get("phase") == "completed":
        return _terminal_frame(mission_dir, run_data)
    submit_result: dict = {}
    if answer is not None:
        submit_result["answer"] = answer
    if data is not None:
        submit_result["data"] = data
    frame = _run_turn(rd=rd, mission_dir=mission_dir, submit_result=submit_result, token=token)
    return {**frame, "mission_id": mission_dir.name}


def dev_step(mission: str | None = None, token: str | None = None, *,
             cwd: Path | None = None) -> dict:
    """Dry-run one step without persisting state."""
    if token:
        mission_dir, rd = _resolve_token(token, cwd)
        mission_id = mission_dir.name
    else:
        if not mission:
            raise SystemExit("dev step requires a mission id or a token")
        mission_dir = _find_mission_dir(mission, cwd)
        _, _, rd = create_run(mission_dir)
        mission_id = mission
    frame = _run_turn(rd=rd, mission_dir=mission_dir, persist=False)
    return {**frame, "mission_id": mission_id}




def _render(frame: dict) -> None:
    print(render_frame(
        call=frame["call"], token=frame["token"],
        tick=frame["tick"], mission_id=frame["mission_id"],
    ))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iterante", description="Iterante agent harness CLI")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="developer: disable leak redaction and show full errors (sets ITERANTE_NO_REDACT)",
    )
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Start a new run or resume an existing one")
    p_init.add_argument("--mission", help="Mission ID to start")
    p_init.add_argument("--resume", help="Runtime ID to resume")
    p_init.add_argument("--args", help="Mission args as a JSON object")

    p_req = sub.add_parser("request", help="Show current call for a runtime")
    p_req.add_argument("--token", required=True, help="Unified token")

    p_sub = sub.add_parser("submit", help="Submit result and advance")
    p_sub.add_argument("--token", required=True, help="Unified token")
    p_sub.add_argument("--answer", help="Answer value")
    p_sub.add_argument("--data", help="JSON data payload")

    p_dev = sub.add_parser("dev", help="Developer commands")
    dev_sub = p_dev.add_subparsers(dest="dev_command")
    p_dev_step = dev_sub.add_parser("step", help="Dry-run one step")
    p_dev_step.add_argument("--mission", help="Mission ID")
    p_dev_step.add_argument("--token", help="Unified token (use existing run state)")
    return parser


def _dispatch(parser: argparse.ArgumentParser, args) -> None:
    if args.command == "init":
        if args.resume:
            r = resume(args.resume)

            print(f"Token: {r['token']}")
            return
        if not args.mission:
            raise SystemExit("init requires --mission <id> or --resume <runtime-id>")
        result = init(args.mission, parse_args(args.args))
        _render(result)
    elif args.command == "request":
        _render(request(args.token))
    elif args.command == "submit":
        data = json.loads(args.data) if args.data else None
        _render(submit(args.token, answer=args.answer, data=data))
    elif args.command == "dev":
        if args.dev_command == "step":
            if not args.token and not args.mission:
                raise SystemExit("dev step requires --mission <id> or --token <token>")
            result = dev_step(mission=args.mission, token=args.token)
            print("[dev step — no state written]")
            print()
            _render(result)
            print("---")
            print("State after step:")
            print(json.dumps(result["state"], indent=2))
        else:
            parser.parse_args(["dev", "--help"])
    else:
        parser.print_help()


def main(argv: list[str] | None = None) -> None:
    """argv → facade → render. The CLI is a one-line shim over this."""
    parser = _build_parser()
    args = parser.parse_args(argv)



    if args.raw:
        os.environ[BYPASS_ENV] = "1"




    try:
        _dispatch(parser, args)
    except Exception as e:
        raise SystemExit(record_fatal(e, log_dir=None, verbose=dev_bypass())) from e
