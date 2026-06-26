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
    if agent.account_policy != "profile-default":
        suffix_parts.append(f"account_policy={agent.account_policy}")
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
    if agent.profile_id is None:
        raise CliError(
            "provider command runtime requires --profile; "
            "--provider/--home default runtime is disabled"
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
    print(
        f"pong model={_agent_ping_model(agent, command_config)} elapsed_ms={elapsed_ms}"
    )
    return 0


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


def _cmd_agent_accounts_materialize(args: argparse.Namespace) -> int:
    if args.provider in ("claude-code", "codex"):
        return _materialize_account(args, args.provider)
    raise CliError(
        f"agent accounts materialize is not supported for provider {args.provider}"
    )


def _cmd_agent_accounts_capture(args: argparse.Namespace) -> int:
    from agentos.agent import auth_registry as R
    from agentos.agent.auth_method_registry import auth_methods_for_provider

    provider = args.provider
    home = Path(args.home)
    for auth_method in auth_methods_for_provider(provider):
        auth = auth_method.read_auth_data(home)
        if auth is None:
            continue
        identity = auth_method.extract_identity(auth)
        # Capture never rejects: a known identity files under its account/method,
        # an identifiable orphan files under the Unknown.Account bucket.
        account, method = R.capture_target(provider, identity, auth_method.name)
        artifact_id = R.store_artifact(provider, auth)
        if not R.is_captured(provider, account, method, artifact_id):
            R.append_capture(
                provider, account=account, method=method,
                auth_class=auth_method.name, auth_ref=identity, artifact_id=artifact_id,
            )
        payload = {"command": "agent accounts capture", "provider": provider,
                   "home": str(home), "account": account, "method": method,
                   "artifact_id": artifact_id}
        if args.json:
            print(format_json_output(payload))
        else:
            print(f"Captured {provider} {account}/{method} <- {home} (artifact {artifact_id[:12]})")
        return 0
    raise CliError(f"no Auth.Data could be read from home: {home}")


def _cmd_agent_accounts_activate(args: argparse.Namespace) -> int:
    from agentos.agent import auth_registry as R

    provider = args.provider
    account_id, sep, method = args.account.partition("/")
    if not sep or not account_id or not method:
        raise CliError(f"{provider} activate requires --account <account-id>/<method>")
    if R.read_artifact(provider, args.artifact) is None:
        raise CliError(f"artifact not found in registry: {args.artifact}")
    R.set_active(provider, account_id, method, args.artifact)
    payload = {"command": "agent accounts activate", "provider": provider,
               "account": args.account, "artifact_id": args.artifact}
    if args.json:
        print(format_json_output(payload))
    else:
        print(f"Activated {provider} {args.account} -> {args.artifact[:12]}")
    return 0


def _materialize_account(args: argparse.Namespace, provider: str) -> int:
    from agentos.agent import auth_registry as R
    from agentos.agent.auth_method_registry import auth_method_for_class

    account_id, sep, method = args.account.partition("/")
    if not sep or not account_id or not method:
        raise CliError(f"{provider} materialize requires --account <account-id>/<method>")

    auth_class = R.method_class(provider, account_id, method)
    auth_method = auth_method_for_class(provider, auth_class) if auth_class else None
    if auth_method is None:
        raise CliError(f"unknown auth method for {provider} {args.account}")

    active_id = R.active_artifact_id(provider, account_id, method)
    if active_id is None:
        raise CliError(f"no active artifact for {provider} {args.account}")
    artifact = R.read_artifact(provider, active_id)
    if artifact is None:
        raise CliError(f"active artifact payload not found: {active_id}")

    home = Path(args.home)

    # Capture.Over.Materialization: archive whatever is live in the home first.
    captured_id = None
    live = auth_method.read_auth_data(home)
    if live is not None:
        captured_id = R.store_artifact(provider, live)
        identity = auth_method.extract_identity(live)
        if identity is not None and not R.is_captured(provider, account_id, method, captured_id):
            R.append_capture(
                provider, account=account_id, method=method,
                auth_class=auth_method.name, auth_ref=identity, artifact_id=captured_id,
            )

    if not args.check:
        auth_method.materialize(artifact, home)

    payload = {
        "command": "agent accounts materialize",
        "provider": provider,
        "account": args.account,
        "home": str(home),
        "active_artifact_id": active_id,
        "captured_artifact_id": captured_id,
        "status": "check" if args.check else "materialized",
    }
    if args.json:
        print(format_json_output(payload))
    else:
        verb = "Would materialize" if args.check else "Materialized"
        line = f"{verb} {provider} {args.account} -> {home} (artifact {active_id[:12]})"
        if captured_id is not None:
            line += f"; captured-first {captured_id[:12]}"
        print(line)
    return 0


def _cmd_agent_accounts_status(args: argparse.Namespace) -> int:
    from agentos.agent.account_status_report import (
        build_status_report,
        format_status_report,
    )

    providers = (
        (args.provider,) if args.provider is not None else _AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES
    )
    home_filter = (
        str(Path(args.home).expanduser().resolve()) if args.home is not None else None
    )

    reports = []
    for provider in providers:
        payload = build_status_report(provider)
        if home_filter is not None:
            homes = [h for h in payload["homes"] if h.get("home") == home_filter]
            payload = {**payload, "homes": homes}
        reports.append(payload)

    if args.json:
        print(format_json_output(reports[0] if args.provider is not None else {"reports": reports}))
    else:
        print("\n".join(format_status_report(p) for p in reports))
    return 0


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
        help="Configured agent profile id.",
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

    accounts_capture_parser = accounts_subparsers.add_parser(
        "capture",
        help="Capture (archive) the Auth.Data present in a provider home. Read-only on the home.",
    )
    accounts_capture_parser.add_argument(
        "--provider", required=True, choices=_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES,
        help="Provider family.",
    )
    accounts_capture_parser.add_argument("--home", required=True, help="Provider home to capture from.")
    accounts_capture_parser.add_argument("--json", action="store_true", help="Output as JSON.")
    accounts_capture_parser.set_defaults(handler=_cmd_agent_accounts_capture)

    accounts_activate_parser = accounts_subparsers.add_parser(
        "activate",
        help="Set a captured artifact as the active Auth.Data for an account/method.",
    )
    accounts_activate_parser.add_argument(
        "--provider", required=True, choices=_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES,
        help="Provider family.",
    )
    accounts_activate_parser.add_argument(
        "--account", required=True, help="Target account as <account-id>/<method>.",
    )
    accounts_activate_parser.add_argument("--artifact", required=True, help="Artifact id to activate.")
    accounts_activate_parser.add_argument("--json", action="store_true", help="Output as JSON.")
    accounts_activate_parser.set_defaults(handler=_cmd_agent_accounts_activate)

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
