# $kw: ^agentos-daemon-command --from Agentos.Daemon --note [DC] run start status stop install and uninstall control one runtime; an installed user LaunchAgent owns login and crash lifecycle --supp ^c20260811-50u ^c20260811-51u ^c20260811-52u
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from collections.abc import Callable

from tarav.l0._core.errors import CliError
from tarav.l1.hooks import HookRegistry

from .client import daemon_status, request_daemon_stop
from .launchd import (
    LAUNCH_AGENT_THROTTLE_SECONDS,
    install_launch_agent,
    kickstart_launch_agent,
    launch_agent_status,
    uninstall_launch_agent,
)
from .model import daemon_socket_path
from .runtime import DaemonRuntime, DaemonRuntimeError





DAEMON_START_TIMEOUT_SECONDS = LAUNCH_AGENT_THROTTLE_SECONDS + 2.0
DAEMON_START_POLL_SECONDS = 0.05
CommandRegistrar = Callable[[argparse._SubParsersAction], None]


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
    payload["service"] = _service_status()
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    elif payload["status"] == "running":
        print(
            f"running pid={payload['pid']} "
            f"service={_service_summary(payload['service'])}"
        )
    else:
        print(f"stopped service={_service_summary(payload['service'])}")
    return 0


def _cmd_start(args: argparse.Namespace) -> int:
    status = daemon_status()
    if status is not None:
        _print_start_result(args, status="running", pid=int(status["pid"]))
        return 0

    service = _service_status()
    if service["installed"]:
        if service["loaded"]:
            kickstart_launch_agent()
        else:
            install_launch_agent(_daemon_executable())
        status = _wait_for_daemon_readiness()
        _print_start_result(args, status="started", pid=int(status["pid"]))
        return 0

    try:
        process = subprocess.Popen(
            [_daemon_executable()],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as exc:
        raise CliError("could not launch the Tarav daemon") from exc
    status = _wait_for_daemon_readiness(process=process)
    reported_status = "started" if status.get("pid") == process.pid else "running"
    _print_start_result(
        args,
        status=reported_status,
        pid=int(status["pid"]),
    )
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    _require_macos_launchd()
    if daemon_status() is not None:
        request_daemon_stop()
        _wait_for_daemon_stop()
    result = install_launch_agent(_daemon_executable())
    if result["bootstrapped"] is not True:
        kickstart_launch_agent(force=True)
    status = _wait_for_daemon_readiness()
    payload = {**result, "pid": int(status["pid"]), "status": "installed"}
    _print_payload(args, payload)
    return 0


def _cmd_uninstall(args: argparse.Namespace) -> int:
    _require_macos_launchd()
    if daemon_status() is not None:
        request_daemon_stop()
        _wait_for_daemon_stop()
    payload = {**uninstall_launch_agent(), "status": "uninstalled"}
    _print_payload(args, payload)
    return 0


def _wait_for_daemon_readiness(
    *, process: subprocess.Popen[bytes] | None = None
) -> dict[str, object]:
    deadline = time.monotonic() + DAEMON_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        status = daemon_status()
        if status is not None:
            return status
        if process is not None:
            exit_code = process.poll()
            if exit_code is not None:
                raise CliError(
                    "Tarav daemon exited before becoming ready "
                    f"(exit status {exit_code})"
                )
        time.sleep(DAEMON_START_POLL_SECONDS)
    if process is not None:
        _terminate_child(process)
    raise CliError("Tarav daemon did not become ready before the start timeout")


def _wait_for_daemon_stop() -> None:
    deadline = time.monotonic() + DAEMON_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if daemon_status() is None:
            return
        time.sleep(DAEMON_START_POLL_SECONDS)
    raise CliError("Tarav daemon did not stop before the lifecycle timeout")


def _daemon_executable() -> str:
    invoked = Path(sys.argv[0])
    if invoked.name == "tarav":
        tarav_path = invoked if invoked.is_file() else None
        if tarav_path is None:
            resolved_tarav = shutil.which(str(invoked))
            tarav_path = Path(resolved_tarav) if resolved_tarav else None
        if tarav_path is not None:
            sibling = tarav_path.resolve().with_name("tarav-daemon")
            if sibling.is_file():
                return str(sibling)
    resolved = shutil.which("tarav-daemon")
    if resolved is None:
        raise CliError("cannot locate the tarav-daemon executable")
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


def _print_payload(args: argparse.Namespace, payload: dict[str, object]) -> None:
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(payload["status"])


def _service_status() -> dict[str, object]:
    if sys.platform != "darwin":
        return {"installed": False, "loaded": False}
    return launch_agent_status()


def _service_summary(value: object) -> str:
    if not isinstance(value, dict) or value.get("installed") is not True:
        return "uninstalled"
    return "loaded" if value.get("loaded") is True else "installed"


def _require_macos_launchd() -> None:
    if sys.platform != "darwin":
        raise CliError("Tarav daemon login service currently requires macOS launchd")


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
    hook_registrar: CommandRegistrar | None = None,
) -> None:
    parser = subparsers.add_parser(
        "daemon",
        help="Run and inspect the local Tarav background worker.",
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

    install_parser = commands.add_parser(
        "install",
        help="Install and start the daemon as a user LaunchAgent.",
    )
    install_parser.add_argument("--json", action="store_true")
    install_parser.set_defaults(handler=_cmd_install)

    status_parser = commands.add_parser("status", help="Report daemon availability.")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(handler=_cmd_status)

    stop_parser = commands.add_parser("stop", help="Request a running daemon to stop.")
    stop_parser.add_argument("--json", action="store_true")
    stop_parser.set_defaults(handler=_cmd_stop)

    uninstall_parser = commands.add_parser(
        "uninstall",
        help="Stop and remove the user LaunchAgent.",
    )
    uninstall_parser.add_argument("--json", action="store_true")
    uninstall_parser.set_defaults(handler=_cmd_uninstall)

    if hook_registrar is not None:
        hook_registrar(commands)


__all__ = ["register_daemon_commands"]
