from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from agentos._core.errors import CliError
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
    env = account_provider_environment(agent)
    if extra_env is not None:
        env.update(extra_env)

    return run_captured_command(
        command,
        env=env,
        timeout_sec=account_timeout_sec(agent),
        cwd=cwd,
    )


def run_captured_command(
    command: list[str],
    *,
    env: dict[str, str],
    timeout_sec: int,
    cwd: str | None = None,
) -> subprocess.CompletedProcess[str]:
    run_kwargs: dict[str, Any] = {
        "env": env,
        "text": True,
        "capture_output": True,
        "timeout": timeout_sec,
        "check": False,
    }
    if cwd is not None:
        run_kwargs["cwd"] = cwd

    try:
        return subprocess.run(command, **run_kwargs)
    except FileNotFoundError as exc:
        raise AccountCommandError(
            error_type="command_not_found",
            message=str(exc),
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AccountCommandError(
            error_type="timeout",
            message=f"provider command timed out after {timeout_sec} seconds",
        ) from exc
    except OSError as exc:
        raise AccountCommandError(
            error_type="command_failed",
            message=str(exc),
        ) from exc


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
