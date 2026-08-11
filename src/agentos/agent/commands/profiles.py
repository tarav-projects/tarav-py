# $kw: --from Agent.Profile
"""`agent profiles` commands."""

from __future__ import annotations

import argparse
import json

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos.agent.config import profile_path, profiles_root


def _cmd_agent_profiles_show(args: argparse.Namespace) -> int:
    path = profile_path(args.id)
    if not path.exists():
        raise CliError(f"agent profile not found: {args.id}")
    print(path.read_text(), end="")
    return 0


def _agent_profile_template(profile_id: str) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "id": profile_id,
            "provider": "<provider>",
            "label": "",
            "accounts": [],
            "account_policy": "profile-default",
            "homes": [],
            "cli_command": [],
            "default_model": "",
            "run_args": [],
            "env": {},
        },
        indent=2,
    ) + "\n"


def _cmd_agent_profiles_new(args: argparse.Namespace) -> int:
    if args.id is None:
        profile_id = "<id>"
        path = profiles_root() / f"{profile_id}.json"
    else:
        validate_string_for_path(args.id, field_name="profile")
        profile_id = args.id
        path = profile_path(profile_id)
    print(path)
    print(_agent_profile_template(profile_id), end="")
    return 0


def _register_profiles_commands(agent_subparsers) -> None:
    profiles_parser = agent_subparsers.add_parser(
        "profiles",
        help="Manage agent profile files.",
    )
    profiles_subparsers = profiles_parser.add_subparsers(
        dest="agent_profiles_command",
        required=True,
    )

    profiles_show_parser = profiles_subparsers.add_parser(
        "show",
        help="Print the raw JSON of an agent profile file.",
    )
    profiles_show_parser.add_argument(
        "--id",
        required=True,
        help="Agent profile id to show.",
    )
    profiles_show_parser.set_defaults(handler=_cmd_agent_profiles_show)

    profiles_new_parser = profiles_subparsers.add_parser(
        "new",
        help="Scaffold a new agent profile file. Prints the template to stdout when --id is omitted.",
    )
    profiles_new_parser.add_argument(
        "--id",
        default=None,
        help="Agent profile id to create. Omit to print the template to stdout.",
    )
    profiles_new_parser.set_defaults(handler=_cmd_agent_profiles_new)
