from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos._core.project import normalize_project_target
from agentos._core.errors import CliError
from agentos.agent.primitives import Agent
from agentos.agent.providers import load_configured_agents, resolve_agent
from agentos.agent.run_runtime import AgentRunRequest
from agentos.providers import canonical_provider_families

_AGENT_PROVIDER_CHOICES = tuple(provider.family for provider in canonical_provider_families())
_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES = ("codex", "claude-code")


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


def _cmd_agent_accounts_register(args: argparse.Namespace) -> int:
    if args.provider == "codex":
        if args.auth_file is None:
            raise CliError("agent accounts register --provider codex requires --auth-file")
        from agentos.codex.account_registry import register_codex_account_from_auth_file

        print(
            json.dumps(
                register_codex_account_from_auth_file(
                    auth_file=Path(args.auth_file),
                    account=args.account,
                    email=args.email,
                    register_only=args.register_only,
                    argv=getattr(args, "_agentos_argv", []),
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.provider == "claude-code":
        from agentos.claude.account_registry import register_claude_account

        print(
            json.dumps(
                register_claude_account(
                    account=args.account,
                    email=args.email,
                    label=args.label,
                    argv=getattr(args, "_agentos_argv", []),
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    raise CliError(f"agent accounts register is not supported for provider {args.provider}")


def _cmd_agent_accounts_link(args: argparse.Namespace) -> int:
    if args.provider == "codex":
        from agentos.codex.account_registry import link_codex_account_to_home

        print(
            json.dumps(
                link_codex_account_to_home(
                    home=Path(args.home),
                    account=args.account,
                    force=args.force,
                    argv=getattr(args, "_agentos_argv", []),
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.provider == "claude-code":
        from agentos.claude.account_registry import link_claude_account_to_home

        print(
            json.dumps(
                link_claude_account_to_home(
                    home=Path(args.home),
                    account=args.account,
                    force=args.force,
                    argv=getattr(args, "_agentos_argv", []),
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    raise CliError(f"agent accounts link is not supported for provider {args.provider}")


def _cmd_agent_accounts_status(args: argparse.Namespace) -> int:
    if args.provider is None:
        if args.home is not None:
            raise CliError("agent accounts status --home requires --provider")
        return _cmd_agent_accounts_registry_status(args, provider=None)

    if args.provider == "codex":
        if args.home is None:
            return _cmd_agent_accounts_registry_status(args, provider=args.provider)
        from agentos.codex.account_registry import inspect_codex_account_home
        payload = inspect_codex_account_home(home=Path(args.home))
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(_format_agent_accounts_status(payload))
        return 0
    if args.home is not None:
        payload = _inspect_claimed_account_home(provider=args.provider, home=Path(args.home))
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(_format_agent_accounts_status(payload))
        return 0
    return _cmd_agent_accounts_registry_status(args, provider=args.provider)


def _cmd_agent_accounts_monitor(args: argparse.Namespace) -> int:
    from agentos.agent.monitor import RichMonitorRenderer, build_monitor_loop, dumps_monitor_json

    max_ticks = 1 if args.once else args.max_ticks
    loop = build_monitor_loop(
        start_path=_config_start_path(args),
        interval_sec=args.interval_sec,
        max_ticks=max_ticks,
    )
    try:
        if args.json:
            if max_ticks is None:
                def print_json_tick(frame, state) -> None:
                    print(dumps_monitor_json(frame, state), flush=True)

                loop.run(on_tick=print_json_tick)
                return 0

            frame, state = loop.run()
            print(dumps_monitor_json(frame, state))
            return 0

        with RichMonitorRenderer() as renderer:
            loop.run(on_tick=renderer.render)
        return 0
    except KeyboardInterrupt:
        return 130


def _inspect_claimed_account_home(*, provider: str, home: Path) -> dict[str, object]:
    from agentos.agent.account_registry import load_links

    normalized_home = str(home.expanduser().resolve())
    links = load_links(provider).get("links")
    link = links.get(normalized_home) if isinstance(links, dict) else None
    return {
        "status": "ok",
        "command": "agent accounts status",
        "provider": provider,
        "home": normalized_home,
        "classification": "claimed" if isinstance(link, dict) and link.get("kind") == "claimed" else "unlinked",
        "link_consistency": "claimed-unverified" if isinstance(link, dict) and link.get("kind") == "claimed" else "unlinked",
        "link": link if isinstance(link, dict) else None,
    }


def _cmd_agent_accounts_registry_status(args: argparse.Namespace, *, provider: str | None) -> int:
    from agentos.agent.account_registry import inspect_account_registry

    payload = inspect_account_registry(provider)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_format_agent_accounts_registry_overview(payload))
    return 0


def _format_agent_accounts_status(payload: dict[str, object]) -> str:
    lines = [
        f"Provider: {payload.get('provider', '<unknown>')}",
        f"Home: {payload.get('home', '<unknown>')}",
        f"Status: {payload.get('classification', '<unknown>')}",
    ]
    auth_path = payload.get("auth_path")
    if isinstance(auth_path, str):
        lines.insert(2, f"Auth file: {auth_path}")
    link_consistency = payload.get("link_consistency")
    if isinstance(link_consistency, str):
        lines.append(f"Link: {link_consistency}")
    auth = payload.get("auth")
    if isinstance(auth, dict):
        lines.append(f"Account ID: {auth.get('account_id', '<unknown>')}")
        email = auth.get("email")
        if isinstance(email, str):
            lines.append(f"Email: {email}")
        sha256 = auth.get("sha256")
        if isinstance(sha256, str):
            lines.append(f"SHA256: {sha256}")
    error = payload.get("error")
    if isinstance(error, str):
        lines.append(f"Error: {error}")
    registry_matches = payload.get("artifact_registry_matches")
    if isinstance(registry_matches, list):
        lines.append(f"Registered artifact matches: {len(registry_matches)}")
    account_matches = payload.get("account_registry_matches")
    if isinstance(account_matches, list):
        accounts = sorted(
            {
                account
                for item in account_matches
                if isinstance(item, dict) and isinstance((account := item.get("account")), str)
            }
        )
        if accounts:
            lines.append(f"Known account aliases: {', '.join(accounts)}")
    link = payload.get("link")
    if isinstance(link, dict):
        account = link.get("account")
        kind = link.get("kind")
        if isinstance(account, str) and isinstance(kind, str):
            lines.append(f"Linked account: {account} ({kind})")
    return "\n".join(lines)


def _format_agent_accounts_registry_overview(payload: dict[str, object]) -> str:
    lines = [
        "Agent accounts",
        f"Root: {payload.get('root', '<unknown>')}",
        f"Providers: {payload.get('provider_count', 0)}",
        f"Accounts: {payload.get('account_count', 0)}",
    ]
    accounts = payload.get("accounts")
    if isinstance(accounts, list) and accounts:
        lines.append("Registered accounts:")
        for item in accounts:
            if not isinstance(item, dict):
                continue
            lines.append(_format_agent_account_line(item))
    links = payload.get("link_count")
    artifacts = payload.get("artifact_count")
    if isinstance(artifacts, int):
        lines.insert(4, f"Artifacts: {artifacts}")
    if isinstance(links, int):
        lines.insert(5, f"Links: {links}")
    return "\n".join(lines)


def _format_agent_account_line(item: dict[str, object]) -> str:
    provider = item.get("provider", "<unknown>")
    account = item.get("account", "<unknown>")
    label = f"  - {provider}/{account}"
    email = item.get("email")
    if isinstance(email, str):
        label += f" <{email}>"
    display_label = item.get("label")
    if isinstance(display_label, str):
        label += f" {display_label}"
    auth_kinds = item.get("auth_kinds")
    if isinstance(auth_kinds, list) and auth_kinds:
        label += f" auth={','.join(str(kind) for kind in auth_kinds)}"
    active_sha = item.get("active_artifact_id")
    if isinstance(active_sha, str):
        label += f" active={active_sha[:12]}"
    elif active_sha is None:
        label += " active=<none>"
    return label


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

    accounts_register_parser = accounts_subparsers.add_parser(
        "register",
        help="Register a provider account in managed account storage.",
    )
    accounts_register_parser.add_argument(
        "--provider",
        required=True,
        choices=_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES,
        help="Provider family to register.",
    )
    accounts_register_parser.add_argument(
        "--auth-file",
        default=None,
        help="Provider auth file to register. Required for codex.",
    )
    accounts_register_parser.add_argument(
        "--account",
        required=True,
        help="Local AgentOS account alias to register.",
    )
    accounts_register_parser.add_argument(
        "--home",
        default=None,
        help="Deprecated for account registration; use accounts link to associate a home.",
    )
    accounts_register_parser.add_argument(
        "--email",
        default=None,
        help="Account email metadata. Required for claude-code; optional fallback for codex.",
    )
    accounts_register_parser.add_argument(
        "--label",
        default=None,
        help="Human label for the account.",
    )
    accounts_register_parser.add_argument(
        "--register-only",
        action="store_true",
        help="Register the auth artifact without making it the account's active artifact. Codex only.",
    )
    accounts_register_parser.set_defaults(handler=_cmd_agent_accounts_register)

    accounts_link_parser = accounts_subparsers.add_parser(
        "link",
        help="Copy a managed provider account auth file to a provider home.",
    )
    accounts_link_parser.add_argument(
        "--provider",
        required=True,
        choices=_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES,
        help="Provider family to link.",
    )
    accounts_link_parser.add_argument(
        "--home",
        required=True,
        help="Provider home to receive auth.json.",
    )
    accounts_link_parser.add_argument(
        "--account",
        required=True,
        help="Local AgentOS account alias to link.",
    )
    accounts_link_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite unknown or broken target-home auth state.",
    )
    accounts_link_parser.set_defaults(handler=_cmd_agent_accounts_link)

    accounts_status_parser = accounts_subparsers.add_parser(
        "status",
        help="Inspect provider home auth state against managed account storage.",
    )
    accounts_status_parser.add_argument(
        "--provider",
        default=None,
        choices=_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES,
        help="Provider family to inspect. Omit with no --home to show all account registry status.",
    )
    accounts_status_parser.add_argument(
        "--home",
        default=None,
        help="Provider home to inspect. Requires --provider.",
    )
    accounts_status_parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw status payload as JSON.",
    )
    accounts_status_parser.set_defaults(handler=_cmd_agent_accounts_status)

    accounts_monitor_parser = accounts_subparsers.add_parser(
        "monitor",
        help="Run configured account monitor workflows.",
    )
    accounts_monitor_parser.add_argument(
        "--project",
        nargs="?",
        type=Path,
        const=Path("."),
        default=None,
        help="Config start path for project-local config discovery. Bare --project uses current pwd. Agent commands do not require an existing project.",
    )
    accounts_monitor_parser.add_argument(
        "--once",
        action="store_true",
        help="Run exactly one monitor tick.",
    )
    accounts_monitor_parser.add_argument(
        "--max-ticks",
        type=int,
        default=None,
        help="Maximum monitor ticks to run. Omit for a continuous monitor loop.",
    )
    accounts_monitor_parser.add_argument(
        "--interval-sec",
        type=float,
        default=1.0,
        help="Target seconds between monitor ticks.",
    )
    accounts_monitor_parser.add_argument(
        "--json",
        action="store_true",
        help="Print monitor state and frame as JSON.",
    )
    accounts_monitor_parser.set_defaults(handler=_cmd_agent_accounts_monitor)

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
