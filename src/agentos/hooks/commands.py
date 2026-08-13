# $kw: ^agentos-hook-command --from Agentos.Hook.Invocation --note [DC] explicit stdin or inline JSON enters the general hook registry through the top-level agentos hook command --supp ^c20260811-16u ^c20260811-17u ^c20260811-18u ^c20260811-19u
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable

from agentos._core.errors import CliError

from .model import HookError, HookInvocation
from .registry import HookRegistry


HookInvocationSubmitter = Callable[[HookInvocation], object]
HookDeliveryFailureReporter = Callable[[HookInvocation, BaseException], object]
LOGGER = logging.getLogger("agentos.hooks")


def _unavailable_submitter(_invocation: HookInvocation) -> object:
    raise RuntimeError("no deferred hook submitter is configured")


def _log_delivery_failure(
    invocation: HookInvocation,
    error: BaseException,
) -> None:
    LOGGER.error(
        "deferred hook delivery failed: hook=%s error_type=%s",
        invocation.name,
        type(error).__name__,
    )


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
    deferred_submitter: HookInvocationSubmitter,
    delivery_failure_reporter: HookDeliveryFailureReporter,
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
            deferred_submitter(invocation.isolated_copy())
        except Exception as exc:
            delivery_failure_reporter(invocation.isolated_copy(), exc)
    return 0


def register_hook_commands(
    subparsers: argparse._SubParsersAction,
    *,
    registry: HookRegistry,
    deferred_submitter: HookInvocationSubmitter = _unavailable_submitter,
    delivery_failure_reporter: HookDeliveryFailureReporter = _log_delivery_failure,
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
            deferred_submitter=deferred_submitter,
            delivery_failure_reporter=delivery_failure_reporter,
        )
    )


__all__ = [
    "HookDeliveryFailureReporter",
    "HookInvocationSubmitter",
    "register_hook_commands",
]
