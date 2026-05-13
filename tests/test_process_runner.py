from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from agentos._core.process import ProcessError, ProcessOutputEvent, run_process


def test_process_runner_terminal_returns_exit_code_only() -> None:
    result = run_process(
        [sys.executable, "-c", "raise SystemExit(7)"],
        mode="terminal",
    )

    assert result.exit_code == 7
    assert result.stdout is None
    assert result.stderr is None


def test_process_runner_capture_returns_stdout_and_stderr() -> None:
    result = run_process(
        [
            sys.executable,
            "-c",
            "import sys; print('out'); print('err', file=sys.stderr)",
        ],
        mode="capture",
    )

    assert result.exit_code == 0
    assert result.stdout == "out\n"
    assert result.stderr == "err\n"


def test_process_runner_stream_emits_events_and_returns_buffers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[ProcessOutputEvent] = []

    result = run_process(
        [
            sys.executable,
            "-u",
            "-c",
            (
                "import sys, time; "
                "print('out-1'); "
                "sys.stdout.flush(); "
                "time.sleep(0.05); "
                "print('err-1', file=sys.stderr)"
            ),
        ],
        mode="stream",
        on_output=events.append,
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert result.exit_code == 0
    assert result.stdout == "out-1\n"
    assert result.stderr == "err-1\n"
    assert ("stdout", "out-1\n") in [(event.stream, event.text) for event in events]
    assert ("stderr", "err-1\n") in [(event.stream, event.text) for event in events]


def test_process_runner_returns_nonzero_without_raising() -> None:
    result = run_process(
        [sys.executable, "-c", "import sys; sys.exit(3)"],
        mode="capture",
    )

    assert result.exit_code == 3


def test_process_runner_command_not_found_is_explicit() -> None:
    with pytest.raises(ProcessError) as exc_info:
        run_process(["agentos-missing-command-for-test"], mode="capture")

    assert exc_info.value.error_type == "command_not_found"


def test_process_runner_timeout_is_explicit_and_stops_process(tmp_path: Path) -> None:
    marker_path = tmp_path / "still-running"

    with pytest.raises(ProcessError) as exc_info:
        run_process(
            [
                sys.executable,
                "-c",
                (
                    "import pathlib, sys, time; "
                    "time.sleep(2); "
                    "pathlib.Path(sys.argv[1]).write_text('alive')"
                ),
                str(marker_path),
            ],
            mode="capture",
            timeout_sec=1,
        )

    assert exc_info.value.error_type == "timeout"
    time.sleep(1.5)
    assert not marker_path.exists()


def test_process_runner_rejects_output_hook_outside_stream() -> None:
    with pytest.raises(ProcessError) as exc_info:
        run_process(
            [sys.executable, "-c", "print('out')"],
            mode="capture",
            on_output=lambda event: None,
        )

    assert exc_info.value.error_type == "invalid_mode"
