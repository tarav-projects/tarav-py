from __future__ import annotations

import argparse
import json
import threading
from pathlib import Path
from typing import cast
from uuid import uuid4

import tarav.daemon.client as daemon_client
import tarav.daemon.commands as daemon_commands
from tarav.daemon import DaemonRuntime
from tarav.hooks import HookInvocation, HookRegistry
from tarav.testing import TaravTestEnvironment
from tarav.cli.cli import build_parser, main
from tarav.runtime import TaravRuntime, create_runtime


def test_daemon_hook_command_accepts_inline_json(monkeypatch, capsys) -> None:
    submitted: list[HookInvocation] = []
    monkeypatch.setattr(
        daemon_client,
        "submit_hook_invocation",
        lambda invocation, *, wait=False: submitted.append(invocation),
    )

    assert (
        main(
            [
                "daemon",
                "hook",
                "--name",
                "agent.session.start",
                "--ctx",
                "{}",
            ]
        )
        == 0
    )
    assert submitted == [HookInvocation(name="agent.session.start", ctx={})]
    assert capsys.readouterr().out == ""


def test_top_level_daemon_status_reports_stopped(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setenv("TARAV_DAEMON_SOCKET", str(tmp_path / "daemon.sock"))
    monkeypatch.setattr(
        daemon_commands,
        "_service_status",
        lambda: {"installed": False, "loaded": False},
    )

    assert main(["daemon", "status", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "socket_path": str(tmp_path / "daemon.sock"),
        "status": "stopped",
        "service": {"installed": False, "loaded": False},
    }


def test_cli_composition_does_not_run_subsystem_callbacks_locally(monkeypatch) -> None:
    seen: list[HookInvocation] = []
    submitted: list[tuple[HookInvocation, bool]] = []

    def submit(invocation: HookInvocation, *, wait: bool = False) -> None:
        submitted.append((invocation, wait))

    monkeypatch.setattr(daemon_client, "submit_hook_invocation", submit)

    def subsystem_hooks(registry: HookRegistry) -> None:
        registry.register(
            "agent.session.start", seen.append, callback_id="test.subsystem"
        )

    parser = build_parser(hook_registrars=(subsystem_hooks,))
    args = parser.parse_args(
        [
            "daemon",
            "hook",
            "--name",
            "agent.session.start",
            "--ctx-type",
            "codex",
            "--ctx",
            '{"session_id":"s1"}',
        ]
    )

    assert isinstance(args, argparse.Namespace)
    assert args.handler(args) == 0
    assert seen == []
    assert submitted == [
        (
            HookInvocation(
                name="agent.session.start",
                ctx={"session_id": "s1"},
                ctx_type="codex",
            ),
            False,
        )
    ]


def test_cli_adapter_delegates_command_composition_to_runtime() -> None:
    registered: list[str] = []

    class StubRuntime:
        def register_commands(
            self,
            subparsers: argparse._SubParsersAction,
        ) -> None:
            parser = subparsers.add_parser("runtime-owned")
            parser.set_defaults(handler=lambda _args: registered.append("called") or 0)

    parser = build_parser(runtime=cast(TaravRuntime, StubRuntime()))
    args = parser.parse_args(["runtime-owned"])

    assert args.handler(args) == 0
    assert registered == ["called"]


def test_daemon_hook_samples_codex_prompt_submission(
    monkeypatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    socket_path = Path("/tmp") / f"agentos-e2e-{uuid4().hex}.sock"
    monkeypatch.setenv("TARAV_DAEMON_SOCKET", str(socket_path))
    ready = threading.Event()
    runtime = DaemonRuntime(create_runtime().hooks, socket_path=socket_path)
    thread = threading.Thread(
        target=runtime.serve_forever,
        kwargs={"ready_event": ready},
        daemon=True,
    )
    thread.start()
    assert ready.wait(timeout=2)
    try:
        assert (
            main(
                [
                    "daemon",
                    "hook",
                    "--name",
                    "agent.prompt.submit",
                    "--ctx-type",
                    "codex",
                    "--ctx",
                    '{"session_id":"s1","prompt":"hello"}',
                    "--wait",
                ]
            )
            == 0
        )
    finally:
        runtime.stop()
        thread.join(timeout=2)

    sample_path = environment.tarav_home / "hooks" / "context-samples.jsonl"
    record = json.loads(sample_path.read_text(encoding="utf-8"))
    assert record["hook_name"] == "agent.prompt.submit"
    assert record["ctx_type"] == "codex"
    assert record["ctx"] == {"session_id": "s1", "prompt": "hello"}
