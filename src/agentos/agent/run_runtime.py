from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from agentos._core.errors import CliError
from agentos._core.process import ProcessError, ProcessMode, run_process


@dataclass(frozen=True)
class AgentCommandConfig:
    prompt: str | None = None
    argv: tuple[str, ...] = ()
    model: str | None = None
    account: str | None = None
    interaction_mode: Literal["interactive", "non_interactive"] = "interactive"


@dataclass(frozen=True)
class AgentRunConfig:
    cwd: Path
    process_mode: ProcessMode = "terminal"
    timeout_sec: int | None = None


@dataclass(frozen=True)
class AgentCommand:
    argv: tuple[str, ...]
    env_overrides: dict[str, str]
    env_display_overrides: dict[str, str] = field(default_factory=dict)
    setup_lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentRunResult:
    exit_code: int
    stdout: str | None = None
    stderr: str | None = None
    preamble_lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentRunDryResult:
    lines: tuple[str, ...]


def build_agent_command_argv(
    command_config: AgentCommandConfig,
    *,
    instance_id: str | None,
    provider: str,
    cli_command: tuple[str, ...],
    run_args: tuple[str, ...],
    default_model: str | None,
    model_flag: str | None,
    prompt_flag: str | None,
) -> tuple[str, ...]:
    if not cli_command:
        raise CliError(_missing_provider_cli_command_message(provider))

    command = [*cli_command, *run_args]
    effective_model = command_config.model or default_model
    if effective_model is not None:
        if model_flag is None:
            raise CliError(
                f"agent {instance_id or '<default>'} for provider {provider} does not define model_flag"
            )
        command.extend([model_flag, effective_model])
    command.extend(command_config.argv)
    if command_config.prompt is not None:
        if prompt_flag is None:
            command.append(command_config.prompt)
        else:
            command.extend([prompt_flag, command_config.prompt])
    return tuple(command)


def _missing_provider_cli_command_message(provider: str) -> str:
    return "\n".join(
        (
            f"agent provider {provider} requires agent.providers.{provider}.cli_command",
            "example:",
            "{",
            '  "agent": {',
            '    "providers": {',
            f'      "{provider}": {{',
            f'        "cli_command": ["{_provider_cli_command_example(provider)}"]',
            "      }",
            "    }",
            "  }",
            "}",
        )
    )


def _provider_cli_command_example(provider: str) -> str:
    if provider == "claude-code":
        return "/opt/homebrew/bin/claude"
    if provider == "codex":
        return "/opt/homebrew/bin/codex"
    return "/path/to/provider-cli"


def format_agent_command(command: AgentCommand) -> str:
    if not command.env_overrides:
        return shlex.join(command.argv)

    env_prefix = " ".join(
        _format_env_assignment(command, key, value)
        for key, value in sorted(command.env_overrides.items())
    )
    return f"{env_prefix} {shlex.join(command.argv)}"


def _format_env_assignment(command: AgentCommand, key: str, value: str) -> str:
    if key in command.env_display_overrides:
        return f"{key}={command.env_display_overrides[key]}"
    return f"{key}={shlex.quote(value)}"


def agent_command_with_env_overrides(
    command: AgentCommand,
    *,
    env_overrides: dict[str, str],
    env_display_overrides: dict[str, str],
) -> AgentCommand:
    if not env_overrides and not env_display_overrides:
        return command
    return AgentCommand(
        argv=command.argv,
        env_overrides={**command.env_overrides, **env_overrides},
        env_display_overrides={
            **command.env_display_overrides,
            **env_display_overrides,
        },
        setup_lines=command.setup_lines,
    )


def execute_agent_command(
    command: AgentCommand,
    *,
    run_config: AgentRunConfig,
) -> AgentRunResult:
    try:
        result = run_process(
            command.argv,
            cwd=run_config.cwd,
            env_overrides=command.env_overrides,
            mode=run_config.process_mode,
            timeout_sec=run_config.timeout_sec,
        )
    except ProcessError as exc:
        if exc.error_type == "command_not_found":
            executable = command.argv[0] if command.argv else "<empty>"
            raise CliError(f"agent executable not found: {executable}") from exc
        raise
    return AgentRunResult(
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
    )


__all__ = [
    "AgentCommand",
    "AgentCommandConfig",
    "AgentRunConfig",
    "AgentRunDryResult",
    "AgentRunResult",
    "agent_command_with_env_overrides",
    "build_agent_command_argv",
    "execute_agent_command",
    "format_agent_command",
]
