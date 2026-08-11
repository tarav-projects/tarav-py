# $kw: ^agentos-daemon-command --from Agentos.Daemon --note [DC] run status and stop form the initial foreground daemon control namespace --supp ^c20260811-50u
from __future__ import annotations

import argparse
import json

from agentos._core.errors import CliError
from agentos.hooks import HookRegistry

from .client import daemon_status, request_daemon_stop
from .model import daemon_socket_path
from .runtime import DaemonRuntime, DaemonRuntimeError


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

    status_parser = commands.add_parser("status", help="Report daemon availability.")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(handler=_cmd_status)

    stop_parser = commands.add_parser("stop", help="Request a running daemon to stop.")
    stop_parser.add_argument("--json", action="store_true")
    stop_parser.set_defaults(handler=_cmd_stop)


__all__ = ["register_daemon_commands"]
