"""`agent run`, `agent ping`, and `agent profile-check` commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l1.agent.commands._shared import (
    _add_agent_run_target_args,
    _config_start_path,
)
from tarav.l1.agent.ping import AgentPingError
from tarav.l1.agent.primitives import AgentConfig, RunCapable
from tarav.l1.agent.providers.registry import resolve_agent
from tarav.l1.agent.run_runtime import AgentCommandConfig, AgentRunConfig


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

    if not args.force:
        check = agent.profile_check()
        if not check.ok:
            _render_profile_checkpoints([c for c in check.checkpoints if not c.passed])
            raise CliError(
                "agent run blocked by pre-flight profile-check; "
                "fix the failing checkpoints or pass --force to run anyway"
            )

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
    try:
        result = agent.ping(cwd=cwd, model=args.model, account=args.account)
    except AgentPingError as exc:
        raise CliError(str(exc)) from exc
    if result.failure is not None:
        raise CliError(f"agent ping failed: {result.failure}")
    print(f"pong model={result.model} elapsed_ms={result.elapsed_ms}")
    return 0


def _render_profile_checkpoints(checkpoints) -> None:
    for checkpoint in checkpoints:
        mark = "ok" if checkpoint.passed else "FAIL"
        line = f"  [{mark}] {checkpoint.id}"
        if checkpoint.reason:
            line += f" — {checkpoint.reason}"
        print(line)


def _cmd_agent_profile_check(args: argparse.Namespace) -> int:
    agent, _cwd = _resolve_agent_run_target(args)
    result = agent.profile_check()
    _render_profile_checkpoints(result.checkpoints)
    print(f"profile-check: {'ok' if result.ok else 'FAILED'}")
    return 0 if result.ok else 1


def _register_run_commands(agent_subparsers) -> None:
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
        "--force",
        action="store_true",
        help="Skip the pre-flight profile-check and run anyway.",
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

    profile_check_parser = agent_subparsers.add_parser(
        "profile-check",
        help="Check whether a resolved agent is fit to run (read-only, no spawn).",
    )
    _add_agent_run_target_args(
        profile_check_parser, provider_help="Provider family to check."
    )
    profile_check_parser.set_defaults(handler=_cmd_agent_profile_check)
