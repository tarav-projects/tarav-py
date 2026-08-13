from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest

import agentos.daemon.commands as daemon_commands
from agentos._core.errors import CliError
from agentos.daemon import (
    DaemonRuntime,
    daemon_log_path,
    daemon_status,
    register_daemon_commands,
    request_daemon_stop,
    submit_hook_invocation,
)
from agentos.daemon.log import report_hook_delivery_failure
from agentos.hooks import HookInvocation, HookRegistry, register_hook_commands
from agentos.testing import AgentosTestEnvironment


def _wait_for(predicate, *, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition was not met before timeout")
        time.sleep(0.01)


def _start_runtime(
    registry: HookRegistry,
    *,
    socket_path: Path,
) -> tuple[DaemonRuntime, threading.Thread]:
    ready = threading.Event()
    runtime = DaemonRuntime(registry, socket_path=socket_path)
    thread = threading.Thread(
        target=runtime.serve_forever,
        kwargs={"ready_event": ready},
        daemon=True,
    )
    thread.start()
    assert ready.wait(timeout=2)
    return runtime, thread


def _short_socket_path() -> Path:
    return Path("/tmp") / f"agentos-test-{uuid4().hex}.sock"


def _daemon_parser(registry: HookRegistry | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_daemon_commands(subparsers, registry=registry or HookRegistry())
    return parser


def test_daemon_start_launches_detached_child_and_waits_for_readiness(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    launched: list[tuple[list[str], dict[str, object]]] = []
    statuses = iter([None, None, {"status": "running", "pid": 4321}])

    class Process:
        pid = 4321

        def poll(self) -> None:
            return None

    def popen(command: list[str], **kwargs: object) -> Process:
        launched.append((command, kwargs))
        return Process()

    monkeypatch.setattr(daemon_commands, "daemon_status", lambda: next(statuses))
    monkeypatch.setattr(
        daemon_commands,
        "_service_status",
        lambda: {"installed": False, "loaded": False},
    )
    monkeypatch.setattr(daemon_commands.subprocess, "Popen", popen)
    monkeypatch.setattr(daemon_commands.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        daemon_commands, "_daemon_executable", lambda: "/bin/agentos-daemon"
    )

    args = _daemon_parser().parse_args(["daemon", "start", "--json"])

    assert args.handler(args) == 0
    assert json.loads(capsys.readouterr().out) == {
        "pid": 4321,
        "status": "started",
    }
    assert launched == [
        (
            ["/bin/agentos-daemon"],
            {
                "close_fds": True,
                "start_new_session": True,
                "stdin": daemon_commands.subprocess.DEVNULL,
                "stdout": daemon_commands.subprocess.DEVNULL,
                "stderr": daemon_commands.subprocess.DEVNULL,
            },
        )
    ]


def test_daemon_start_is_idempotent_when_already_running(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        daemon_commands,
        "daemon_status",
        lambda: {"status": "running", "pid": 9876},
    )
    monkeypatch.setattr(
        daemon_commands.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("must not launch another daemon"),
    )

    args = _daemon_parser().parse_args(["daemon", "start", "--json"])

    assert args.handler(args) == 0
    assert json.loads(capsys.readouterr().out) == {
        "pid": 9876,
        "status": "running",
    }


def test_daemon_start_uses_installed_launch_agent(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    statuses = iter([None, None, {"status": "running", "pid": 2468}])
    kickstarts: list[str] = []
    monkeypatch.setattr(daemon_commands, "daemon_status", lambda: next(statuses))
    monkeypatch.setattr(
        daemon_commands,
        "launch_agent_status",
        lambda: {"installed": True, "loaded": True},
    )
    monkeypatch.setattr(
        daemon_commands,
        "kickstart_launch_agent",
        lambda: kickstarts.append("kickstart"),
    )
    monkeypatch.setattr(daemon_commands.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        daemon_commands.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("launchd must own the process"),
    )

    args = _daemon_parser().parse_args(["daemon", "start", "--json"])

    assert args.handler(args) == 0
    assert kickstarts == ["kickstart"]
    assert json.loads(capsys.readouterr().out) == {
        "pid": 2468,
        "status": "started",
    }


def test_daemon_install_and_uninstall_commands_are_exposed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(daemon_commands.sys, "platform", "darwin")
    statuses = iter([None, {"status": "running", "pid": 1357}, None])
    monkeypatch.setattr(daemon_commands, "daemon_status", lambda: next(statuses))
    monkeypatch.setattr(
        daemon_commands, "_daemon_executable", lambda: "/bin/agentos-daemon"
    )
    monkeypatch.setattr(
        daemon_commands,
        "install_launch_agent",
        lambda executable: {
            "bootstrapped": False,
            "changed": True,
            "installed": True,
            "label": "org.agentos.daemon",
            "loaded": True,
            "path": "/tmp/org.agentos.daemon.plist",
        },
    )
    kickstarts: list[bool] = []
    monkeypatch.setattr(
        daemon_commands,
        "kickstart_launch_agent",
        lambda *, force=False: kickstarts.append(force),
    )
    monkeypatch.setattr(
        daemon_commands,
        "uninstall_launch_agent",
        lambda: {
            "bootstrapped": False,
            "changed": True,
            "installed": False,
            "label": "org.agentos.daemon",
            "loaded": False,
            "path": "/tmp/org.agentos.daemon.plist",
        },
    )

    install_args = _daemon_parser().parse_args(["daemon", "install", "--json"])
    assert install_args.handler(install_args) == 0
    install_payload = json.loads(capsys.readouterr().out)
    assert install_payload["status"] == "installed"
    assert kickstarts == [True]

    uninstall_args = _daemon_parser().parse_args(["daemon", "uninstall", "--json"])
    assert uninstall_args.handler(uninstall_args) == 0
    uninstall_payload = json.loads(capsys.readouterr().out)
    assert uninstall_payload["status"] == "uninstalled"


def test_daemon_start_fails_when_child_exits_before_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Process:
        pid = 4321

        def poll(self) -> int:
            return 1

    monkeypatch.setattr(daemon_commands, "daemon_status", lambda: None)
    monkeypatch.setattr(
        daemon_commands,
        "_service_status",
        lambda: {"installed": False, "loaded": False},
    )
    monkeypatch.setattr(
        daemon_commands.subprocess,
        "Popen",
        lambda *_args, **_kwargs: Process(),
    )
    monkeypatch.setattr(
        daemon_commands, "_daemon_executable", lambda: "/bin/agentos-daemon"
    )

    args = _daemon_parser().parse_args(["daemon", "start"])

    with pytest.raises(CliError, match="exited before becoming ready"):
        args.handler(args)


def test_daemon_start_terminates_child_after_readiness_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    class Process:
        pid = 4321

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            calls.append("terminate")

        def wait(self, *, timeout: float) -> int:
            calls.append(("wait", timeout))
            return 0

    times = iter([0.0, daemon_commands.DAEMON_START_TIMEOUT_SECONDS + 1.0])
    monkeypatch.setattr(daemon_commands, "daemon_status", lambda: None)
    monkeypatch.setattr(
        daemon_commands,
        "_service_status",
        lambda: {"installed": False, "loaded": False},
    )
    monkeypatch.setattr(
        daemon_commands.subprocess,
        "Popen",
        lambda *_args, **_kwargs: Process(),
    )
    monkeypatch.setattr(daemon_commands.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(
        daemon_commands, "_daemon_executable", lambda: "/bin/agentos-daemon"
    )

    args = _daemon_parser().parse_args(["daemon", "start"])

    with pytest.raises(CliError, match="start timeout"):
        args.handler(args)
    assert calls == ["terminate", ("wait", 1)]


def test_daemon_accepts_while_worker_is_busy_and_runs_events_serially(
    monkeypatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    socket_path = _short_socket_path()
    registry = HookRegistry()
    first_started = threading.Event()
    release_first = threading.Event()
    seen: list[str] = []

    def consume(invocation: HookInvocation) -> None:
        session_id = str(invocation.ctx["session_id"])
        seen.append(f"start:{session_id}")
        if session_id == "one":
            first_started.set()
            assert release_first.wait(timeout=2)
        seen.append(f"end:{session_id}")

    registry.register("agent.turn.stop", consume)
    runtime, thread = _start_runtime(registry, socket_path=socket_path)
    try:
        first_event = submit_hook_invocation(
            HookInvocation(name="agent.turn.stop", ctx={"session_id": "one"}),
            socket_path=socket_path,
        )
        assert first_started.wait(timeout=2)

        second_event = submit_hook_invocation(
            HookInvocation(name="agent.turn.stop", ctx={"session_id": "two"}),
            socket_path=socket_path,
        )
        assert first_event != second_event
        assert seen == ["start:one"]

        release_first.set()
        _wait_for(lambda: seen == ["start:one", "end:one", "start:two", "end:two"])
        status = daemon_status(socket_path=socket_path)
        assert status is not None
        assert status["status"] == "running"
        assert request_daemon_stop(socket_path=socket_path) is True
        thread.join(timeout=2)
        assert not thread.is_alive()
    finally:
        release_first.set()
        runtime.stop()
        thread.join(timeout=2)


def test_waiting_submission_returns_after_dispatch_completion(
    monkeypatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    socket_path = _short_socket_path()
    registry = HookRegistry()
    callback_started = threading.Event()
    release_callback = threading.Event()
    completed_events: list[str] = []

    def consume(_invocation: HookInvocation) -> None:
        callback_started.set()
        assert release_callback.wait(timeout=2)

    def submit_and_wait() -> None:
        completed_events.append(
            submit_hook_invocation(
                HookInvocation(name="agent.turn.stop", ctx={}),
                socket_path=socket_path,
                wait=True,
            )
        )

    registry.register("agent.turn.stop", consume)
    runtime, thread = _start_runtime(registry, socket_path=socket_path)
    waiter = threading.Thread(target=submit_and_wait)
    try:
        waiter.start()
        assert callback_started.wait(timeout=2)
        assert waiter.is_alive()
        assert daemon_status(socket_path=socket_path) is not None
        release_callback.set()
        waiter.join(timeout=2)
        assert not waiter.is_alive()
        assert len(completed_events) == 1
    finally:
        release_callback.set()
        runtime.stop()
        thread.join(timeout=2)


def test_daemon_consumer_failure_log_excludes_context_and_exception_text(
    monkeypatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    socket_path = _short_socket_path()
    registry = HookRegistry()

    def broken(invocation: HookInvocation) -> None:
        raise RuntimeError(f"must-not-log {invocation.ctx['secret']}")

    registry.register(
        "agent.turn.stop",
        broken,
        callback_id="tests.daemon-broken",
    )
    runtime, thread = _start_runtime(registry, socket_path=socket_path)
    try:
        submit_hook_invocation(
            HookInvocation(
                name="agent.turn.stop",
                ctx={"secret": "provider-prompt"},
                ctx_type="codex",
            ),
            socket_path=socket_path,
        )
        path = daemon_log_path()
        _wait_for(
            lambda: (
                path.is_file()
                and "hook_consumer_failed" in path.read_text(encoding="utf-8")
            )
        )
        text = path.read_text(encoding="utf-8")
        assert "tests.daemon-broken" in text
        assert "RuntimeError" in text
        assert "provider-prompt" not in text
        assert "must-not-log" not in text
    finally:
        runtime.stop()
        thread.join(timeout=2)


def test_hook_delivery_failure_is_logged_and_does_not_fail_command(
    monkeypatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    monkeypatch.setenv("AGENTOS_DAEMON_SOCKET", str(tmp_path / "missing.sock"))
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_hook_commands(
        subparsers,
        submitter=submit_hook_invocation,
        delivery_failure_reporter=report_hook_delivery_failure,
    )
    args = parser.parse_args(
        [
            "hook",
            "--name",
            "agent.turn.stop",
            "--ctx-type",
            "codex",
            "--ctx",
            '{"session_id":"s1","secret":"must-not-persist"}',
        ]
    )

    assert args.handler(args) == 0
    records = [
        json.loads(line)
        for line in daemon_log_path().read_text(encoding="utf-8").splitlines()
    ]
    failure = records[-1]
    assert failure["event"] == "hook_delivery_failed"
    assert failure["hook_name"] == "agent.turn.stop"
    assert failure["ctx_type"] == "codex"
    assert failure["error_type"] == "DaemonUnavailableError"
    assert "must-not-persist" not in json.dumps(failure)

    waiting_args = parser.parse_args(
        [
            "hook",
            "--name",
            "agent.turn.stop",
            "--ctx",
            "{}",
            "--wait",
        ]
    )
    with pytest.raises(CliError, match="did not complete"):
        waiting_args.handler(waiting_args)
