from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentos.chat import commands as chat_commands
from agentos.cli import main


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _set_iso_mtime(path: Path, timestamp: str) -> None:
    normalized = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
    seconds = datetime.fromisoformat(normalized).astimezone(timezone.utc).timestamp()
    os.utime(path, (seconds, seconds))


def _write_codex_rollout(path: Path, *, session_id: str) -> None:
    records = [
        {
            "timestamp": "2026-03-08T01:08:59.089Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "originator": "codex_cli_rs",
                "source": "cli",
            },
        }
    ]
    _write(path, "\n".join(json.dumps(record) for record in records) + "\n")
    _set_iso_mtime(path, records[0]["timestamp"])


def _write_codex_session_index(
    path: Path,
    *,
    session_id: str,
    thread_name: str,
    updated_at: str = "2026-03-10T12:13:33.263726Z",
) -> None:
    _write(
        path,
        json.dumps(
            {
                "id": session_id,
                "thread_name": thread_name,
                "updated_at": updated_at,
            }
        )
        + "\n",
    )


def _write_pi_session(
    path: Path,
    *,
    session_id: str,
    cwd: str = "/Users/pereiro/workspaces/pi-agent",
    user_text: str = "hello from pi",
    assistant_text: str = "pi reply",
    include_custom_message: bool = False,
) -> None:
    records = [
        {
            "type": "session",
            "version": 3,
            "id": session_id,
            "timestamp": "2026-04-17T19:14:52.021Z",
            "cwd": cwd,
        },
        {
            "type": "model_change",
            "timestamp": "2026-04-17T19:14:52.022Z",
            "provider": "openai-codex",
            "modelId": "gpt-5.4-mini",
        },
        {
            "type": "thinking_level_change",
            "timestamp": "2026-04-17T19:14:52.023Z",
            "thinkingLevel": "medium",
        },
    ]
    if include_custom_message:
        records.append(
            {
                "type": "custom_message",
                "timestamp": "2026-04-17T19:14:52.024Z",
                "customType": "iterante-start",
                "display": True,
                "content": "mission prelude",
            }
        )
    records.extend(
        [
            {
                "type": "message",
                "id": "msg-user-1",
                "timestamp": "2026-04-17T19:14:53.000Z",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": user_text}],
                },
            },
            {
                "type": "message",
                "id": "msg-assistant-1",
                "timestamp": "2026-04-17T19:14:54.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "internal plan"},
                        {"type": "text", "text": assistant_text},
                        {"type": "toolCall", "name": "ls", "toolCallId": "tool-1"},
                    ],
                    "metadata": {
                        "provider": "openai-codex",
                        "model": "gpt-5.4-mini",
                        "responseId": "resp_1",
                    },
                },
            },
            {
                "type": "message",
                "id": "msg-tool-1",
                "timestamp": "2026-04-17T19:14:55.000Z",
                "message": {
                    "role": "toolResult",
                    "content": [{"type": "text", "text": "tool output"}],
                },
            },
        ]
    )
    _write(path, "\n".join(json.dumps(record) for record in records) + "\n")
    _set_iso_mtime(path, "2026-04-17T19:14:55.000Z")


def _write_project_marker(project_root: Path) -> None:
    _write(
        project_root / ".agentos" / "project.json",
        json.dumps(
            {
                "class": "agentos.project",
                "schema_version": 1,
                "project_id": "00000000-0000-4000-8000-000000000001",
            }
        )
        + "\n",
    )


def _write_project_config(
    path: Path,
    *,
    provider_instances: list[dict[str, object]] | None = None,
) -> None:
    _write(
        path,
        json.dumps(
            {
                "class": "agentos.project.config",
                "schema_version": 1,
                "chat": {
                    "provider_instances": provider_instances or [],
                },
            }
        )
        + "\n",
    )


def test_chat_help_exposes_debug_surface(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["chat", "--help"])
    assert exc_info.value.code == 0
    output = capsys.readouterr().out

    assert "{debug,accounts}" in output
    assert "session" not in output


def test_chat_debug_list_returns_live_inventory(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    thread_name = "live-debug-thread"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "08" / f"rollout-2026-03-08T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(["chat", "debug", "list", "--provider", "codex", "--output", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "chat debug list"
    assert payload["session_count"] == 1
    session = payload["sessions"][0]
    assert session["provider"] == "codex"
    assert session["session_id"] == session_id
    assert session["display_name"] == thread_name
    assert session["native"] == {"thread_name": thread_name}


def test_chat_debug_find_returns_live_match_and_findings(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    thread_name = "grep-debug-thread"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "08" / f"rollout-2026-03-08T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(["chat", "debug", "find", thread_name, "--artifacts", "--grep", "--full-output"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "chat debug find"
    assert payload["session_count"] == 1
    session = payload["sessions"][0]
    assert session["provider"] == "codex"
    assert session["session_id"] == session_id
    assert session["match"]["fields"] == [{"field": "thread_name", "value": thread_name}]
    assert session["backing_artifact_count"] == 2
    assert payload["search_finding_count"] >= 1
    assert payload["search_findings"]
    assert payload["provider_diagnostics"]


def test_chat_debug_list_returns_live_pi_inventory(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "019d9cde-0ff5-75a6-b36d-c11a19c2e1b4"
    cwd = "/Users/pereiro/Documents/workspaces/oba-workspace/agentos-iterante-dev"
    _write_pi_session(
        home / ".pi" / "agent" / "sessions" / "project" / f"2026-04-17T19-14-52-021Z_{session_id}.jsonl",
        session_id=session_id,
        cwd=cwd,
    )

    assert main(["chat", "debug", "list", "--provider", "pi", "--output", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "chat debug list"
    assert payload["session_count"] == 1
    session = payload["sessions"][0]
    assert session["provider"] == "pi"
    assert session["session_id"] == session_id
    assert session["created_at"] == "2026-04-17T19:14:52.021Z"
    assert session["extractable"] is True
    assert session["native"] == {
        "cwd": cwd,
        "model_provider": "openai-codex",
        "model_id": "gpt-5.4-mini",
        "thinking_level": "medium",
    }


def test_chat_debug_list_supports_explicit_project_target(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    project_root = tmp_path / "project"
    workspace = tmp_path / "workspace"
    home.mkdir()
    project_root.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(workspace)

    _write_project_marker(project_root)
    _write_project_config(
        project_root / ".agentos" / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "project-codex",
                "home": str(home / ".codex"),
            }
        ],
    )

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    thread_name = "project-debug-thread"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "08" / f"rollout-2026-03-08T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert (
        main(
            [
                "chat",
                "debug",
                "list",
                "--project",
                str(project_root),
                "--provider",
                "codex",
                "--output",
                "json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "chat debug list"
    assert payload["session_count"] == 1
    session = payload["sessions"][0]
    assert session["provider"] == "codex"
    assert session["session_id"] == session_id
    assert session["display_name"] == thread_name


def test_load_card_session_context_loads_gemini_session_data_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_path = tmp_path / "gemini-session.json"
    _write(session_path, "{}")

    observed_load_calls: list[Path] = []
    session_data = {
        "sessionId": "gemini-session-1",
        "startTime": "2026-03-08T10:00:00Z",
    }

    def fake_load_gemini_cli_session_data(path: Path) -> dict[str, object]:
        observed_load_calls.append(path)
        return session_data

    def fake_extract_dialog_from_gemini_cli_session(
        *,
        session_data: dict[str, object],
        session_id: str,
        raw: bool,
    ) -> list[SimpleNamespace]:
        assert session_data is not None
        assert session_id == "gemini-session-1"
        assert raw is False
        return [
            SimpleNamespace(
                timestamp="2026-03-08T11:00:00Z",
                role="user",
                text="hello from gemini",
            )
        ]

    monkeypatch.setattr(
        chat_commands,
        "load_gemini_cli_session_data",
        fake_load_gemini_cli_session_data,
    )
    monkeypatch.setattr(
        chat_commands,
        "extract_dialog_from_gemini_cli_session",
        fake_extract_dialog_from_gemini_cli_session,
    )

    created_at, preview = chat_commands._load_card_session_context(
        provider="gemini-cli",
        path=session_path,
        session_id="fallback-session-id",
    )

    assert observed_load_calls == [session_path]
    assert created_at == datetime(2026, 3, 8, 11, 0, tzinfo=timezone.utc).timestamp()
    assert preview == "hello from gemini"
