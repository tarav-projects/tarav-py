from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from agentos._core.project import normalize_project_target
from agentos._core.errors import CliError
from agentos.agent.primitives import Agent
from agentos.agent.providers import load_configured_agents, resolve_agent
from agentos.agent.accounts import supported_account_provider_families
from agentos.agent.account_commands import _cmd_chat_accounts_stats
from agentos.codex.commands import (
    CODEX_HOME_ENV_VAR,
    _link_codex_auth_for_account,
    _load_codex_mux_config,
)
from agentos.providers import canonical_provider_families

_AGENT_PROVIDER_CHOICES = tuple(provider.family for provider in canonical_provider_families())
_AGENT_ACCOUNTS_PROVIDER_CHOICES = tuple(
    provider.family for provider in supported_account_provider_families()
)


def _list_configured_agents(
    *,
    provider: str | None,
    start_path: Path,
) -> tuple[Agent, ...]:
    instances = load_configured_agents(start_path=start_path)
    if provider is None:
        return instances
    return tuple(instance for instance in instances if instance.provider == provider)


def _format_instance_line(agent: Agent) -> str:
    instance_id = agent.instance_id or "<default>"
    suffix_parts: list[str] = [f"id={instance_id}"]
    if agent.label is not None and agent.label != agent.instance_id:
        suffix_parts.append(agent.label)
    if agent.default_model is not None:
        suffix_parts.append(f"model={agent.default_model}")
    if agent.homes:
        homes_text = ", ".join(f"{key}={path}" for key, path in agent.homes)
        suffix_parts.append(f"homes={homes_text}")

    return f"{agent.provider} [{'; '.join(suffix_parts)}]"


def _config_start_path(args: argparse.Namespace) -> Path:
    if args.project is not None:
        return normalize_project_target(args.project)
    return Path.cwd().resolve()


def _cmd_agent_list(args: argparse.Namespace) -> int:
    config_start_path = _config_start_path(args)
    agents = _list_configured_agents(
        provider=args.provider,
        start_path=config_start_path,
    )
    if args.json:
        payload = {
            "instances": [agent.summary() for agent in agents],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
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


def _resolve_prompt(prompt_parts: list[str]) -> str:
    if prompt_parts and prompt_parts[0] == "--":
        prompt_parts = prompt_parts[1:]
    if prompt_parts:
        return " ".join(prompt_parts)
    if sys.stdin.isatty():
        raise CliError("prompt is required (pass it after -- or pipe stdin)")
    prompt = sys.stdin.read()
    if not prompt.strip():
        raise CliError("prompt is empty")
    return prompt


def _format_agent_run_command(
    command: tuple[str, ...],
    *,
    env_overrides: dict[str, str],
) -> str:
    if not env_overrides:
        return shlex.join(command)

    env_prefix = " ".join(
        f"{key}={shlex.quote(value)}"
        for key, value in sorted(env_overrides.items())
    )
    return f"{env_prefix} {shlex.join(command)}"


def _single_agent_home(agent: Agent) -> Path | None:
    if not agent.homes:
        return None
    for key, home in agent.homes:
        if key == "home":
            return home
    if len(agent.homes) == 1:
        return agent.homes[0][1]
    return None


def _prepare_account_run(
    args: argparse.Namespace,
    *,
    agent: Agent,
    env_overrides: dict[str, str],
) -> list[str]:
    link_lines: list[str] = []
    if agent.provider == "codex":
        codex_home = _single_agent_home(agent)
        if codex_home is not None:
            env_overrides[CODEX_HOME_ENV_VAR] = str(codex_home)
        if args.account is None:
            return link_lines
        if codex_home is None:
            raise CliError("--account for provider codex requires a configured or explicit --home")
        source_auth, destination_auth = _link_codex_auth_for_account(
            args.account,
            codex_home=codex_home,
            config=_load_codex_mux_config(),
            mutate=not args.dry_run,
        )
        if args.dry_run:
            link_lines.append(f"link {destination_auth} -> {source_auth}")
        return link_lines

    if args.account is not None:
        raise CliError(f"--account is not supported for provider {agent.provider}")
    return link_lines


def _cmd_agent_run(args: argparse.Namespace) -> int:
    config_start_path = _config_start_path(args)
    cwd = Path(args.cwd).expanduser().resolve() if args.cwd else Path.cwd().resolve()
    agent = resolve_agent(
        provider=args.provider,
        profile=args.profile,
        start_path=config_start_path,
        home=args.home,
    )
    prompt = _resolve_prompt(args.prompt)
    resolved_run = agent.resolve_run(prompt=prompt, model=args.model)
    env_overrides = resolved_run.env_mapping()
    account_lines = _prepare_account_run(
        args,
        agent=agent,
        env_overrides=env_overrides,
    )

    env = os.environ.copy()
    env.update(env_overrides)

    if args.dry_run:
        for line in account_lines:
            print(line)
        print(_format_agent_run_command(resolved_run.command, env_overrides=env_overrides))
        return 0

    try:
        result = subprocess.run(
            list(resolved_run.command),
            cwd=str(cwd),
            env=env,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CliError(f"agent executable not found: {exc.filename}") from exc
    return int(result.returncode)


def register_agent_commands(subparsers: argparse._SubParsersAction) -> None:
    agent_parser = subparsers.add_parser(
        "agent",
        help="Run configured agents with global/project config resolution.",
    )
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command")

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
    list_parser.add_argument(
        "--project",
        nargs="?",
        type=Path,
        const=Path("."),
        default=None,
        help="Config start path for project-local config discovery. Bare --project uses current pwd. Agent commands do not require an existing project.",
    )
    list_parser.add_argument(
        "--json",
        action="store_true",
        help="Print agents as JSON.",
    )
    list_parser.set_defaults(handler=_cmd_agent_list)

    accounts_parser = agent_subparsers.add_parser(
        "accounts",
        help="Query configured account status across supported providers.",
    )
    accounts_subparsers = accounts_parser.add_subparsers(
        dest="agent_accounts_command",
        required=True,
    )

    accounts_stats_parser = accounts_subparsers.add_parser(
        "stats",
        help="Aggregate configured account status and usage checks across supported providers.",
    )
    accounts_stats_parser.add_argument(
        "instance_ids",
        nargs="*",
        help="Optional configured account instance ids to query. Defaults to configured agent.accounts.instance_ids or all supported instances.",
    )
    accounts_stats_parser.add_argument(
        "--provider",
        choices=_AGENT_ACCOUNTS_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help="Restrict checks to a provider. Repeat to include multiple providers.",
    )
    accounts_stats_parser.add_argument(
        "--output",
        choices=("json", "markdown", "usage"),
        default="json",
        dest="output_format",
        help="Output format (default: json).",
    )
    accounts_stats_parser.add_argument(
        "--full-output",
        action="store_true",
        help="Keep zero-account provider diagnostics in the providers array.",
    )
    accounts_stats_parser.add_argument(
        "--refresh-usage",
        action="store_true",
        help=(
            "Allow provider adapters to issue live refresh requests for usage data when needed "
            "(for example Claude Code)."
        ),
    )
    accounts_stats_parser.add_argument(
        "--loop",
        action="store_true",
        help="Refresh forever every 60 seconds; press Enter to refresh immediately.",
    )
    accounts_stats_parser.add_argument(
        "--project",
        nargs="?",
        type=Path,
        const=Path("."),
        default=None,
        help="Config start path for project-local config discovery. Bare --project uses current pwd. Agent commands do not require an existing project.",
    )
    accounts_stats_parser.set_defaults(handler=_cmd_chat_accounts_stats)

    run_parser = agent_subparsers.add_parser(
        "run",
        help="Run one configured agent with a prompt.",
    )
    run_parser.add_argument(
        "--provider",
        required=True,
        choices=_AGENT_PROVIDER_CHOICES,
        help="Provider family to run.",
    )
    run_parser.add_argument(
        "--profile",
        default=None,
        help="Configured agent profile id. Optional when provider resolution is unambiguous.",
    )
    run_parser.add_argument(
        "--home",
        default=None,
        help="Provider home override for this run.",
    )
    run_parser.add_argument(
        "--account",
        default=None,
        help="Provider account/auth identity for this run.",
    )
    run_parser.add_argument(
        "--model",
        default=None,
        help="Model override.",
    )
    run_parser.add_argument(
        "--project",
        nargs="?",
        type=Path,
        const=Path("."),
        default=None,
        help="Config start path for project-local config discovery. Bare --project uses current pwd. Agent commands do not require an existing project.",
    )
    run_parser.add_argument(
        "--cwd",
        default=None,
        help="Working directory override for the launched agent process (default: current directory).",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved command instead of running it.",
    )
    run_parser.add_argument(
        "prompt",
        nargs=argparse.REMAINDER,
        help="Prompt to pass after --, or omit and pipe stdin.",
    )
    run_parser.set_defaults(handler=_cmd_agent_run)
