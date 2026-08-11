from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.testing import AgentosTestEnvironment
from agentos.cli.cli import main
from ._helpers import captured_json, write_chatlas_codex_source, write_text_file


def _isolate_chatlas(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[AgentosTestEnvironment, Path]:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    codex_home = tmp_path / "codex-home"
    return environment, codex_home


def _configure_chatlas(environment: AgentosTestEnvironment, codex_home: Path) -> None:
    write_chatlas_codex_source(environment, codex_home)


def _write_codex_rollout(
    path: Path,
    *,
    session_id: str,
    title: str = "Codex fixture",
    cwd: str = "/tmp",
    messages: list[tuple[str, str]] | None = None,
    tool_calls: list[tuple[str, dict[str, object]]] | None = None,
) -> None:
    if messages is None:
        messages = [("user", "hello"), ("assistant", "hi")]
    events = [
        {
            "timestamp": "2026-03-08T01:08:59.089Z",
            "type": "session_meta",
            "payload": {"id": session_id, "originator": "codex_cli_rs", "cwd": cwd},
        },
        {
            "timestamp": "2026-03-08T01:09:01.000Z",
            "type": "turn_context",
            "payload": {"cwd": cwd, "title": title},
        },
    ]
    for index, (role, text) in enumerate(messages, start=2):
        content_type = "input_text" if role == "user" else "output_text"
        events.append(
            {
                "timestamp": f"2026-03-08T01:09:{index:02d}.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": role,
                    "content": [{"type": content_type, "text": text}],
                },
            }
        )
    for call_index, (tool_name, arguments) in enumerate(tool_calls or []):
        call_id = f"call-{call_index}"
        events.append(
            {
                "timestamp": f"2026-03-08T01:10:{call_index:02d}.000Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": call_id,
                    "name": tool_name,
                    "arguments": json.dumps(arguments),
                },
            }
        )
        events.append(
            {
                "timestamp": f"2026-03-08T01:10:{call_index:02d}.500Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps({"output": "ok"}),
                },
            }
        )
    write_text_file(path, "\n".join(json.dumps(event) for event in events) + "\n")


def _write_codex_custom_tool_rollout(
    path: Path,
    *,
    session_id: str,
    tool_input: str,
) -> None:
    events = [
        {
            "timestamp": "2026-03-08T01:08:59.089Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "originator": "codex_cli_rs",
                "cwd": "/repo",
            },
        },
        {
            "timestamp": "2026-03-08T01:09:01.000Z",
            "type": "turn_context",
            "payload": {"cwd": "/repo", "title": "Codex custom tool fixture"},
        },
        {
            "timestamp": "2026-03-08T01:09:02.000Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "call_id": "call-1",
                "name": "apply_patch",
                "input": tool_input,
            },
        },
        {
            "timestamp": "2026-03-08T01:09:02.500Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "call-1",
                "output": "Success",
            },
        },
    ]
    write_text_file(path, "\n".join(json.dumps(event) for event in events) + "\n")


def _write_codex_rollout_script(
    path: Path,
    *,
    session_id: str,
    script: list[tuple[str, str]],
    cwd: str = "/tmp",
) -> None:
    """Rollout writer with messages and tool calls interleaved in script order."""
    events: list[dict[str, object]] = [
        {
            "timestamp": "2026-03-08T01:08:59.089Z",
            "type": "session_meta",
            "payload": {"id": session_id, "originator": "codex_cli_rs", "cwd": cwd},
        },
        {
            "timestamp": "2026-03-08T01:09:01.000Z",
            "type": "turn_context",
            "payload": {"cwd": cwd, "title": "Codex fixture"},
        },
    ]
    for index, (kind, text) in enumerate(script, start=2):
        timestamp = f"2026-03-08T01:09:{index:02d}"
        if kind == "tool":
            call_id = f"call-{index}"
            events.append(
                {
                    "timestamp": f"{timestamp}.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "call_id": call_id,
                        "name": text,
                        "arguments": json.dumps({"arg": text}),
                    },
                }
            )
            events.append(
                {
                    "timestamp": f"{timestamp}.500Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps({"output": "ok"}),
                    },
                }
            )
            continue
        content_type = "input_text" if kind == "user" else "output_text"
        events.append(
            {
                "timestamp": f"{timestamp}.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": kind,
                    "content": [{"type": content_type, "text": text}],
                },
            }
        )
    write_text_file(path, "\n".join(json.dumps(event) for event in events) + "\n")


def _index_rows(chatlas_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted((chatlas_root / "index" / "sessions").rglob("*.jsonl")):
        rows.extend(
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        )
    return rows


def _inline_selection_events(
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> list[dict[str, object]]:
    assert main([*argv, "--json"]) == 0
    payload = captured_json(capsys)
    chat = payload["chat"]
    assert isinstance(chat, dict)
    events = chat["events"]
    assert isinstance(events, list)
    return events


def _selection_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> str:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675aaa"
    _write_codex_rollout(
        codex_home / "sessions" / "2026" / "03" / "08" / f"rollout-{session_id}.jsonl",
        session_id=session_id,
        messages=[
            ("user", "alpha question"),
            ("assistant", "alpha answer"),
            ("user", "beta question"),
            ("assistant", "beta answer"),
        ],
    )
    _configure_chatlas(environment, codex_home)
    assert (
        main(
            [
                "chatlas",
                "index",
                "update",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    return session_id
