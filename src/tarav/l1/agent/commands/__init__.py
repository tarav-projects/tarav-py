"""Agent command registration, split by command domain."""

from __future__ import annotations

import argparse

from tarav.l1.agent.commands.accounts import _register_accounts_commands
from tarav.l1.agent.commands.listing import _register_list_command
from tarav.l1.agent.commands.profiles import _register_profiles_commands
from tarav.l1.agent.commands.run import _register_run_commands
from tarav.l1.agent.commands.sessions import _register_sessions_commands


def register_agent_commands(subparsers: argparse._SubParsersAction) -> None:
    agent_parser = subparsers.add_parser(
        "agent",
        help="Run configured agents with global/project config resolution.",
    )
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command")
    _register_list_command(agent_subparsers)
    _register_accounts_commands(agent_subparsers)
    _register_sessions_commands(agent_subparsers)
    _register_profiles_commands(agent_subparsers)
    _register_run_commands(agent_subparsers)


__all__ = ["register_agent_commands"]
