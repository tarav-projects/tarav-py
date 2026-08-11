# $kw: ^agentos-daemon-command --from Agentos.Daemon --note [DC] run start status and stop form the initial daemon control namespace; start is a manual detached launcher rather than OS lifecycle ownership --supp ^c20260811-50u ^c20260811-51u
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from agentos._core.errors import CliError
from agentos.hooks import HookRegistry

from .client import daemon_status, request_daemon_stop
from .model import daemon_socket_path
from .runtime import DaemonRuntime, DaemonRuntimeError


DAEMON_START_TIMEOUT_SECONDS = 5.0
DAEMON_START_POLL_SECONDS = 0.05


def _cmd_run(registry: HookRegistry) -> int:
    try:
        DaemonRuntime(registry).serve_forever()
    except DaemonRuntimeError as exc:
        raise CliError(str(exc)) from exc
    except KeyboardInterrupt:
        return 0
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    status = daemon_status()
    payload = status or {
        "status": "stopped",
        "socket_path": str(daemon_socket_path()),
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    elif payload["status"] == "running":
        print(f"running pid={payload['pid']}")
    else:
        print("stopped")
    return 0


def _cmd_start(args: argparse.Namespace) -> int:
    status = daemon_status()
    if status is not None:
        _print_start_result(args, status="running", pid=int(status["pid"]))
        return 0

    try:
        process = subprocess.Popen(
            [_agentos_executable(), "daemon", "run"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as exc:
        raise CliError("could not launch the Agentos daemon") from exc
    deadline = time.monotonic() + DAEMON_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        status = daemon_status()
        if status is not None:
            reported_status = (
                "started" if status.get("pid") == process.pid else "running"
            )
            _print_start_result(
                args,
                status=reported_status,
                pid=int(status["pid"]),
            )
            return 0
        exit_code = process.poll()
        if exit_code is not None:
            raise CliError(
                f"Agentos daemon exited before becoming ready (exit status {exit_code})"
            )
        time.sleep(DAEMON_START_POLL_SECONDS)

    _terminate_child(process)
    raise CliError("Agentos daemon did not become ready before the start timeout")


def _agentos_executable() -> str:
    invoked = Path(sys.argv[0])
    if invoked.name == "agentos":
        if invoked.is_file():
            return str(invoked.resolve())
        resolved = shutil.which(str(invoked))
        if resolved is not None:
            return resolved
    resolved = shutil.which("agentos")
    if resolved is None:
        raise CliError("cannot locate the agentos executable for detached daemon start")
    return resolved


def _terminate_child(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1)


def _print_start_result(args: argparse.Namespace, *, status: str, pid: int) -> None:
    if args.json:
        print(json.dumps({"status": status, "pid": pid}, sort_keys=True))
    else:
        print(f"{status} pid={pid}")


def _cmd_stop(args: argparse.Namespace) -> int:
    stopped = request_daemon_stop()
    payload = {
        "status": "stopping" if stopped else "stopped",
        "socket_path": str(daemon_socket_path()),
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(payload["status"])
    return 0


def register_daemon_commands(
    subparsers: argparse._SubParsersAction,
    *,
    registry: HookRegistry,
) -> None:
    parser = subparsers.add_parser(
        "daemon",
        help="Run and inspect the local Agentos background worker.",
    )
    commands = parser.add_subparsers(dest="daemon_command", required=True)

    run_parser = commands.add_parser("run", help="Run the daemon in the foreground.")
    run_parser.set_defaults(handler=lambda args: _cmd_run(registry))

    start_parser = commands.add_parser(
        "start",
        help="Start the daemon detached from the current terminal.",
    )
    start_parser.add_argument("--json", action="store_true")
    start_parser.set_defaults(handler=_cmd_start)

    status_parser = commands.add_parser("status", help="Report daemon availability.")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(handler=_cmd_status)

    stop_parser = commands.add_parser("stop", help="Request a running daemon to stop.")
    stop_parser.add_argument("--json", action="store_true")
    stop_parser.set_defaults(handler=_cmd_stop)


__all__ = ["register_daemon_commands"]
