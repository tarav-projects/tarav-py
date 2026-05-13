from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.process import ProcessError, run_process


@dataclass(frozen=True)
class AgentRunRequest:
    prompt: str | None
    argv: tuple[str, ...]
    model: str | None
    cwd: Path
    account: str | None = None


@dataclass(frozen=True)
class AgentRunResult:
    exit_code: int


@dataclass(frozen=True)
class AgentRunDryResult:
    lines: tuple[str, ...]


def build_agent_run_command(
    request: AgentRunRequest,
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
        raise CliError(
            f"agent {instance_id or '<default>'} for provider {provider} has no cli_command"
        )

    command = [*cli_command, *run_args]
    effective_model = request.model or default_model
    if effective_model is not None:
        if model_flag is None:
            raise CliError(
                f"agent {instance_id or '<default>'} for provider {provider} does not define model_flag"
            )
        command.extend([model_flag, effective_model])
    command.extend(request.argv)
    if request.prompt is not None:
        if prompt_flag is None:
            command.append(request.prompt)
        else:
            command.extend([prompt_flag, request.prompt])
    return tuple(command)


def format_agent_run_command(
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


def execute_agent_run_command(
    command: tuple[str, ...],
    *,
    cwd: Path,
    env_overrides: dict[str, str],
) -> AgentRunResult:
    try:
        result = run_process(
            command,
            cwd=cwd,
            env_overrides=env_overrides,
            mode="terminal",
        )
    except ProcessError as exc:
        if exc.error_type == "command_not_found":
            executable = command[0] if command else "<empty>"
            raise CliError(f"agent executable not found: {executable}") from exc
        raise
    return AgentRunResult(
        exit_code=result.exit_code,
    )


__all__ = [
    "AgentRunDryResult",
    "AgentRunRequest",
    "AgentRunResult",
    "build_agent_run_command",
    "execute_agent_run_command",
    "format_agent_run_command",
]
