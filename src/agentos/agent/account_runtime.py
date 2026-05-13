from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from agentos._core.errors import CliError
from agentos._core.process import ProcessError, run_process
from agentos.agent.primitives import Agent


DEFAULT_ACCOUNT_TIMEOUT_SEC = 15


@dataclass(frozen=True)
class AccountStatsRequest:
    refresh_usage: bool = False


class AccountCommandError(Exception):
    def __init__(
        self,
        *,
        error_type: str,
        message: str,
        exit_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.exit_code = exit_code


def account_instance_id(agent: Agent) -> str:
    if agent.instance_id is None:
        raise CliError("account provider instance is missing instance_id")
    return agent.instance_id


def account_timeout_sec(agent: Agent) -> int:
    return agent.timeout_sec or DEFAULT_ACCOUNT_TIMEOUT_SEC


def account_provider_environment(agent: Agent) -> dict[str, str]:
    env = os.environ.copy()
    env.update(dict(agent.env))
    return env


def collect_parsed_command_payload(
    agent: Agent,
    *,
    extra_args: tuple[str, ...],
    parser: Callable[[str], dict[str, Any]],
    cwd: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    result = run_account_command(
        agent,
        extra_args=extra_args,
        cwd=cwd,
        extra_env=extra_env,
    )

    success_output = successful_command_output(result)
    try:
        return parser(success_output)
    except (CliError, TypeError, ValueError) as exc:
        raise AccountCommandError(
            error_type="invalid_output",
            message=str(exc),
        ) from exc


def run_account_command(
    agent: Agent,
    *,
    extra_args: tuple[str, ...],
    cwd: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [*agent.cli_command, *extra_args]
    env_overrides = dict(agent.env)
    if extra_env is not None:
        env_overrides.update(extra_env)

    return run_captured_command(
        command,
        env_overrides=env_overrides,
        timeout_sec=account_timeout_sec(agent),
        cwd=cwd,
    )


def run_captured_command(
    command: list[str],
    *,
    env_overrides: dict[str, str],
    timeout_sec: int,
    cwd: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = run_process(
            command,
            cwd=cwd,
            env_overrides=env_overrides,
            mode="capture",
            timeout_sec=timeout_sec,
        )
    except ProcessError as exc:
        if exc.error_type not in {"command_not_found", "timeout"}:
            error_type = "command_failed"
        else:
            error_type = exc.error_type
        raise AccountCommandError(
            error_type=error_type,
            message=(
                f"provider command timed out after {timeout_sec} seconds"
                if exc.error_type == "timeout"
                else exc.message
            ),
        ) from exc
    return subprocess.CompletedProcess(
        command,
        result.exit_code,
        stdout=result.stdout or "",
        stderr=result.stderr or "",
    )


def successful_command_output(result: subprocess.CompletedProcess[str]) -> str:
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if result.returncode != 0:
        message = stderr or stdout or f"provider command exited with code {result.returncode}"
        raise AccountCommandError(
            error_type="command_failed",
            message=message,
            exit_code=result.returncode,
        )
    success_output = stdout or stderr
    if not success_output:
        raise AccountCommandError(
            error_type="invalid_output",
            message="provider command returned no output",
        )
    return success_output
