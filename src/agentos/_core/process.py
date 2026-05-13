from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Callable, Literal, Mapping, Sequence

from agentos._core.errors import CliError

ProcessMode = Literal["terminal", "capture", "stream"]
ProcessStream = Literal["stdout", "stderr"]


@dataclass(frozen=True)
class ProcessOutputEvent:
    stream: ProcessStream
    text: str


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    stdout: str | None = None
    stderr: str | None = None


class ProcessError(CliError):
    def __init__(self, *, error_type: str, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message


def run_process(
    argv: Sequence[str],
    *,
    cwd: Path | str | None = None,
    env_overrides: Mapping[str, str] | None = None,
    mode: ProcessMode = "terminal",
    timeout_sec: int | None = None,
    on_output: Callable[[ProcessOutputEvent], None] | None = None,
) -> ProcessResult:
    if not argv:
        raise ProcessError(error_type="invalid_command", message="process argv must not be empty")
    if mode != "stream" and on_output is not None:
        raise ProcessError(
            error_type="invalid_mode",
            message="on_output is only valid for stream mode",
        )

    env = _process_environment(env_overrides)
    cwd_value = None if cwd is None else str(cwd)

    if mode == "terminal":
        return _run_terminal(argv, cwd=cwd_value, env=env, timeout_sec=timeout_sec)
    if mode == "capture":
        return _run_capture(argv, cwd=cwd_value, env=env, timeout_sec=timeout_sec)
    if mode == "stream":
        return _run_stream(argv, cwd=cwd_value, env=env, timeout_sec=timeout_sec, on_output=on_output)
    raise ProcessError(error_type="invalid_mode", message=f"unknown process mode: {mode}")


def _process_environment(env_overrides: Mapping[str, str] | None) -> dict[str, str]:
    env = os.environ.copy()
    if env_overrides is not None:
        env.update(env_overrides)
    return env


def _run_terminal(
    argv: Sequence[str],
    *,
    cwd: str | None,
    env: dict[str, str],
    timeout_sec: int | None,
) -> ProcessResult:
    try:
        run_kwargs: dict[str, object] = {
            "env": env,
            "check": False,
        }
        if timeout_sec is not None:
            run_kwargs["timeout"] = timeout_sec
        if cwd is not None:
            run_kwargs["cwd"] = cwd
        result = subprocess.run(list(argv), **run_kwargs)
    except FileNotFoundError as exc:
        raise ProcessError(
            error_type="command_not_found",
            message=f"process executable not found: {exc.filename}",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ProcessError(
            error_type="timeout",
            message=f"process timed out after {timeout_sec} seconds",
        ) from exc
    except OSError as exc:
        raise ProcessError(error_type="command_failed", message=str(exc)) from exc
    return ProcessResult(exit_code=int(result.returncode))


def _run_capture(
    argv: Sequence[str],
    *,
    cwd: str | None,
    env: dict[str, str],
    timeout_sec: int | None,
) -> ProcessResult:
    try:
        run_kwargs: dict[str, object] = {
            "env": env,
            "text": True,
            "capture_output": True,
            "timeout": timeout_sec,
            "check": False,
        }
        if cwd is not None:
            run_kwargs["cwd"] = cwd
        result = subprocess.run(list(argv), **run_kwargs)
    except FileNotFoundError as exc:
        raise ProcessError(
            error_type="command_not_found",
            message=f"process executable not found: {exc.filename}",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ProcessError(
            error_type="timeout",
            message=f"process timed out after {timeout_sec} seconds",
        ) from exc
    except OSError as exc:
        raise ProcessError(error_type="command_failed", message=str(exc)) from exc
    return ProcessResult(
        exit_code=int(result.returncode),
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _run_stream(
    argv: Sequence[str],
    *,
    cwd: str | None,
    env: dict[str, str],
    timeout_sec: int | None,
    on_output: Callable[[ProcessOutputEvent], None] | None,
) -> ProcessResult:
    try:
        process = subprocess.Popen(
            list(argv),
            cwd=cwd,
            env=env,
            stdin=None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ProcessError(
            error_type="command_not_found",
            message=f"process executable not found: {exc.filename}",
        ) from exc
    except OSError as exc:
        raise ProcessError(error_type="command_failed", message=str(exc)) from exc

    output_queue: Queue[ProcessOutputEvent] = Queue()
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    readers = (
        threading.Thread(
            target=_read_process_stream,
            args=(process.stdout, "stdout", output_queue),
            daemon=True,
        ),
        threading.Thread(
            target=_read_process_stream,
            args=(process.stderr, "stderr", output_queue),
            daemon=True,
        ),
    )
    for reader in readers:
        reader.start()

    deadline = None if timeout_sec is None else time.monotonic() + timeout_sec
    try:
        while process.poll() is None or any(reader.is_alive() for reader in readers):
            if deadline is not None and time.monotonic() > deadline:
                process.kill()
                process.wait()
                _join_readers(readers)
                _drain_output_events(output_queue, stdout_parts, stderr_parts, on_output)
                raise ProcessError(
                    error_type="timeout",
                    message=f"process timed out after {timeout_sec} seconds",
                )
            _drain_output_events(output_queue, stdout_parts, stderr_parts, on_output, wait_sec=0.05)
    finally:
        _join_readers(readers)

    _drain_output_events(output_queue, stdout_parts, stderr_parts, on_output)
    return ProcessResult(
        exit_code=int(process.returncode or 0),
        stdout="".join(stdout_parts),
        stderr="".join(stderr_parts),
    )


def _read_process_stream(
    stream: object,
    stream_name: ProcessStream,
    output_queue: Queue[ProcessOutputEvent],
) -> None:
    if stream is None:
        return
    for line in stream:
        output_queue.put(ProcessOutputEvent(stream=stream_name, text=line))


def _drain_output_events(
    output_queue: Queue[ProcessOutputEvent],
    stdout_parts: list[str],
    stderr_parts: list[str],
    on_output: Callable[[ProcessOutputEvent], None] | None,
    *,
    wait_sec: float | None = None,
) -> None:
    try:
        event = output_queue.get(timeout=wait_sec) if wait_sec is not None else output_queue.get_nowait()
    except Empty:
        return

    while True:
        if event.stream == "stdout":
            stdout_parts.append(event.text)
        else:
            stderr_parts.append(event.text)
        if on_output is not None:
            on_output(event)

        try:
            event = output_queue.get_nowait()
        except Empty:
            return


def _join_readers(readers: tuple[threading.Thread, threading.Thread]) -> None:
    for reader in readers:
        reader.join(timeout=0.2)


__all__ = [
    "ProcessError",
    "ProcessMode",
    "ProcessOutputEvent",
    "ProcessResult",
    "run_process",
]
