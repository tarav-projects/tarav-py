# $kw: --from Iterante.Driver
"""iterante2 CLI — init, request, submit, dev step."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from tarav.l1.iterante2._runner import FRAME_SENTINEL, parse_error
from tarav.l1.iterante2.env import ensure_iterante_importable, resolve_launch_prefix
from tarav.l1.iterante2.errors import BYPASS_ENV, dev_bypass, record_fatal
from tarav.l1.iterante2.harness import find_run_by_runtime_id, find_run_by_token
from tarav.l1.iterante2.render import render_frame
from tarav.l1.iterante2.state import create_run, load_run


def _run_turn(*, rd: Path, mission_dir: Path, submit_result: dict | None = None,
              persist: bool = True, token: str | None = None) -> dict:
    """Run one turn inside the resolved Mission.Env subprocess; return the frame dict.

    The CLI never imports the mission — it launches the runner in the resolved env
    and parses the sentinel-marked JSON frame from its stdout.
    """
    argv = [
        *resolve_launch_prefix(mission_dir),
        "-m", "tarav.l1.iterante2._runner",
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


def _load_args(value: str | None) -> dict:
    if value is None:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError as e:
        raise SystemExit(f"invalid --args JSON: {e}") from e
    if not isinstance(data, dict):
        raise SystemExit("--args must be a JSON object")
    return data


def _missions_roots() -> list[Path]:
    """Roots under which mission directories live."""
    cwd = Path.cwd()
    return [cwd / ".tarav" / "missions", cwd]


def _find_mission_dir(mission_id: str) -> Path:
    """Locate mission directory by id."""
    for root in _missions_roots():
        if (root / mission_id / "mission.py").is_file():
            return root / mission_id


    raise SystemExit(f"Mission not found: {mission_id}")


def _resolve_token(token: str) -> tuple[Path, Path]:
    """Find run directory by unified token. Returns (mission_dir, run_dir)."""
    for root in _missions_roots():
        result = find_run_by_token(root, token)
        if result:
            return result
    raise SystemExit(f"No run found for token: {token}")


def _find_run_by_runtime_id(runtime_id: str) -> tuple[Path, Path]:
    """Find run directory by runtime id (for --resume)."""
    for root in _missions_roots():
        result = find_run_by_runtime_id(root, runtime_id)
        if result:
            return result
    raise SystemExit(f"Runtime not found: {runtime_id}")


def cmd_init(args):
    if args.resume:
        mission_dir, rd = _find_run_by_runtime_id(args.resume)
        run_data = load_run(rd)
        print(f"Resumed run: {run_data['runtime_id']}")
        print(f"Token: {run_data['token']}")
        return

    if not args.mission:
        raise SystemExit("init requires --mission <id> or --resume <runtime-id>")

    mission_dir = _find_mission_dir(args.mission)
    ensure_iterante_importable(mission_dir)
    runtime_id, token, rd = create_run(mission_dir, mission_args=_load_args(args.args))


    result = _run_turn(rd=rd, mission_dir=mission_dir)

    print(f"Run created: {runtime_id}")
    print()
    print(render_frame(call=result["call"], token=result["token"], tick=result["tick"], mission_id=args.mission))


def cmd_request(args):
    mission_dir, rd = _resolve_token(args.token)
    run_data = load_run(rd)

    if run_data.get("call") is None:
        raise SystemExit("No active call for this runtime.")

    print(render_frame(
        call=run_data["call"],
        token=run_data["token"],
        tick=run_data["tick"],
        mission_id=mission_dir.name,
    ))


def cmd_submit(args):
    mission_dir, rd = _resolve_token(args.token)

    submit_result = {}
    if args.answer:
        submit_result["answer"] = args.answer
    if args.data:
        submit_result["data"] = json.loads(args.data)

    result = _run_turn(
        rd=rd, mission_dir=mission_dir, submit_result=submit_result,
        token=args.token,
    )

    print(render_frame(
        call=result["call"],
        token=result["token"],
        tick=result["tick"],
        mission_id=mission_dir.name,
    ))


def cmd_dev_step(args):
    if args.token:
        mission_dir, rd = _resolve_token(args.token)
    else:
        if not args.mission:
            raise SystemExit("dev step requires --mission <id> or --token <token>")
        mission_dir = _find_mission_dir(args.mission)
        _, _, rd = create_run(mission_dir)

    result = _run_turn(rd=rd, mission_dir=mission_dir, persist=False)

    mission_id = args.mission or mission_dir.name
    print("[dev step — no state written]")
    print()
    print(render_frame(call=result["call"], token=result["token"], tick=result["tick"], mission_id=mission_id))


    print("---")
    print("State after step:")
    print(json.dumps(result["state"], indent=2))


def main():
    parser = argparse.ArgumentParser(prog="iterante2", description="Iterante v2 agent harness CLI")
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

    args = parser.parse_args()



    if args.raw:
        os.environ[BYPASS_ENV] = "1"





    try:
        if args.command == "init":
            cmd_init(args)
        elif args.command == "request":
            cmd_request(args)
        elif args.command == "submit":
            cmd_submit(args)
        elif args.command == "dev":
            if args.dev_command == "step":
                cmd_dev_step(args)
            else:
                sub.choices["dev"].print_help()
        else:
            parser.print_help()
    except Exception as e:
        raise SystemExit(record_fatal(e, log_dir=None, verbose=dev_bypass())) from e
