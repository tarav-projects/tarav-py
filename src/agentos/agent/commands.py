from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos._core.project import normalize_project_target
from agentos._core.errors import CliError
from agentos.agent.primitives import Agent
from agentos.agent.providers import load_configured_agents, resolve_agent
from agentos.agent.accounts import supported_account_provider_families
from agentos.agent.account_commands import _cmd_chat_accounts_stats
from agentos.agent.link_runtime import AgentLinkRequest
from agentos.agent.run_runtime import AgentRunRequest
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
    if agent.home is not None:
        suffix_parts.append(f"home={agent.home}")

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


def _resolve_run_prompt(prompt: str | None, raw_argv: tuple[str, ...]) -> str | None:
    if prompt is not None and raw_argv:
        raise CliError("--prompt cannot be combined with provider arguments after --")
    if raw_argv:
        return None
    if prompt is not None:
        if not prompt.strip():
            raise CliError("--prompt is empty")
        return prompt
    return None


def _resolve_run_argv(argv_parts: list[str]) -> tuple[str, ...]:
    if argv_parts and argv_parts[0] == "--":
        argv_parts = argv_parts[1:]
    return tuple(argv_parts)


def _cmd_agent_run(args: argparse.Namespace) -> int:
    argv = _resolve_run_argv(args.argv)
    prompt = _resolve_run_prompt(args.prompt, argv)
    agent, request = _resolve_agent_run(
        args,
        prompt=prompt,
        argv=argv,
    )

    if args.dry_run:
        dry_result = agent.run_dry(request)
        for line in dry_result.lines:
            print(line)
        return 0

    result = agent.run(request)
    return result.exit_code


def _resolve_agent_run_target(args: argparse.Namespace) -> tuple[Agent, Path]:
    config_start_path = _config_start_path(args)
    cwd = Path(args.cwd).expanduser().resolve() if args.cwd else Path.cwd().resolve()
    agent = resolve_agent(
        provider=args.provider,
        profile=args.profile,
        start_path=config_start_path,
        home=args.home,
    )
    return agent, cwd


def _resolve_agent_run(
    args: argparse.Namespace,
    *,
    prompt: str | None,
    argv: tuple[str, ...],
) -> tuple[Agent, AgentRunRequest]:
    agent, cwd = _resolve_agent_run_target(args)
    return agent, _agent_run_request(
        args,
        prompt=prompt,
        argv=argv,
        cwd=cwd,
    )


def _agent_run_request(
    args: argparse.Namespace,
    *,
    prompt: str | None,
    argv: tuple[str, ...],
    cwd: Path,
) -> AgentRunRequest:
    return AgentRunRequest(
        prompt=prompt,
        argv=argv,
        model=args.model,
        cwd=cwd,
        account=args.account,
    )


def _cmd_agent_ping(args: argparse.Namespace) -> int:
    agent, cwd = _resolve_agent_run_target(args)
    if not agent.ping.enabled:
        raise CliError(
            f"agent {agent.instance_id or '<default>'} for provider {agent.provider} has ping disabled"
        )
    request = _agent_run_request(
        args,
        prompt=agent.ping.prompt,
        argv=agent.ping.argv,
        cwd=cwd,
    )
    result = agent.run(request)
    return result.exit_code


def _cmd_agent_link(args: argparse.Namespace) -> int:
    request = AgentLinkRequest(
        provider=args.provider,
        home=Path(args.home).expanduser().resolve(),
        account=args.account,
    )

    if request.provider == "codex":
        from agentos.codex.linking import link_codex_account, link_codex_account_dry

        if args.dry_run:
            dry_result = link_codex_account_dry(request)
            for line in dry_result.lines:
                print(line)
            return 0
        result = link_codex_account(request)
        return result.exit_code

    raise CliError(f"agent link is not supported for provider {request.provider}")


def _add_agent_run_target_args(
    parser: argparse.ArgumentParser,
    *,
    provider_help: str,
) -> None:
    parser.add_argument(
        "--provider",
        required=True,
        choices=_AGENT_PROVIDER_CHOICES,
        help=provider_help,
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Configured agent profile id. Optional when provider resolution is unambiguous.",
    )
    parser.add_argument(
        "--home",
        default=None,
        help="Provider home override for this run.",
    )
    parser.add_argument(
        "--account",
        default=None,
        help="Provider account/auth identity for this run.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model override.",
    )
    parser.add_argument(
        "--project",
        nargs="?",
        type=Path,
        const=Path("."),
        default=None,
        help="Config start path for project-local config discovery. Bare --project uses current pwd. Agent commands do not require an existing project.",
    )
    parser.add_argument(
        "--cwd",
        default=None,
        help="Working directory override for the launched agent process (default: current directory).",
    )


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
        help="Run one configured agent with a prompt or raw provider arguments.",
    )
    _add_agent_run_target_args(run_parser, provider_help="Provider family to run.")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved command instead of running it.",
    )
    run_parser.add_argument(
        "--prompt",
        default=None,
        help="Prompt for normalized provider prompt-run mode.",
    )
    run_parser.add_argument(
        "argv",
        nargs=argparse.REMAINDER,
        help="Raw provider arguments to pass after --.",
    )
    run_parser.set_defaults(handler=_cmd_agent_run)

    ping_parser = agent_subparsers.add_parser(
        "ping",
        help="Run a configured agent ping.",
    )
    _add_agent_run_target_args(ping_parser, provider_help="Provider family to ping.")
    ping_parser.set_defaults(handler=_cmd_agent_ping)

    link_parser = agent_subparsers.add_parser(
        "link",
        help="Link a managed provider account to an explicit provider home.",
    )
    link_parser.add_argument(
        "--provider",
        required=True,
        choices=_AGENT_PROVIDER_CHOICES,
        help="Provider family to link.",
    )
    link_parser.add_argument(
        "--home",
        required=True,
        help="Provider home to link.",
    )
    link_parser.add_argument(
        "--account",
        required=True,
        help="Managed provider account id to link.",
    )
    link_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the link action without mutating the provider home.",
    )
    link_parser.set_defaults(handler=_cmd_agent_link)
