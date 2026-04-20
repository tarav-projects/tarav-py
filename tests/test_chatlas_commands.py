from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

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


def _write_codex_dialog_rollout(
    path: Path,
    *,
    session_id: str,
    user_text: str = "hello from codex",
    assistant_text: str = "codex reply",
) -> None:
    records = [
        {
            "timestamp": "2026-03-08T01:08:59.089Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "originator": "codex_cli_rs",
                "source": "cli",
            },
        },
        {
            "timestamp": "2026-03-08T01:08:59.093Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"{user_text}<system-reminder>\nmetadata tail",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-03-08T01:08:59.094Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": assistant_text,
                    }
                ],
            },
        },
    ]
    _write(path, "\n".join(json.dumps(record) for record in records) + "\n")
    _set_iso_mtime(path, records[-1]["timestamp"])


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


def _write_openclaw_session(
    sessions_dir: Path,
    *,
    session_id: str,
    session_key: str = "agent:main:telegram:direct:734641842",
) -> Path:
    records = [
        {
            "type": "session",
            "version": 3,
            "id": session_id,
            "timestamp": "2026-03-08T12:05:10.000Z",
            "cwd": "/Users/pereiro/.openclaw/workspace",
        },
        {
            "type": "message",
            "id": "msg-user-1",
            "timestamp": "2026-03-08T12:05:12.017Z",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "hello from openclaw"}],
            },
        },
        {
            "type": "message",
            "id": "msg-assistant-1",
            "timestamp": "2026-03-08T12:05:18.000Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "[[reply_to_current]] openclaw reply"}],
            },
        },
    ]
    transcript_path = sessions_dir / f"{session_id}.jsonl"
    _write(transcript_path, "\n".join(json.dumps(record) for record in records) + "\n")
    _write(
        sessions_dir / "sessions.json",
        json.dumps(
            {
                session_key: {
                    "sessionId": session_id,
                    "sessionFile": str(transcript_path),
                    "updatedAt": 1772995738498,
                }
            }
        ),
    )
    return transcript_path


def _write_pi_session(
    path: Path,
    *,
    session_id: str,
    cwd: str = "/Users/pereiro/Documents/workspaces/oba-workspace/agentos-iterante-dev",
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
        ]
    )
    _write(path, "\n".join(json.dumps(record) for record in records) + "\n")
    _set_iso_mtime(path, "2026-04-17T19:14:54.000Z")


def _write_copilot_events(
    path: Path,
    *,
    session_id: str,
    user_text: str = "hello from copilot",
    assistant_text: str = "copilot reply",
) -> None:
    records = [
        {
            "type": "session.start",
            "timestamp": "2026-04-18T11:00:00.000Z",
            "data": {
                "sessionId": session_id,
                "producer": "copilot-agent",
            },
        },
        {
            "type": "user.message",
            "timestamp": "2026-04-18T11:00:01.000Z",
            "data": {
                "content": [{"type": "text", "text": user_text}],
            },
        },
        {
            "type": "assistant.message",
            "timestamp": "2026-04-18T11:00:02.000Z",
            "data": {
                "content": [{"type": "text", "text": assistant_text}],
                "reasoningText": "check repository state",
                "toolRequests": [
                    {"name": "shell", "arguments": {"cmd": "git status"}}
                ],
            },
        },
        {
            "type": "tool.execution_start",
            "timestamp": "2026-04-18T11:00:03.000Z",
            "data": {
                "toolName": "shell",
                "command": "git status",
            },
        },
        {
            "type": "session.shutdown",
            "timestamp": "2026-04-18T11:00:04.000Z",
            "data": {
                "totalPremiumRequests": 1,
                "modelMetrics": {"inputTokens": 12, "outputTokens": 34},
            },
        },
    ]
    _write(path, "\n".join(json.dumps(record) for record in records) + "\n")
    _set_iso_mtime(path, "2026-04-18T11:00:04.000Z")


def _write_global_config(
    path: Path,
    *,
    provider_instances: list[dict[str, object]] | None = None,
) -> None:
    home = path.parent.parent / "home"
    _write(
        path,
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "agent": {
                    "instances": [
                        {
                            "provider": "codex",
                            "id": "codex-main",
                            "home": str(home / ".codex"),
                            "cli_command": ["/opt/homebrew/bin/codex"],
                            "env": {
                                "CODEX_HOME": str(home / ".codex"),
                            },
                        },
                        {
                            "provider": "claude-code",
                            "id": "claude-main",
                            "homes": {
                                "cli": str(home / ".claude"),
                                "desktop": str(home / "Library" / "Application Support" / "Claude"),
                            },
                            "cli_command": ["/opt/homebrew/bin/claude"],
                        },
                        {
                            "provider": "openclaw",
                            "id": "openclaw-main",
                            "home": str(home / ".openclaw"),
                        },
                        *(provider_instances or []),
                    ]
                },
            }
        ),
    )


def _git_output(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def _default_chatlas_root(home: Path) -> Path:
    return home / "Documents" / "chatlas"


def _legacy_chatlas_root(agentos_home: Path) -> Path:
    return agentos_home / "chatlas"


def _chatlas_home_root(home: Path, source_home: Path) -> Path:
    return _default_chatlas_root(home) / "raw" / source_home.relative_to(home)


def _chatlas_update_argv(
    *args: str,
    output_mode: str | None = "json",
    verbose_mode: str | None = None,
) -> list[str]:
    argv = ["chatlas", "update", *args]
    if verbose_mode is not None:
        argv.extend(["--verbose-mode", verbose_mode])
    if output_mode is not None:
        argv.extend(["--output-mode", output_mode])
    return argv


def test_chatlas_update_mirrors_default_codex_home_and_commits(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    thread_name = "chatlas-default-thread"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )
    _write(home / ".codex" / "notes.md", "# notes\n")
    _write(home / ".codex" / "log" / "skip.txt", "skip\n")
    _write(home / ".codex" / "auth.json", '{"token":"secret"}\n')

    assert main(_chatlas_update_argv("--provider", "codex")) == 0

    payload = json.loads(capsys.readouterr().out)
    chatlas_root = _default_chatlas_root(home)
    source_root = home / ".codex"
    destination_root = _chatlas_home_root(home, source_root)

    assert payload["command"] == "chatlas update"
    assert payload["committed"] is True
    assert payload["changes_detected"] is True
    assert payload["synced_instance_count"] == 1
    assert payload["skipped_instance_count"] == 0
    assert payload["normalized_session_count"] == 1
    assert payload["derived_transcript_session_count"] == 1
    assert payload["derived_summary_count"] == 1
    assert payload["derived_summary_counts"] == {"brief": 1, "detailed": 1}
    assert payload["instances"][0]["instance"] == "codex-main"
    assert payload["instances"][0]["destination_root"] == str(destination_root)
    assert payload["manifest_path"] is not None
    assert Path(payload["normalized_sessions_path"]).is_file()
    assert Path(payload["derived_summaries_path"]).is_file()
    assert Path(payload["derived_summary_paths"]["detailed"]).is_file()
    assert (
        destination_root
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    ).exists()
    assert (destination_root / "notes.md").exists()
    assert not (destination_root / "log" / "skip.txt").exists()
    assert not (destination_root / "auth.json").exists()
    manifest_path = Path(payload["manifest_path"])
    assert manifest_path.is_file()
    normalized_rows = [
        json.loads(line)
        for line in Path(payload["normalized_sessions_path"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(normalized_rows) == 1
    assert normalized_rows[0]["class"] == "agentos.chatlas.session"
    assert normalized_rows[0]["provider"] == "codex"
    assert normalized_rows[0]["session_id"] == session_id
    assert normalized_rows[0]["display_name"] == thread_name
    assert normalized_rows[0]["native"] == {"thread_name": thread_name}
    derived_md_path = (
        _default_chatlas_root(home)
        / "derived"
        / "transcripts"
        / "codex"
        / normalized_rows[0]["provider_instance_fingerprint"]
        / f"{session_id}.md"
    )
    assert derived_md_path.is_file()

    log_subject = _git_output(chatlas_root, "log", "-1", "--pretty=%s")
    assert log_subject.startswith("chatlas update: ")


def test_chatlas_update_supports_configured_pi_provider(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    pi_home = home / ".pi" / "profiles" / "codex-mm"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "pi",
                "id": "pi-mm",
                "home": str(pi_home),
            }
        ],
    )

    session_id = "019d9cde-0ff5-75a6-b36d-c11a19c2e1b4"
    transcript_path = (
        pi_home
        / "sessions"
        / "--Users-pereiro-Documents-workspaces-oba-workspace-agentos-iterante-dev--"
        / f"2026-04-17T19-14-52-021Z_{session_id}.jsonl"
    )
    _write_pi_session(
        transcript_path,
        session_id=session_id,
        include_custom_message=True,
        assistant_text="pi assistant",
    )
    _write(pi_home / "settings.json", json.dumps({"defaultProvider": "openai-codex"}) + "\n")
    _write(pi_home / "auth.json", '{"token":"secret"}\n')
    _write(pi_home / "bin" / "pi-helper", "#!/bin/sh\n")
    _write(pi_home / "notes.md", "do not archive this\n")

    assert main(_chatlas_update_argv("--provider", "pi")) == 0

    payload = json.loads(capsys.readouterr().out)
    chatlas_root = _default_chatlas_root(home)
    destination_root = _chatlas_home_root(home, pi_home)

    assert payload["command"] == "chatlas update"
    assert payload["committed"] is True
    assert payload["changes_detected"] is True
    assert payload["synced_instance_count"] == 1
    assert payload["normalized_session_count"] == 1
    assert payload["derived_transcript_session_count"] == 1
    assert payload["instances"][0]["instance"] == "pi-mm"
    assert payload["instances"][0]["destination_root"] == str(destination_root)
    assert sorted(payload["instances"][0]["includes"]) == ["sessions/**", "settings.json"]
    assert transcript_path.relative_to(pi_home).is_relative_to(Path("sessions"))
    assert (destination_root / transcript_path.relative_to(pi_home)).is_file()
    assert (destination_root / "settings.json").is_file()
    assert not (destination_root / "auth.json").exists()
    assert not (destination_root / "bin" / "pi-helper").exists()
    assert not (destination_root / "notes.md").exists()

    normalized_rows = [
        json.loads(line)
        for line in Path(payload["normalized_sessions_path"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(normalized_rows) == 1
    assert normalized_rows[0]["provider"] == "pi"
    assert normalized_rows[0]["instance"] == "pi-mm"
    assert normalized_rows[0]["session_id"] == session_id
    assert normalized_rows[0]["native"] == {
        "cwd": "/Users/pereiro/Documents/workspaces/oba-workspace/agentos-iterante-dev",
        "model_provider": "openai-codex",
        "model_id": "gpt-5.4-mini",
        "thinking_level": "medium",
    }

    derived_md_path = (
        chatlas_root
        / "derived"
        / "transcripts"
        / "pi"
        / normalized_rows[0]["provider_instance_fingerprint"]
        / f"{session_id}.md"
    )
    assert derived_md_path.is_file()
    transcript_markdown = derived_md_path.read_text(encoding="utf-8")
    assert "mission prelude" in transcript_markdown
    assert "pi assistant" in transcript_markdown


def test_chatlas_update_copilot_uses_raw_retention_whitelist(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    copilot_home = home / ".copilot"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "copilot-cli",
                "id": "copilot-main",
                "home": str(copilot_home),
            }
        ],
    )

    session_id = "0005d4b6-a983-4801-8b2a-fa626db1cf50"
    legacy_session_id = "11111111-1111-4111-8111-111111111111"
    session_root = copilot_home / "session-state" / session_id
    _write_copilot_events(
        session_root / "events.jsonl",
        session_id=session_id,
        user_text="retain copilot user input",
        assistant_text="retain copilot assistant output",
    )
    _write_copilot_events(
        copilot_home / "session-state" / f"{legacy_session_id}.jsonl",
        session_id=legacy_session_id,
        user_text="retain legacy copilot user input",
        assistant_text="retain legacy copilot assistant output",
    )
    _write(session_root / "files" / "user-attachment.txt", "session artifact\n")
    _write(session_root / "plan.md", "# Plan\n- inspect retention\n")
    _write(session_root / "checkpoints" / "001-implementation.md", "# Checkpoint\n")
    _write(copilot_home / "copilot-instructions.md", "Prefer concise answers.\n")

    _write(session_root / "workspace.yaml", "cwd: /tmp/project\n")
    _write(session_root / "checkpoints" / "index.md", "# Index\n")
    _write(session_root / "vscode.metadata.json", "{}\n")
    _write(session_root / "session.db", "opaque\n")
    _write(session_root / "rewind-snapshots" / "index.json", "{}\n")
    _write(
        session_root / "rewind-snapshots" / "backups" / "snapshot.txt",
        "workspace copy\n",
    )
    _write(copilot_home / "session-state" / "inuse.99735.lock", "locked\n")
    _write(
        copilot_home / "command-history-state.json",
        '{"commands":["private spillover"]}\n',
    )
    _write(copilot_home / "config.json", '{"account":"local"}\n')
    _write(copilot_home / "logs" / "copilot.log", "noise\n")

    assert main(_chatlas_update_argv("--provider", "copilot-cli")) == 0

    payload = json.loads(capsys.readouterr().out)
    chatlas_root = _default_chatlas_root(home)
    destination_root = _chatlas_home_root(home, copilot_home)
    instance_payload = payload["instances"][0]
    expected_includes = [
        "session-state/**/events.jsonl",
        "session-state/*.jsonl",
        "session-state/**/files/**",
        "session-state/**/plan.md",
        "session-state/**/checkpoints/*.md",
        "copilot-instructions.md",
    ]
    expected_excludes = [
        "pkg/",
        "logs/",
        "ide/",
        "session-state/**/workspace.yaml",
        "session-state/**/checkpoints/index.md",
        "session-state/**/vscode.metadata.json",
        "session-state/**/session.db",
        "session-state/**/rewind-snapshots/**",
        "session-state/**/*.lock",
        "command-history-state.json",
        "config.json",
    ]

    assert payload["command"] == "chatlas update"
    assert payload["committed"] is True
    assert payload["changes_detected"] is True
    assert payload["synced_instance_count"] == 1
    assert payload["normalized_session_count"] == 2
    assert payload["derived_transcript_session_count"] == 2
    assert instance_payload["instance"] == "copilot-main"
    assert instance_payload["destination_root"] == str(destination_root)
    assert instance_payload["includes"] == expected_includes
    assert instance_payload["excludes"] == expected_excludes

    assert (destination_root / "session-state" / session_id / "events.jsonl").is_file()
    assert (destination_root / "session-state" / f"{legacy_session_id}.jsonl").is_file()
    assert (
        destination_root / "session-state" / session_id / "files" / "user-attachment.txt"
    ).is_file()
    assert (destination_root / "session-state" / session_id / "plan.md").is_file()
    assert (
        destination_root / "session-state" / session_id / "checkpoints" / "001-implementation.md"
    ).is_file()
    assert (destination_root / "copilot-instructions.md").is_file()
    assert not (destination_root / "session-state" / session_id / "workspace.yaml").exists()
    assert not (
        destination_root / "session-state" / session_id / "checkpoints" / "index.md"
    ).exists()
    assert not (
        destination_root / "session-state" / session_id / "vscode.metadata.json"
    ).exists()
    assert not (destination_root / "session-state" / session_id / "session.db").exists()
    assert not (destination_root / "session-state" / session_id / "rewind-snapshots").exists()
    assert not (destination_root / "session-state" / "inuse.99735.lock").exists()
    assert not (destination_root / "command-history-state.json").exists()
    assert not (destination_root / "config.json").exists()
    assert not (destination_root / "logs" / "copilot.log").exists()

    normalized_rows = [
        json.loads(line)
        for line in Path(payload["normalized_sessions_path"])
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    normalized_by_session_id = {row["session_id"]: row for row in normalized_rows}
    assert sorted(normalized_by_session_id) == [session_id, legacy_session_id]
    assert normalized_by_session_id[session_id]["provider"] == "copilot-cli"
    assert normalized_by_session_id[session_id]["instance"] == "copilot-main"
    assert normalized_by_session_id[legacy_session_id]["provider"] == "copilot-cli"
    assert normalized_by_session_id[legacy_session_id]["instance"] == "copilot-main"

    derived_md_path = (
        chatlas_root
        / "derived"
        / "transcripts"
        / "copilot-cli"
        / normalized_by_session_id[session_id]["provider_instance_fingerprint"]
        / f"{session_id}.md"
    )
    legacy_derived_md_path = (
        chatlas_root
        / "derived"
        / "transcripts"
        / "copilot-cli"
        / normalized_by_session_id[legacy_session_id]["provider_instance_fingerprint"]
        / f"{legacy_session_id}.md"
    )
    transcript_markdown = derived_md_path.read_text(encoding="utf-8")
    legacy_transcript_markdown = legacy_derived_md_path.read_text(encoding="utf-8")
    assert "retain copilot user input" in transcript_markdown
    assert "retain copilot assistant output" in transcript_markdown
    assert "retain legacy copilot user input" in legacy_transcript_markdown
    assert "retain legacy copilot assistant output" in legacy_transcript_markdown


def test_chatlas_update_second_run_skips_commit_when_unchanged(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    payload = json.loads(capsys.readouterr().out)

    chatlas_root = _default_chatlas_root(home)
    assert payload["changes_detected"] is False
    assert payload["committed"] is False
    assert payload["manifest_path"] is None
    assert payload["commit_message"] is None
    assert _git_output(chatlas_root, "rev-list", "--count", "HEAD") == "1"


def test_chatlas_update_default_caches_skip_deep_rebuild_work(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from agentos.chatlas import core as chatlas_core
    from agentos.chatlas import raw as chatlas_raw

    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name="cached-thread",
    )
    _write(home / ".codex" / "notes.md", "# notes\n")

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    first_payload = json.loads(capsys.readouterr().out)

    chatlas_root = _default_chatlas_root(home)
    raw_cache_path = chatlas_raw._chatlas_raw_scan_cache_path(chatlas_root)
    normalized_cache_path = chatlas_core._normalized_session_cache_path(chatlas_root)
    transcript_cache_path = chatlas_core._derived_transcript_cache_path(chatlas_root)

    assert first_payload["scan_cache_enabled"] is True
    assert first_payload["normalized_cache_enabled"] is True
    assert first_payload["transcript_cache_enabled"] is True
    assert raw_cache_path.is_file()
    assert normalized_cache_path.is_file()
    assert transcript_cache_path.is_file()
    assert "/cache/" in (chatlas_root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert _git_output(chatlas_root, "ls-files", "cache/raw-scan-v1.json") == ""
    assert _git_output(chatlas_root, "ls-files", "cache/normalized-sessions-v1.json") == ""
    assert _git_output(chatlas_root, "ls-files", "cache/derived-transcripts-v1.json") == ""
    assert _git_output(chatlas_root, "status", "--porcelain") == ""

    def fail_match(*args, **kwargs):
        raise AssertionError("expected scan cache to bypass destination content comparison")

    def fail_normalized_record(*args, **kwargs):
        raise AssertionError("expected normalized cache to bypass normalized session rebuild")

    def fail_render(*args, **kwargs):
        raise AssertionError("expected transcript cache to bypass transcript rendering")

    monkeypatch.setattr(chatlas_raw, "_chatlas_archive_files_match", fail_match)
    monkeypatch.setattr(chatlas_core, "_normalized_session_record", fail_normalized_record)
    monkeypatch.setattr(chatlas_core, "_render_transcript", fail_render)

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["scan_cache_enabled"] is True
    assert payload["normalized_cache_enabled"] is True
    assert payload["transcript_cache_enabled"] is True
    assert payload["changes_detected"] is False
    assert payload["committed"] is False
    assert _git_output(chatlas_root, "status", "--porcelain") == ""


def test_chatlas_update_can_disable_scan_cache(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from agentos.chatlas import raw as chatlas_raw

    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name="uncached-thread",
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    original_match = chatlas_raw._chatlas_archive_files_match
    match_calls = {"count": 0}

    def counting_match(*args, **kwargs):
        match_calls["count"] += 1
        return original_match(*args, **kwargs)

    monkeypatch.setattr(chatlas_raw, "_chatlas_archive_files_match", counting_match)

    assert main(_chatlas_update_argv("--provider", "codex", "--scan-cache=false")) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["scan_cache_enabled"] is False
    assert payload["normalized_cache_enabled"] is True
    assert payload["transcript_cache_enabled"] is True
    assert payload["changes_detected"] is False
    assert payload["committed"] is False
    assert match_calls["count"] > 0


def test_chatlas_update_can_disable_transcript_cache(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from agentos.chatlas import core as chatlas_core

    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name="transcript-deep-pass-thread",
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    original_render = chatlas_core._render_transcript
    render_calls = {"count": 0}

    def counting_render(*args, **kwargs):
        render_calls["count"] += 1
        return original_render(*args, **kwargs)

    monkeypatch.setattr(chatlas_core, "_render_transcript", counting_render)

    assert main(_chatlas_update_argv("--provider", "codex", "--transcript-cache=false")) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["scan_cache_enabled"] is True
    assert payload["normalized_cache_enabled"] is True
    assert payload["transcript_cache_enabled"] is False
    assert payload["changes_detected"] is False
    assert payload["committed"] is False
    assert render_calls["count"] > 0


def test_chatlas_update_can_disable_normalized_cache(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from agentos.chatlas import core as chatlas_core

    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name="normalized-deep-pass-thread",
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    original_normalized_record = chatlas_core._normalized_session_record
    normalized_record_calls = {"count": 0}

    def counting_normalized_record(*args, **kwargs):
        normalized_record_calls["count"] += 1
        return original_normalized_record(*args, **kwargs)

    monkeypatch.setattr(chatlas_core, "_normalized_session_record", counting_normalized_record)

    assert main(_chatlas_update_argv("--provider", "codex", "--normalized-cache=false")) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["scan_cache_enabled"] is True
    assert payload["normalized_cache_enabled"] is False
    assert payload["transcript_cache_enabled"] is True
    assert payload["changes_detected"] is False
    assert payload["committed"] is False
    assert normalized_record_calls["count"] > 0


def test_chatlas_update_disable_cache_overrides_all_individual_cache_flags(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from agentos.chatlas import core as chatlas_core
    from agentos.chatlas import raw as chatlas_raw

    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name="master-disable-cache-thread",
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    original_match = chatlas_raw._chatlas_archive_files_match
    original_normalized_record = chatlas_core._normalized_session_record
    original_render = chatlas_core._render_transcript
    calls = {
        "match": 0,
        "normalized_record": 0,
        "render": 0,
    }

    def counting_match(*args, **kwargs):
        calls["match"] += 1
        return original_match(*args, **kwargs)

    def counting_normalized_record(*args, **kwargs):
        calls["normalized_record"] += 1
        return original_normalized_record(*args, **kwargs)

    def counting_render(*args, **kwargs):
        calls["render"] += 1
        return original_render(*args, **kwargs)

    monkeypatch.setattr(chatlas_raw, "_chatlas_archive_files_match", counting_match)
    monkeypatch.setattr(chatlas_core, "_normalized_session_record", counting_normalized_record)
    monkeypatch.setattr(chatlas_core, "_render_transcript", counting_render)

    assert main(
        _chatlas_update_argv(
            "--provider",
            "codex",
            "--disable-cache",
            "--scan-cache=true",
            "--normalized-cache=true",
            "--transcript-cache=true",
        )
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["scan_cache_enabled"] is False
    assert payload["normalized_cache_enabled"] is False
    assert payload["transcript_cache_enabled"] is False
    assert payload["changes_detected"] is False
    assert payload["committed"] is False
    assert calls["match"] > 0
    assert calls["normalized_record"] > 0
    assert calls["render"] > 0


def test_chatlas_stats_migrates_legacy_default_chatlas_root(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    legacy_root = _legacy_chatlas_root(agentos_home)
    new_root = _default_chatlas_root(home)
    _write(
        legacy_root / "normalized" / "sessions.jsonl",
        json.dumps(
            {
                "class": "agentos.chatlas.session",
                "schema_version": 1,
                "provider": "codex",
                "session_id": "legacy-session",
                "extractable": False,
            }
        )
        + "\n",
    )

    assert main(["chatlas", "stats", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["chatlas_root"] == str(new_root)
    assert payload["stats"]["session_count"] == 1
    assert (new_root / "normalized" / "sessions.jsonl").is_file()
    assert not legacy_root.exists()


def test_chatlas_update_preserves_archived_sessions_when_source_home_disappears(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = (
        home
        / ".codex"
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    )
    _write_codex_rollout(rollout_path, session_id=session_id)
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name="archived-thread",
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    shutil.rmtree(home / ".codex")

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    payload = json.loads(capsys.readouterr().out)

    archived_rollout = _chatlas_home_root(home, home / ".codex") / rollout_path.relative_to(home / ".codex")

    assert payload["changes_detected"] is False
    assert payload["committed"] is False
    assert payload["synced_instance_count"] == 0
    assert payload["skipped_instance_count"] == 1
    assert payload["normalized_session_count"] == 1
    assert archived_rollout.is_file()


def test_chatlas_update_skips_transient_missing_source_files(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from agentos.chatlas import raw as chatlas_raw

    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name="transient-thread",
    )
    _write(home / ".codex" / "notes.md", "# notes\n")

    original_copy2 = chatlas_raw.shutil.copy2

    def flaky_copy2(source: Path | str, destination: Path | str, *args, **kwargs):
        source_path = Path(source)
        if source_path.name == "notes.md":
            source_path.unlink()
        return original_copy2(source, destination, *args, **kwargs)

    monkeypatch.setattr(chatlas_raw.shutil, "copy2", flaky_copy2)

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    payload = json.loads(capsys.readouterr().out)

    home_status = payload["instances"][0]["homes_status"][0]
    assert payload["normalized_session_count"] == 1
    assert home_status["skipped_file_count"] == 1
    assert home_status["skipped_file_examples"] == ["notes.md"]


def test_chatlas_update_emits_progress_to_stderr(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )

    assert main(_chatlas_update_argv("--provider", "codex", output_mode=None)) == 0
    captured = capsys.readouterr()

    assert captured.out == ""
    assert "[chatlas] update start:" in captured.err
    assert "[chatlas] codex/codex-main: archive start" in captured.err
    assert "codex/codex-main:home: done (scanned=" in captured.err
    assert "[chatlas] codex/codex-main: archive done (synced=True, elapsed=" in captured.err
    assert "[chatlas] archive provider codex:" in captured.err
    assert "[chatlas] archive totals:" in captured.err
    assert "[chatlas] normalized sessions: 1 (elapsed=" in captured.err
    assert "[chatlas] derived transcripts: 1 (elapsed=" in captured.err
    assert "[chatlas] derived summaries: brief=1 detailed=1 (elapsed=" in captured.err


def test_chatlas_update_can_disable_progress_output(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )

    assert main(
        _chatlas_update_argv(
            "--provider",
            "codex",
            verbose_mode="quiet",
        )
    ) == 0
    captured = capsys.readouterr()

    payload = json.loads(captured.out)
    assert payload["command"] == "chatlas update"
    assert captured.err == ""


def test_chatlas_update_uses_configured_extra_codex_instance(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    extra_codex_home = home / ".codex-jp"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    default_session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    extra_session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd6"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{default_session_id}.jsonl",
        session_id=default_session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=default_session_id,
        thread_name="default-thread",
    )
    _write_codex_rollout(
        extra_codex_home / "sessions" / "2026" / "03" / "26" / f"rollout-2026-03-26T01-05-38-{extra_session_id}.jsonl",
        session_id=extra_session_id,
    )
    _write_codex_session_index(
        extra_codex_home / "session_index.jsonl",
        session_id=extra_session_id,
        thread_name="jp-thread",
    )
    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "jp",
                "home": str(extra_codex_home),
            }
        ],
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    payload = json.loads(capsys.readouterr().out)

    instance_names = [instance["instance"] for instance in payload["instances"]]

    assert payload["instance_count"] == 2
    assert payload["synced_instance_count"] == 2
    assert instance_names == ["codex-main", "jp"]
    assert (
        _chatlas_home_root(home, home / ".codex")
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-2026-03-25T01-05-38-{default_session_id}.jsonl"
    ).exists()
    assert (
        _chatlas_home_root(home, extra_codex_home)
        / "sessions"
        / "2026"
        / "03"
        / "26"
        / f"rollout-2026-03-26T01-05-38-{extra_session_id}.jsonl"
    ).exists()
    assert payload["normalized_session_count"] == 2


def test_chatlas_update_uses_shared_claude_code_home_slots(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    claude_cli_home = home / ".claude"
    claude_desktop_home = home / "Library" / "Application Support" / "Claude"
    (claude_cli_home / "projects").mkdir(parents=True, exist_ok=True)
    (claude_desktop_home / "claude-code-sessions").mkdir(parents=True, exist_ok=True)
    (claude_desktop_home / "Cache").mkdir(parents=True, exist_ok=True)
    (claude_desktop_home / "vm_bundles" / "claudevm.bundle").mkdir(parents=True, exist_ok=True)
    _write(claude_cli_home / "README.md", "cli root\n")
    _write(claude_desktop_home / "desktop-state.json", "{}\n")
    _write(claude_desktop_home / "Cache" / "cache.bin", "cache\n")
    _write(claude_desktop_home / "vm_bundles" / "claudevm.bundle" / "rootfs.img", "vm\n")

    assert main(_chatlas_update_argv("--provider", "claude-code")) == 0
    payload = json.loads(capsys.readouterr().out)

    destination_cli_root = _chatlas_home_root(home, claude_cli_home)
    destination_desktop_root = _chatlas_home_root(home, claude_desktop_home)
    instance = payload["instances"][0]

    assert payload["instance_count"] == 1
    assert payload["synced_instance_count"] == 1
    assert payload["normalized_session_count"] == 0
    assert instance["instance"] == "claude-main"
    assert instance["destination_root"] is None
    assert instance["destination_roots"] == {
        "cli": str(destination_cli_root),
        "desktop": str(destination_desktop_root),
    }
    assert instance["homes"] == {
        "cli": str(claude_cli_home),
        "desktop": str(claude_desktop_home),
    }
    assert (destination_cli_root / "README.md").is_file()
    assert (destination_desktop_root / "desktop-state.json").is_file()
    assert not (destination_desktop_root / "Cache").exists()
    assert not (destination_desktop_root / "vm_bundles").exists()


def test_chatlas_stats_reports_normalized_counts(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name="stats-thread",
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "stats"]) == 0
    rendered = capsys.readouterr().out

    assert "# Chatlas Stats" in rendered
    assert "- Providers: 1" in rendered
    assert "- Sessions: 1" in rendered
    assert "## codex" in rendered
    assert "- Derived transcripts: 1" in rendered

    assert main(["chatlas", "stats", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "chatlas stats"
    assert payload["stats"]["session_count"] == 1
    assert payload["stats"]["provider_count"] == 1
    assert payload["stats"]["derived_transcript_session_count"] == 1
    assert payload["stats"]["derived_summary_count"] == 1
    assert payload["stats"]["derived_summary_counts"] == {"brief": 1, "detailed": 1}
    assert payload["stats"]["by_provider"][0]["provider"] == "codex"
    assert payload["stats"]["last_update_recorded_at"] is not None
    assert payload["stats"]["last_update_manifest_path"] is not None


def test_chatlas_query_matches_normalized_thread_name(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    thread_name = "query-thread"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(
        [
            "chatlas",
            "query",
            thread_name,
            "--include-match",
            "--include-summary",
            "--summary-level",
            "brief",
            "--summary-level",
            "detailed",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "chatlas query"
    assert payload["session_count"] == 1
    session = payload["sessions"][0]
    assert session["provider"] == "codex"
    assert session["instance"] == "codex-main"
    assert session["session_id"] == session_id
    assert session["display_name"] == thread_name
    assert session["native"] == {"thread_name": thread_name}
    assert session["match"]["fields"] == [{"field": "thread_name", "value": thread_name}]
    assert session["summary"]["instance"] == "codex-main"
    assert session["summary"]["turn_count"] == 0
    assert session["summary_levels"]["brief"]["instance"] == "codex-main"
    assert session["summary_levels"]["brief"]["level"] == "brief"
    assert session["summary_levels"]["detailed"]["level"] == "detailed"


def test_chatlas_query_can_include_provider_stats_for_exact_session_queries(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    thread_name = "provider-stats-thread"
    _write_codex_dialog_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "query", thread_name, "--include-match", "--include-provider-stats"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["session_count"] == 1
    assert "provider_stats" in payload["expansions"]
    session = payload["sessions"][0]
    assert session["match"]["fields"] == [{"field": "thread_name", "value": thread_name}]
    assert session["provider_stats"]["has_rollout_artifact"] is True
    assert session["provider_stats"]["dialog_turn_count"] == 2


def test_chatlas_query_supports_instance_matching_filtering_and_compact_output(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    extra_codex_home = home / ".codex-jp"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    default_session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    extra_session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd6"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{default_session_id}.jsonl",
        session_id=default_session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=default_session_id,
        thread_name="default-thread",
    )
    _write_codex_rollout(
        extra_codex_home / "sessions" / "2026" / "03" / "26" / f"rollout-2026-03-26T01-05-38-{extra_session_id}.jsonl",
        session_id=extra_session_id,
    )
    _write_codex_session_index(
        extra_codex_home / "session_index.jsonl",
        session_id=extra_session_id,
        thread_name="jp-thread",
    )
    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "jp",
                "home": str(extra_codex_home),
            }
        ],
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "query", "jp", "--include-match", "--compact"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["session_count"] == 1
    assert payload["sessions"][0]["instance"] == "jp"
    assert payload["sessions"][0]["match"]["fields"] == [{"field": "instance", "value": "jp"}]
    assert set(payload["sessions"][0]) == {
        "provider",
        "instance",
        "session_id",
        "display_name",
        "updated_at",
        "match",
    }

    assert main(
        [
            "chatlas",
            "query",
            "--provider",
            "codex",
            "--instance",
            "jp",
            "--compact",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["selection"]["filters"]["instances"] == ["jp"]
    assert payload["selection"]["filters"]["compact"] is True
    assert payload["session_count"] == 1
    session = payload["sessions"][0]
    assert session["provider"] == "codex"
    assert session["instance"] == "jp"
    assert session["session_id"] == extra_session_id
    assert set(session) == {"provider", "instance", "session_id", "display_name", "updated_at"}

    assert main(["chatlas", "query", "--provider", "codex", "--sort", "lexical", "--compact"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["session_count"] == 2
    assert [session["instance"] for session in payload["sessions"]] == ["codex-main", "jp"]
    for session in payload["sessions"]:
        assert "primary_backing_artifact" not in session
        assert "native" not in session
        assert set(session) == {"provider", "instance", "session_id", "display_name", "updated_at"}


def test_chatlas_query_matches_openclaw_logical_session_keys(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "9ce6dc88-dd77-4ea1-9c6b-2c4e9fd5d401"
    session_key = "agent:main:telegram:direct:734641842"
    _write_openclaw_session(
        home / ".openclaw" / "agents" / "main" / "sessions",
        session_id=session_id,
        session_key=session_key,
    )

    assert main(_chatlas_update_argv("--provider", "openclaw")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(
        [
            "chatlas",
            "query",
            session_key,
            "--include-match",
            "--include-provider-stats",
            "--include-artifacts",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["session_count"] == 1
    session = payload["sessions"][0]
    assert session["provider"] == "openclaw"
    assert session["session_id"] == session_id
    assert session["native"] == {
        "session_keys": [session_key],
        "agent_id": "main",
    }
    assert session["match"]["fields"] == [{"field": "session_key", "value": session_key}]
    assert session["provider_stats"]["session_key_count"] == 1
    assert session["provider_stats"]["dialog_turn_count"] == 2


def test_chatlas_query_supports_user_contain_transcript_filter(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_dialog_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
        user_text="searchable user text",
        assistant_text="other assistant text",
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name="content-query-thread",
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(
        [
            "chatlas",
            "query",
            "--user-contain",
            "searchable user",
            "--include-summary",
            "--summary-level",
            "detailed",
            "--include-transcript-filter-match",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["session_count"] == 1
    assert payload["selection"]["query"] is None
    assert payload["selection"]["filters"]["user_contain"] == "searchable user"
    assert payload["sessions"][0]["transcript_filter_match"] == {"user_contain": "searchable user"}
    assert payload["sessions"][0]["summary"]["first_user_text"] == "searchable user text"
    assert payload["sessions"][0]["summary_levels"]["detailed"]["user_turn_previews"] == ["searchable user text"]


def test_chatlas_query_supports_text_contain_filter(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_dialog_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
        user_text="neutral user text",
        assistant_text="assistant searchable phrase",
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name="text-filter-thread",
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(
        [
            "chatlas",
            "query",
            "--text-contain",
            "searchable phrase",
            "--include-summary",
            "--include-transcript-filter-match",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["session_count"] == 1
    assert payload["sessions"][0]["transcript_filter_match"] == {"text_contain": "searchable phrase"}
    assert payload["sessions"][0]["summary"]["last_assistant_text"] == "assistant searchable phrase"


def test_chatlas_export_returns_derived_markdown_transcript(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    thread_name = "export-thread"
    rollout_path = home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    _write_codex_dialog_rollout(
        rollout_path,
        session_id=session_id,
        user_text="markdown export user",
        assistant_text="markdown export assistant",
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "export", thread_name]) == 0
    output = capsys.readouterr().out

    assert "### USER [2026-03-08T01:08:59.093Z]" in output
    assert "markdown export user" in output
    assert "markdown export assistant" in output
    assert "<system-reminder>" not in output


def test_chatlas_export_supports_jsonl_transcript_output(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    _write_codex_dialog_rollout(
        rollout_path,
        session_id=session_id,
        user_text="jsonl export user",
        assistant_text="jsonl export assistant",
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name="jsonl-export-thread",
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "export", session_id, "--format", "jsonl"]) == 0
    payload_lines = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]

    assert [line["role"] for line in payload_lines] == ["user", "assistant"]
    assert payload_lines[0]["text"] == "jsonl export user"
    assert payload_lines[1]["text"] == "jsonl export assistant"


def test_chatlas_export_supports_detailed_summary_json_output(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(agentos_home / "config.json")

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    thread_name = "summary-export-thread"
    rollout_path = home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    _write_codex_dialog_rollout(
        rollout_path,
        session_id=session_id,
        user_text="summary export user",
        assistant_text="summary export assistant",
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(
        [
            "chatlas",
            "export",
            thread_name,
            "--kind",
            "summary",
            "--summary-level",
            "detailed",
            "--format",
            "json",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["level"] == "detailed"
    assert payload["first_user_text"] == "summary export user"
    assert payload["last_assistant_text"] == "summary export assistant"
    assert payload["turn_previews"] == [
        {"role": "user", "text_preview": "summary export user"},
        {"role": "assistant", "text_preview": "summary export assistant"},
    ]
