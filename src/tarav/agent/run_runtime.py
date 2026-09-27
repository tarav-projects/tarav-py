# $kw: --from Agentos.Agent.Adapter
from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from tarav.l0._core.errors import CliError
from tarav.l0._core.process import ProcessError, ProcessMode, run_process
from tarav.agent.providers import canonical_provider_family_for_name





_PROVIDER_MODEL_FLAG: dict[str, str] = {
    "claude-code": "--model",
    "codex": "--model",
    "copilot-cli": "--model",
    "opencode": "--model",
    "pi": "--model",
}
_PROVIDER_PROMPT_FLAG: dict[str, str] = {
    "claude-code": "-p",
    "copilot-cli": "-p",
    "pi": "-p",
}


def provider_model_flag(provider: str) -> str | None:
    return _PROVIDER_MODEL_FLAG.get(_provider_family(provider))


def provider_prompt_flag(provider: str) -> str | None:
    return _PROVIDER_PROMPT_FLAG.get(_provider_family(provider))


def _provider_family(provider: str) -> str:
    family = canonical_provider_family_for_name(provider)
    return family.family if family is not None else provider


CODEX_HOME_ENV_VAR = "CODEX_HOME"
CLAUDE_CONFIG_DIR_ENV_VAR = "CLAUDE_CONFIG_DIR"
CLAUDE_CODE_OAUTH_TOKEN_ENV_VAR = "CLAUDE_CODE_OAUTH_TOKEN"
COPILOT_HOME_ENV_VAR = "COPILOT_HOME"
HARNESS_INJECTED_ENV_ALLOWLIST = {
    "codex": frozenset({CODEX_HOME_ENV_VAR}),
    "claude-code": frozenset(
        {CLAUDE_CONFIG_DIR_ENV_VAR, CLAUDE_CODE_OAUTH_TOKEN_ENV_VAR}
    ),
    "copilot-cli": frozenset({COPILOT_HOME_ENV_VAR}),
    "pi": frozenset(),
    "gemini-cli": frozenset(),
    "opencode": frozenset(),
    "openclaw": frozenset(),
}


@dataclass(frozen=True)
class AgentCommandConfig:
    prompt: str | None = None
    argv: tuple[str, ...] = ()
    model: str | None = None
    account: str | None = None
    interaction_mode: Literal["interactive", "non_interactive"] = "interactive"
    credential_success_source: str | None = "agent.run"


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
    provider: str,
    cli_command: tuple[str, ...],
    run_args: tuple[str, ...],
    default_model: str | None,
) -> tuple[str, ...]:
    if not cli_command:
        raise CliError(_missing_provider_cli_command_message(provider))

    command = [*cli_command, *run_args]
    effective_model = command_config.model or default_model
    if effective_model is not None:
        model_flag = provider_model_flag(provider)
        if model_flag is None:
            raise CliError(
                f"provider {provider} does not support a model flag"
            )
        command.extend([model_flag, effective_model])
    command.extend(command_config.argv)
    if command_config.prompt is not None:
        prompt_flag = provider_prompt_flag(provider)
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
    "CLAUDE_CODE_OAUTH_TOKEN_ENV_VAR",
    "CLAUDE_CONFIG_DIR_ENV_VAR",
    "CODEX_HOME_ENV_VAR",
    "COPILOT_HOME_ENV_VAR",
    "HARNESS_INJECTED_ENV_ALLOWLIST",
    "agent_command_with_env_overrides",
    "build_agent_command_argv",
    "execute_agent_command",
    "format_agent_command",
]
