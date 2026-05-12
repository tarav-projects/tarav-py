from __future__ import annotations

import os
import pty
import select
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
    capture_output: bool = False


@dataclass(frozen=True)
class AgentRunResult:
    exit_code: int
    terminal_output: str | None = None


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
    capture_output: bool = False,
) -> AgentRunResult:
    env = os.environ.copy()
    env.update(env_overrides)
    if capture_output:
        return _execute_agent_run_command_with_terminal_capture(
            command,
            cwd=cwd,
            env=env,
        )

    run_kwargs: dict[str, object] = {
        "cwd": str(cwd),
        "env": env,
        "check": False,
    }
    try:
        result = subprocess.run(
            list(command),
            **run_kwargs,
        )
    except FileNotFoundError as exc:
        raise CliError(f"agent executable not found: {exc.filename}") from exc
    return AgentRunResult(
        exit_code=int(result.returncode),
    )


def _execute_agent_run_command_with_terminal_capture(
    command: tuple[str, ...],
    *,
    cwd: Path,
    env: dict[str, str],
) -> AgentRunResult:
    master_fd: int | None = None
    slave_fd: int | None = None
    try:
        master_fd, slave_fd = pty.openpty()
        process = subprocess.Popen(
            list(command),
            cwd=str(cwd),
            env=env,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            text=False,
            close_fds=True,
        )
    except FileNotFoundError as exc:
        if master_fd is not None:
            os.close(master_fd)
        raise CliError(f"agent executable not found: {exc.filename}") from exc
    except Exception:
        if master_fd is not None:
            os.close(master_fd)
        raise
    finally:
        if slave_fd is not None:
            os.close(slave_fd)

    output_chunks: list[bytes] = []
    os.set_blocking(master_fd, False)
    try:
        while process.poll() is None:
            output_chunks.extend(_read_terminal_chunks(master_fd, timeout_sec=0.1))
        output_chunks.extend(_read_terminal_chunks(master_fd, timeout_sec=0))
    finally:
        os.close(master_fd)

    return AgentRunResult(
        exit_code=int(process.returncode),
        terminal_output=b"".join(output_chunks).decode(errors="replace"),
    )


def _read_terminal_chunks(master_fd: int, *, timeout_sec: float) -> list[bytes]:
    chunks: list[bytes] = []
    while True:
        try:
            ready, _, _ = select.select([master_fd], [], [], timeout_sec)
        except OSError:
            break
        if not ready:
            break
        try:
            chunk = os.read(master_fd, 4096)
        except BlockingIOError:
            break
        except OSError:
            break
        if not chunk:
            break
        chunks.append(chunk)
        timeout_sec = 0
    return chunks


__all__ = [
    "AgentRunDryResult",
    "AgentRunRequest",
    "AgentRunResult",
    "build_agent_run_command",
    "execute_agent_run_command",
    "format_agent_run_command",
]
