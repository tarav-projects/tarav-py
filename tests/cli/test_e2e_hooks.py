from __future__ import annotations

import argparse
import json
from pathlib import Path

import agentos.daemon.commands as daemon_commands
from agentos.hooks import HookInvocation, HookRegistry
from agentos.testing import AgentosTestEnvironment
from agentos.cli.cli import build_parser, main


def test_top_level_hook_command_accepts_inline_json(capsys) -> None:
    assert main(["hook", "--name", "agent.session.start", "--ctx", "{}"]) == 0
    assert capsys.readouterr().out == ""


def test_top_level_daemon_status_reports_stopped(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setenv("AGENTOS_DAEMON_SOCKET", str(tmp_path / "daemon.sock"))
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


def test_cli_composition_can_register_subsystem_callbacks() -> None:
    seen: list[HookInvocation] = []

    def subsystem_hooks(registry: HookRegistry) -> None:
        registry.register(
            "agent.session.start", seen.append, callback_id="test.subsystem"
        )

    parser = build_parser(hook_registrars=(subsystem_hooks,))
    args = parser.parse_args(
        [
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
    assert seen == [
        HookInvocation(
            name="agent.session.start",
            ctx={"session_id": "s1"},
            ctx_type="codex",
        )
    ]


def test_top_level_cli_samples_codex_prompt_submission(
    monkeypatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    assert (
        main(
            [
                "hook",
                "--name",
                "agent.prompt.submit",
                "--ctx-type",
                "codex",
                "--ctx",
                '{"session_id":"s1","prompt":"hello"}',
            ]
        )
        == 0
    )

    sample_path = environment.agentos_home / "hooks" / "context-samples.jsonl"
    record = json.loads(sample_path.read_text(encoding="utf-8"))
    assert record["hook_name"] == "agent.prompt.submit"
    assert record["ctx_type"] == "codex"
    assert record["ctx"] == {"session_id": "s1", "prompt": "hello"}
