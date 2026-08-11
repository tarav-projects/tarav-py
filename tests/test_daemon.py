from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path
from uuid import uuid4

from agentos.daemon import (
    DaemonRuntime,
    daemon_log_path,
    daemon_status,
    request_daemon_stop,
    submit_hook_invocation,
)
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

    registry.register("agent.turn.stop", consume, execution="daemon")
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
        execution="daemon",
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
    registry = HookRegistry()
    registry.register(
        "agent.turn.stop",
        lambda invocation: None,
        callback_id="tests.deferred",
        execution="daemon",
    )
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_hook_commands(subparsers, registry=registry)
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
