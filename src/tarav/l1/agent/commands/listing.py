# $kw: --from Agent.Normal.Model
"""`agent list` command."""

from __future__ import annotations

import argparse
from pathlib import Path

from tarav.l1.agent._cli_common import format_json_output
from tarav.l1.agent.commands._shared import (
    _AGENT_PROVIDER_CHOICES,
    _add_project_argument,
    _config_start_path,
)
from tarav.l1.agent.primitives import AgentConfig
from tarav.l1.agent.providers.registry import load_configured_agents


def _list_configured_agents(
    *,
    provider: str | None,
    start_path: Path,
) -> tuple[AgentConfig, ...]:
    agents = load_configured_agents(start_path=start_path)
    if provider is None:
        return agents
    return tuple(agent for agent in agents if agent.provider == provider)


def _format_instance_line(agent: AgentConfig) -> str:
    profile_id = agent.profile_id or "<default>"
    suffix_parts: list[str] = [f"id={profile_id}"]
    if agent.label is not None and agent.label != agent.profile_id:
        suffix_parts.append(agent.label)
    if agent.default_model is not None:
        suffix_parts.append(f"model={agent.default_model}")
    if agent.account is not None:
        suffix_parts.append(f"account={agent.account.account}")
    if agent.account_policy != "profile-default":
        suffix_parts.append(f"account_policy={agent.account_policy}")
    if agent.home is not None:
        suffix_parts.append(f"home={agent.home}")

    return f"{agent.provider} [{'; '.join(suffix_parts)}]"


def _cmd_agent_list(args: argparse.Namespace) -> int:
    config_start_path = _config_start_path(args)
    agents = _list_configured_agents(
        provider=args.provider,
        start_path=config_start_path,
    )
    if args.json:
        payload = {
            "agents": [agent.summary() for agent in agents],
        }
        print(format_json_output(payload))
        return 0

    if not agents:
        if args.provider is None:
            print("No agents configured.")
        else:
            print(f"No agents configured for provider {args.provider}.")
        return 0

    for agent in agents:
        print(_format_instance_line(agent))
    return 0


def _register_list_command(agent_subparsers) -> None:
    list_parser = agent_subparsers.add_parser(
        "list",
        help="List available configured agents.",
    )
    list_parser.add_argument(
        "--provider",
        default=None,
        choices=_AGENT_PROVIDER_CHOICES,
        help="Optional provider family filter.",
    )
    _add_project_argument(list_parser)
    list_parser.add_argument(
        "--json",
        action="store_true",
        help="Print agents as JSON.",
    )
    list_parser.set_defaults(handler=_cmd_agent_list)
