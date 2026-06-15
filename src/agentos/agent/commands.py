from __future__ import annotations

import argparse
import json
import re
import sys
import termios
import time
import tty
from dataclasses import replace
from pathlib import Path
from threading import Thread

from agentos._core.project import normalize_project_target
from agentos._core.errors import CliError
from agentos.agent.primitives import AgentConfig, RunCapable
from agentos.agent.config import (
    profile_path,
    profiles_root,
)
from agentos._core.path_validation import validate_string_for_path
from agentos.agent._cli_common import format_json_output
from agentos.agent.providers import load_configured_agents, resolve_agent
from agentos.agent.run_runtime import AgentCommandConfig, AgentRunConfig
from agentos.providers import canonical_provider_families

_AGENT_PROVIDER_CHOICES = tuple(
    provider.family for provider in canonical_provider_families()
)
_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES = ("codex", "claude-code", "copilot-cli")
_PING_NUMBER_PATTERN = re.compile(r"(?<![\d.])-?\d+(?![\d.])")


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
            "homes": [],
            "cli_command": [],
            "default_model": "",
            "model_flag": "",
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
    interaction_mode = "non_interactive" if args.non_interactive else "interactive"
    agent, command_config, run_config = _resolve_agent_run(
        args,
        prompt=prompt,
        argv=argv,
        interaction_mode=interaction_mode,
    )
    if args.dry_run:
        dry_result = agent.run_dry(command_config)
        for line in dry_result.lines:
            print(line)
        return 0

    result = agent.run(command_config, run_config)
    return result.exit_code


def _resolve_agent_run_target(args: argparse.Namespace) -> tuple[AgentConfig, Path]:
    config_start_path = _config_start_path(args)
    cwd = Path(args.cwd).expanduser().resolve() if args.cwd else Path.cwd().resolve()
    agent = resolve_agent(
        provider=args.provider,
        profile=args.profile,
        start_path=config_start_path,
        home=args.home,
    )
    if not isinstance(agent, RunCapable):
        raise CliError(f"provider {agent.provider} does not support run")
    return agent, cwd


def _resolve_agent_run(
    args: argparse.Namespace,
    *,
    prompt: str | None,
    argv: tuple[str, ...],
    interaction_mode: str = "interactive",
) -> tuple[AgentConfig, AgentCommandConfig, AgentRunConfig]:
    agent, cwd = _resolve_agent_run_target(args)
    return (
        agent,
        _agent_command_config(
            args,
            prompt=prompt,
            argv=argv,
            interaction_mode=interaction_mode,
        ),
        _agent_run_config(cwd=cwd),
    )


def _agent_command_config(
    args: argparse.Namespace,
    *,
    prompt: str | None,
    argv: tuple[str, ...],
    interaction_mode: str = "interactive",
) -> AgentCommandConfig:
    return AgentCommandConfig(
        prompt=prompt,
        argv=argv,
        model=args.model,
        account=args.account,
        interaction_mode=interaction_mode,
    )


def _agent_run_config(*, cwd: Path) -> AgentRunConfig:
    return AgentRunConfig(
        cwd=cwd,
        process_mode="terminal",
    )


def _cmd_agent_ping(args: argparse.Namespace) -> int:
    agent, cwd = _resolve_agent_run_target(args)
    if not agent.ping.enabled:
        raise CliError(
            f"agent {agent.profile_id or '<default>'} for provider {agent.provider} has ping disabled"
        )
    command_config = _agent_command_config(
        args,
        prompt=agent.ping.prompt,
        argv=agent.ping.argv,
        interaction_mode="non_interactive",
    )
    command_config = replace(command_config, credential_success_source=None)
    if command_config.model is None and agent.ping.model is not None:
        command_config = replace(command_config, model=agent.ping.model)
    started_at = time.perf_counter()
    result = agent.run(command_config, AgentRunConfig(cwd=cwd, process_mode="capture"))
    elapsed_ms = round((time.perf_counter() - started_at) * 1000)
    _validate_agent_ping_result(
        result,
        expected_number=agent.ping.expected_number,
    )
    _record_agent_credential_success(
        agent,
        command_config=command_config,
        source="agent.ping",
    )
    print(
        f"pong model={_agent_ping_model(agent, command_config)} elapsed_ms={elapsed_ms}"
    )
    return 0


def _record_agent_credential_success(
    agent: AgentConfig,
    *,
    command_config: AgentCommandConfig,
    source: str,
) -> None:
    if agent.home is None:
        return
    account = command_config.account
    if account is None and agent.account is not None and agent.account.provider == agent.provider:
        account = agent.account.account
    if account is None:
        return
    try:
        if agent.provider == "claude-code":
            from agentos.claude.account_registry import (
                has_claude_oauth_token_kind,
                promote_verified_claude_ambient_auth_from_home,
            )

            if has_claude_oauth_token_kind(account):
                return
            promote_verified_claude_ambient_auth_from_home(
                home=agent.home,
                account=account,
                source=source,
            )
        elif agent.provider == "codex":
            from agentos.codex.account_registry import promote_verified_codex_auth_from_home

            promote_verified_codex_auth_from_home(
                home=agent.home,
                account=account,
                source=source,
            )
    except CliError:
        return



def _validate_agent_ping_result(
    result,
    *,
    expected_number: int | None,
) -> None:
    output = _agent_ping_output(result.stdout, result.stderr)
    if result.exit_code != 0:
        detail = output.strip()
        suffix = f": {detail}" if detail else ""
        raise CliError(
            f"agent ping failed: provider command exited with {result.exit_code}{suffix}"
        )

    if expected_number is None:
        return

    numbers = [int(match.group(0)) for match in _PING_NUMBER_PATTERN.finditer(output)]
    if expected_number not in numbers:
        raise CliError(
            f"agent ping failed: expected numeric answer {expected_number} "
            "was not present in provider output"
        )


def _agent_ping_output(stdout: str | None, stderr: str | None) -> str:
    return "\n".join(part for part in (stdout, stderr) if part)


def _agent_ping_model(agent: AgentConfig, command_config: AgentCommandConfig) -> str:
    return command_config.model or agent.default_model or "<provider-default>"


def _cmd_agent_accounts_register(args: argparse.Namespace) -> int:
    if args.oauth_token_file is not None and args.provider != "claude-code":
        raise CliError("--oauth-token-file is only supported for provider claude-code")
    if args.provider == "codex":
        if args.auth_file is None:
            raise CliError(
                "agent accounts register --provider codex requires --auth-file"
            )
        from agentos.codex.account_registry import register_codex_account_from_auth_file

        print(
            format_json_output(
                register_codex_account_from_auth_file(
                    auth_file=Path(args.auth_file),
                    account=args.account,
                    email=args.email,
                    register_only=args.register_only,
                    argv=getattr(args, "_agentos_argv", []),
                )
            )
        )
        return 0
    if args.provider == "claude-code":
        from agentos.claude.account_registry import register_claude_account

        print(
            format_json_output(
                register_claude_account(
                    account=args.account,
                    email=args.email,
                    label=args.label,
                    oauth_token_file=args.oauth_token_file,
                    argv=getattr(args, "_agentos_argv", []),
                )
            )
        )
        return 0
    if args.provider == "copilot-cli":
        from agentos.copilot.account_registry import register_copilot_account

        print(
            format_json_output(
                register_copilot_account(
                    account=args.account,
                    account_id=args.account_id,
                    label=args.label,
                    argv=getattr(args, "_agentos_argv", []),
                )
            )
        )
        return 0
    raise CliError(
        f"agent accounts register is not supported for provider {args.provider}"
    )


def _cmd_agent_accounts_materialize(args: argparse.Namespace) -> int:
    if args.provider == "codex":
        from agentos.codex.account_registry import materialize_codex_account_to_home

        payload = materialize_codex_account_to_home(
            home=Path(args.home),
            account=args.account,
            force=args.force,
            check=args.check,
            argv=getattr(args, "_agentos_argv", []),
        )
        if args.json:
            print(format_json_output(payload))
        else:
            print(_format_agent_accounts_materialize(payload))
        return 0
    raise CliError(
        f"agent accounts materialize is not supported for provider {args.provider}"
    )


def _cmd_agent_accounts_reconcile(args: argparse.Namespace) -> int:
    if args.ping and args.provider not in {"claude-code", "codex"}:
        raise CliError("--ping is only supported for provider claude-code or codex")
    if args.provider == "codex":
        from agentos.codex.account_reconcile import reconcile_codex_accounts

        payload = reconcile_codex_accounts(
            account=args.account,
            home=Path(args.home) if args.home is not None else None,
            start_path=_config_start_path(args),
            check=args.check,
            ping=args.ping,
            argv=getattr(args, "_agentos_argv", []),
        )
        if args.json:
            print(format_json_output(payload))
        else:
            print(_format_agent_accounts_reconcile(payload))
        return 0
    if args.provider == "claude-code":
        from agentos.claude.account_reconcile import reconcile_claude_accounts

        payload = reconcile_claude_accounts(
            account=args.account,
            home=Path(args.home) if args.home is not None else None,
            start_path=_config_start_path(args),
            check=args.check,
            ping=args.ping,
            argv=getattr(args, "_agentos_argv", []),
        )
        if args.json:
            print(format_json_output(payload))
        else:
            print(_format_agent_accounts_reconcile(payload))
        return 0
    raise CliError(f"agent accounts reconcile is not supported for provider {args.provider}")


def _format_agent_accounts_materialize(payload: dict[str, object]) -> str:
    provider = payload.get("provider")
    account = payload.get("account")
    home = payload.get("home")
    auth_path = payload.get("auth_path")
    artifact_id = payload.get("artifact_id")
    prefix = "Would materialize" if payload.get("check") else "Materialized"
    if isinstance(auth_path, str):
        return (
            f"{prefix} {provider} account {account} to {home} "
            f"(auth copied to {auth_path})."
        )
    if isinstance(artifact_id, str):
        return (
            f"{prefix} {provider} account {account} to {home} "
            f"(artifact {artifact_id[:12]})."
        )
    return f"{prefix} {provider} account {account} to {home}."


def _format_agent_accounts_reconcile(payload: dict[str, object]) -> str:
    lines = [
        f"Reconciled {payload.get('provider', '<unknown>')} accounts",
        f"Homes scanned: {payload.get('scanned_count', 0)}",
        f"Actions: {payload.get('action_count', 0)}",
        f"Warnings: {payload.get('warning_count', 0)}",
    ]
    actions = payload.get("actions")
    if isinstance(actions, list):
        for action in actions:
            if not isinstance(action, dict):
                continue
            kind = action.get("kind", "<unknown>")
            account = action.get("account", "<unknown>")
            artifact_id = action.get("artifact_id")
            suffix = f" {str(artifact_id)[:12]}" if isinstance(artifact_id, str) else ""
            lines.append(f"  - {kind}: {account}{suffix}")
    warnings = payload.get("warnings")
    if isinstance(warnings, list):
        for warning in warnings:
            if not isinstance(warning, dict):
                continue
            message = warning.get("message") or warning.get("kind") or "warning"
            home = warning.get("home")
            suffix = f" ({home})" if isinstance(home, str) else ""
            lines.append(f"  ! {message}{suffix}")
    return "\n".join(lines)


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
            print(format_json_output(payload))
        else:
            print(_format_agent_accounts_status(payload))
        return 0
    if args.home is not None:
        payload = _inspect_account_home(provider=args.provider, home=Path(args.home))
        if args.json:
            print(format_json_output(payload))
        else:
            print(_format_agent_accounts_status(payload))
        return 0
    return _cmd_agent_accounts_registry_status(args, provider=args.provider)


def _cmd_agent_accounts_monitor(args: argparse.Namespace) -> int:
    from agentos.agent.monitor import (
        RichMonitorRenderer,
        build_monitor_loop,
        dumps_monitor_json,
    )

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

            frame, state = loop.run(wait_for_first_frame=True)
            print(dumps_monitor_json(frame, state))
            return 0

        with RichMonitorRenderer() as renderer:
            if _should_listen_for_monitor_enter(args):
                _start_monitor_input_thread(loop)
            loop.run(on_tick=renderer.render, wait_for_first_frame=args.once)
        return 0
    except KeyboardInterrupt:
        return 130


def _should_listen_for_monitor_enter(args: argparse.Namespace) -> bool:
    return not args.json and not args.once and sys.stdin.isatty()


def _start_monitor_input_thread(loop) -> Thread:
    import select

    from agentos.agent.monitor import (
        MONITOR_ENTER_ALARM,
        MONITOR_USAGE_VARIANT_TOGGLE_ALARM,
    )

    def listen_for_input() -> None:
        stdin = sys.stdin
        fd = stdin.fileno()
        previous_attrs = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while not loop.stop_requested.is_set():
                readable, _, _ = select.select([stdin], [], [], 0.1)
                if not readable:
                    continue
                char = stdin.read(1)
                if char == "":
                    return
                if char in {"\n", "\r"}:
                    loop.set_alarm(MONITOR_ENTER_ALARM, remaining_ticks=0)
                elif char.lower() == "r":
                    loop.set_alarm(
                        MONITOR_USAGE_VARIANT_TOGGLE_ALARM,
                        remaining_ticks=0,
                    )
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, previous_attrs)

    thread = Thread(
        target=listen_for_input,
        name="agentos-monitor-input",
        daemon=True,
    )
    thread.start()
    return thread


def _cmd_agent_sessions_copy(args: argparse.Namespace) -> int:
    from agentos.agent.session_copy import copy_agent_session

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


def _inspect_account_home(*, provider: str, home: Path) -> dict[str, object]:
    normalized_home = str(home.expanduser().resolve())
    return {
        "status": "ok",
        "command": "agent accounts status",
        "provider": provider,
        "home": normalized_home,
        "classification": "exists" if Path(normalized_home).exists() else "missing",
    }


def _cmd_agent_accounts_registry_status(
    args: argparse.Namespace, *, provider: str | None
) -> int:
    from agentos.agent.account_registry import inspect_account_registry

    payload = inspect_account_registry(provider)
    if args.json:
        print(format_json_output(payload))
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
                if isinstance(item, dict)
                and isinstance((account := item.get("account")), str)
            }
        )
        if accounts:
            lines.append(f"Known account aliases: {', '.join(accounts)}")
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
    artifacts = payload.get("artifact_count")
    if isinstance(artifacts, int):
        lines.insert(4, f"Artifacts: {artifacts}")
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
    auth_kind = item.get("auth_kind")
    if isinstance(auth_kind, str) and auth_kind:
        label += f" auth={auth_kind}"
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
        default=None,
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
        "-a",
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
        "--oauth-token-file",
        default=None,
        help="Claude OAuth token file to register. Use '-' to read from stdin. Claude-code only.",
    )
    accounts_register_parser.add_argument(
        "--account",
        required=True,
        help="Local AgentOS account alias to register.",
    )
    accounts_register_parser.add_argument(
        "--email",
        default=None,
        help="Account email metadata. Required for claude-code; optional fallback for codex.",
    )
    accounts_register_parser.add_argument(
        "--account-id",
        default=None,
        help="Provider account id metadata. Required for copilot-cli.",
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

    accounts_materialize_parser = accounts_subparsers.add_parser(
        "materialize",
        help="Materialize a managed provider account credential into a provider runtime target.",
    )
    accounts_materialize_parser.add_argument(
        "--provider",
        required=True,
        choices=_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES,
        help="Provider family to materialize.",
    )
    accounts_materialize_parser.add_argument(
        "--home",
        required=True,
        help="Provider home to receive credential materialization.",
    )
    accounts_materialize_parser.add_argument(
        "--account",
        required=True,
        help="Local AgentOS account alias to materialize.",
    )
    accounts_materialize_parser.add_argument(
        "--check",
        action="store_true",
        help="Report intended materialization without mutating the provider home.",
    )
    accounts_materialize_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite unknown or broken target-home auth state when supported.",
    )
    accounts_materialize_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON.",
    )
    accounts_materialize_parser.set_defaults(handler=_cmd_agent_accounts_materialize)

    accounts_reconcile_parser = accounts_subparsers.add_parser(
        "reconcile",
        help="Register fresh known auth files and sync stale materialized homes.",
    )
    accounts_reconcile_parser.add_argument(
        "--provider",
        required=True,
        choices=_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES,
        help="Provider family to reconcile.",
    )
    accounts_reconcile_parser.add_argument(
        "--account",
        default=None,
        help="Local AgentOS account alias to reconcile.",
    )
    accounts_reconcile_parser.add_argument(
        "--home",
        default=None,
        help="Known provider home to reconcile.",
    )
    accounts_reconcile_parser.add_argument(
        "--project",
        nargs="?",
        type=Path,
        const=Path("."),
        default=None,
        help="Config start path for configured home discovery.",
    )
    accounts_reconcile_parser.add_argument(
        "--check",
        action="store_true",
        help="Report intended actions without mutating account storage or homes.",
    )
    accounts_reconcile_parser.add_argument(
        "--ping",
        action="store_true",
        help="For claude-code, run live ping verification before activating credentials.",
    )
    accounts_reconcile_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON.",
    )
    accounts_reconcile_parser.set_defaults(handler=_cmd_agent_accounts_reconcile)

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

    run_parser = agent_subparsers.add_parser(
        "run",
        help="Run one configured agent with a prompt or raw provider arguments.",
    )
    _add_agent_run_target_args(run_parser, provider_help="Provider family to run.")
    run_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run in non-interactive mode. Providers that support it will use their non-interactive execution path (e.g., codex exec).",
    )
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
