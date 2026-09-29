# $kw: --from Agent.Normal.Model
"""`agent sessions` commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from tarav.l1.agent._cli_common import format_json_output


def _cmd_agent_sessions_copy(args: argparse.Namespace) -> int:
    from tarav.l1.agent.session_copy import copy_agent_session

    payload = copy_agent_session(
        provider=args.provider,
        from_home=Path(args.from_home),
        to_home=Path(args.to_home),
        session_id=args.session,
        check=args.check,
        force=args.force,
    )
    if args.json:
        print(format_json_output(payload))
    else:
        print(_format_agent_sessions_copy(payload))
    return 0


def _format_agent_sessions_copy(payload: dict[str, object]) -> str:
    provider = payload.get("provider", "<unknown>")
    session_id = payload.get("session_id", "<unknown>")
    planned = any(
        isinstance(action, dict) and action.get("status") == "planned"
        for action in _payload_actions(payload)
    )
    verb = "Planned" if planned else "Completed"
    lines = [f"{verb} {provider} session copy: {session_id}"]
    for action in _payload_actions(payload):
        kind = action.get("kind", "<unknown>")
        status = action.get("status", "<unknown>")
        source = action.get("source_path", "<unknown>")
        destination = action.get("destination_path", "<unknown>")
        lines.append(f"  - {kind} ({status}): {source} -> {destination}")
    warnings = payload.get("warnings")
    if isinstance(warnings, list):
        for warning in warnings:
            lines.append(f"  ! {warning}")
    return "\n".join(lines)


def _payload_actions(payload: dict[str, object]) -> list[dict[str, object]]:
    actions = payload.get("actions")
    if not isinstance(actions, list):
        return []
    return [action for action in actions if isinstance(action, dict)]


def _register_sessions_commands(agent_subparsers) -> None:
    sessions_parser = agent_subparsers.add_parser(
        "sessions",
        help="Manage provider-native agent session artifacts.",
    )
    sessions_subparsers = sessions_parser.add_subparsers(
        dest="agent_sessions_command",
        required=True,
    )

    sessions_copy_parser = sessions_subparsers.add_parser(
        "copy",
        help="Copy a provider-native session artifact between provider homes.",
    )
    sessions_copy_parser.add_argument(
        "--provider",
        required=True,
        choices=("claude-code",),
        help="Provider family to copy.",
    )
    sessions_copy_parser.add_argument(
        "--from-home",
        required=True,
        help="Provider home containing the source session.",
    )
    sessions_copy_parser.add_argument(
        "--to-home",
        required=True,
        help="Provider home that should receive the session.",
    )
    sessions_copy_parser.add_argument(
        "--session",
        required=True,
        help="Native provider session id to copy.",
    )
    sessions_copy_parser.add_argument(
        "--check",
        action="store_true",
        help="Report the planned copy without mutating provider homes.",
    )
    sessions_copy_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing different destination artifact.",
    )
    sessions_copy_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON.",
    )
    sessions_copy_parser.set_defaults(handler=_cmd_agent_sessions_copy)
