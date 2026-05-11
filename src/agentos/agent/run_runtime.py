from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agentos._core.errors import CliError


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
    env = os.environ.copy()
    env.update(env_overrides)
    try:
        result = subprocess.run(
            list(command),
            cwd=str(cwd),
            env=env,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CliError(f"agent executable not found: {exc.filename}") from exc
    return AgentRunResult(exit_code=int(result.returncode))


__all__ = [
    "AgentRunDryResult",
    "AgentRunRequest",
    "AgentRunResult",
    "execute_agent_run_command",
    "format_agent_run_command",
]
