# $kw: ^agentos-hook-command --from Agentos.Hook.Invocation --note [DC] explicit stdin or inline JSON enters the general hook registry through the top-level agentos hook command --supp ^c20260811-16u ^c20260811-17u ^c20260811-18u ^c20260811-19u
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable

from agentos._core.errors import CliError

from .model import HookError, HookInvocation
from .registry import HookRegistry


DaemonHookSubmitter = Callable[[HookInvocation], object]


def _default_daemon_submitter(invocation: HookInvocation) -> object:
    from agentos.daemon.client import submit_hook_invocation

    return submit_hook_invocation(invocation)


def _load_context(args: argparse.Namespace) -> dict[str, object]:
    raw = sys.stdin.read() if args.ctx_from_stdin else args.ctx
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid hook context JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CliError("hook context must be a JSON object")
    return payload


def _cmd_hook(
    args: argparse.Namespace,
    registry: HookRegistry,
    *,
    daemon_submitter: DaemonHookSubmitter,
) -> int:
    try:
        invocation = HookInvocation(
            name=args.name,
            ctx=_load_context(args),
            ctx_type=args.ctx_type,
        )
    except HookError as exc:
        raise CliError(str(exc)) from exc
    registry.dispatch(invocation)
    if registry.has_callbacks(invocation.name, execution="daemon"):
        try:
            daemon_submitter(invocation.isolated_copy())
        except Exception as exc:
            from agentos.daemon.log import append_daemon_log

            append_daemon_log(
                "hook_delivery_failed",
                event_id=getattr(exc, "event_id", None),
                invocation=invocation,
                error=exc,
            )
    return 0


def register_hook_commands(
    subparsers: argparse._SubParsersAction,
    *,
    registry: HookRegistry,
    daemon_submitter: DaemonHookSubmitter = _default_daemon_submitter,
) -> None:
    parser = subparsers.add_parser(
        "hook",
        help="Dispatch a namespaced event to registered Agentos subsystem callbacks.",
    )
    parser.add_argument("--name", required=True, help="Namespaced hook identifier.")
    parser.add_argument(
        "--ctx-type",
        default=None,
        help="Optional open-string label identifying the context producer or schema.",
    )
    context = parser.add_mutually_exclusive_group(required=True)
    context.add_argument(
        "--ctx-from-stdin",
        action="store_true",
        help="Read one hook context JSON object from standard input.",
    )
    context.add_argument(
        "--ctx",
        help="Inline hook context JSON object for small manual invocations.",
    )
    parser.set_defaults(
        handler=lambda args: _cmd_hook(
            args,
            registry,
            daemon_submitter=daemon_submitter,
        )
    )


__all__ = ["register_hook_commands"]
