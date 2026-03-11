from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from agentos.chat import core
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


def _write_codex_rollout_with_records(path: Path, *, session_id: str, records: list[dict[str, object]]) -> None:
    base_records = [
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
    _write(path, "\n".join(json.dumps(record) for record in base_records + records) + "\n")
    _set_iso_mtime(path, base_records[0]["timestamp"])


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


def _write_claude_desktop_session(
    path: Path,
    *,
    session_id: str,
    title: str,
    created_at: str = "2026-03-08T12:05:12.017Z",
) -> None:
    _write(
        path,
        json.dumps(
            {
                "sessionId": session_id,
                "title": title,
                "createdAt": created_at,
                "lastActivityAt": created_at,
            }
        ),
    )
    _set_iso_mtime(path, created_at)


def _write_claude_project_session(path: Path, *, session_id: str) -> None:
    records = [
        {
            "sessionId": session_id,
            "version": "1.0.0",
            "timestamp": "2026-03-08T12:05:12.017Z",
            "message": {
                "role": "user",
                "content": "hello from claude user",
            },
        },
        {
            "sessionId": session_id,
            "version": "1.0.0",
            "timestamp": "2026-03-08T12:05:18.000Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "hello from claude assistant"}],
            },
        },
    ]
    _write(path, "\n".join(json.dumps(record) for record in records) + "\n")
    _set_iso_mtime(path, records[-1]["timestamp"])


def _write_copilot_session_events(session_root: Path, *, session_id: str) -> Path:
    events_path = session_root / "events.jsonl"
    records = [
        {
            "type": "session.start",
            "timestamp": "2026-03-08T12:00:00.000Z",
            "data": {
                "sessionId": session_id,
                "producer": "copilot-agent",
            },
        },
        {
            "type": "user.message",
            "timestamp": "2026-03-08T12:00:05.000Z",
            "data": {
                "content": "hello from copilot user",
            },
        },
        {
            "type": "assistant.message",
            "timestamp": "2026-03-08T12:00:10.000Z",
            "data": {
                "content": "hello from copilot assistant",
            },
        },
        {
            "type": "tool.execution_start",
            "timestamp": "2026-03-08T12:00:12.000Z",
            "data": {
                "toolName": "terminal",
            },
        },
        {
            "type": "skill.invoked",
            "timestamp": "2026-03-08T12:00:15.000Z",
            "data": {
                "skillName": "design-discussion",
            },
        },
    ]
    _write(events_path, "\n".join(json.dumps(record) for record in records) + "\n")
    _set_iso_mtime(events_path, records[-1]["timestamp"])
    return events_path


def _write_gemini_session(
    path: Path,
    *,
    session_id: str,
    last_updated: str,
    start_time: str | None = None,
    messages: list[dict[str, object]] | None = None,
) -> None:
    payload = {
        "sessionId": session_id,
        "lastUpdated": last_updated,
        "startTime": start_time or last_updated,
        "messages": messages or [],
    }
    _write(path, json.dumps(payload))
    _set_iso_mtime(path, last_updated)


def _write_openclaw_session(
    sessions_dir: Path,
    *,
    session_id: str,
    agent_key: str = "agent:main:main",
    updated_at: int = 1772995738498,
    extra_records: list[dict[str, object]] | None = None,
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
    ]
    if extra_records:
        records.extend(extra_records)

    transcript_path = sessions_dir / f"{session_id}.jsonl"
    _write(transcript_path, "\n".join(json.dumps(record) for record in records) + "\n")
    _set_iso_mtime(transcript_path, str(records[-1]["timestamp"]))
    _write(
        sessions_dir / "sessions.json",
        json.dumps(
            {
                agent_key: {
                    "sessionId": session_id,
                    "updatedAt": updated_at,
                    "sessionFile": str(transcript_path.resolve()),
                }
            }
        ),
    )
    return transcript_path


def _write_opencode_session_db(db_path: Path, *, session_id: str) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("CREATE TABLE session (id TEXT PRIMARY KEY, time_updated INTEGER)")
        connection.execute(
            "CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT)"
        )
        connection.execute(
            "CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, time_created INTEGER, data TEXT)"
        )
        connection.execute(
            "INSERT INTO session (id, time_updated) VALUES (?, ?)",
            (session_id, 1772971740000),
        )
        connection.execute(
            "INSERT INTO message (id, session_id, time_created, data) VALUES (?, ?, ?, ?)",
            (
                "msg-user",
                session_id,
                1772971738498,
                json.dumps({"role": "user"}),
            ),
        )
        connection.execute(
            "INSERT INTO message (id, session_id, time_created, data) VALUES (?, ?, ?, ?)",
            (
                "msg-assistant",
                session_id,
                1772971740000,
                json.dumps({"role": "assistant"}),
            ),
        )
        connection.execute(
            "INSERT INTO part (id, message_id, time_created, data) VALUES (?, ?, ?, ?)",
            (
                "part-user",
                "msg-user",
                1772971738498,
                json.dumps({"type": "text", "text": "hello from opencode user"}),
            ),
        )
        connection.execute(
            "INSERT INTO part (id, message_id, time_created, data) VALUES (?, ?, ?, ?)",
            (
                "part-assistant",
                "msg-assistant",
                1772971740000,
                json.dumps({"type": "text", "text": "hello from opencode assistant"}),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _write_global_config(path: Path, *, provider_instances: list[dict[str, object]]) -> None:
    _write(
        path,
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "chat": {
                    "provider_instances": provider_instances,
                },
            }
        ),
    )


def _expected_session_summary(
    *,
    provider: str,
    session_id: str,
    display_name: str | None,
    display_name_field: str | None,
    updated_at: str | None,
    extractable: bool,
    primary_artifact_path: str | None,
    canonical_finding_count: int,
    title: str | None = None,
    thread_name: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "provider": provider,
        "session_id": session_id,
        "display_name": display_name,
        "display_name_field": display_name_field,
        "updated_at": updated_at,
        "extractable": extractable,
        "primary_artifact_path": primary_artifact_path,
        "canonical_finding_count": canonical_finding_count,
    }
    if title is not None:
        payload["title"] = title
    if thread_name is not None:
        payload["thread_name"] = thread_name
    return payload


def test_chat_session_list_returns_provider_grouped_session_ids_only(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    claude_session_id = "8948fa51-ae3d-4a28-bf5c-d9d8d8069a6b"
    claude_title = "Claude Session Title"
    codex_session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    codex_thread_name = "tape-uri-discovery-refactor"
    copilot_session_id = "663f2740-5d31-4098-af41-66b3389adb24"
    gemini_session_id = "aba05f70-c886-4d1b-9b34-b95402476b94"
    opencode_session_id = "ses_3386643b2ffegZgI4IgNfmL9n3"
    openclaw_session_id = "061729c9-f0c0-4d62-a3fb-1d21553fc0e4"

    claude_project_path = home / ".claude" / "projects" / "workspace" / f"{claude_session_id}.jsonl"
    _write(
        claude_project_path,
        json.dumps(
            {
                "sessionId": claude_session_id,
                "timestamp": "2026-03-08T12:05:12.017Z",
            }
        )
        + "\n",
    )
    _set_iso_mtime(claude_project_path, "2026-03-08T12:05:12.017Z")
    _write_claude_desktop_session(
        home
        / "Library"
        / "Application Support"
        / "Claude"
        / "claude-code-sessions"
        / "workspace"
        / f"{claude_session_id}.json",
        session_id=claude_session_id,
        title=claude_title,
    )
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "08" / f"rollout-2026-03-08T01-05-38-{codex_session_id}.jsonl",
        session_id=codex_session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=codex_session_id,
        thread_name=codex_thread_name,
    )
    _write(
        home / ".copilot" / "session-state" / copilot_session_id / "events.jsonl",
        '{"event":"started"}\n',
    )
    _write_gemini_session(
        home / ".gemini" / "tmp" / "workspace" / "chats" / "session-2026-03-07T11-47-aba05f70.json",
        session_id=gemini_session_id,
        last_updated="2026-03-07T11:47:42.513Z",
    )
    _write(
        home / ".local" / "share" / "opencode" / "storage" / "session_diff" / f"{opencode_session_id}.json",
        '{"diff":"value"}\n',
    )
    _write_openclaw_session(
        home / ".openclaw" / "agents" / "main" / "sessions",
        session_id=openclaw_session_id,
    )

    db_path = home / ".local" / "share" / "opencode" / "opencode.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("CREATE TABLE session (id TEXT PRIMARY KEY, time_updated INTEGER)")
        connection.execute(
            "INSERT INTO session (id, time_updated) VALUES (?, ?)",
            (opencode_session_id, 1772875306929),
        )
        connection.commit()
    finally:
        connection.close()

    assert main(["chat", "session", "list"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "ok"
    assert payload["command"] == "chat session list"
    assert payload["sort"] == "lexical"
    assert payload["provider_count"] == 6
    assert payload["session_count"] == 6

    providers = {provider["provider"]: provider for provider in payload["providers"]}
    assert providers["claude-code"]["session_ids"] == [claude_session_id]
    assert providers["claude-code"]["sessions"] == [
        _expected_session_summary(
            provider="claude-code",
            session_id=claude_session_id,
            display_name=claude_title,
            display_name_field="title",
            updated_at="2026-03-08T12:05:12.017Z",
            extractable=True,
            primary_artifact_path=str(
                claude_project_path.resolve()
            ),
            canonical_finding_count=2,
            title=claude_title,
        )
    ]
    assert providers["codex"]["session_ids"] == [codex_session_id]
    assert providers["codex"]["sessions"] == [
        _expected_session_summary(
            provider="codex",
            session_id=codex_session_id,
            display_name=codex_thread_name,
            display_name_field="thread_name",
            updated_at="2026-03-10T12:13:33.263Z",
            extractable=True,
            primary_artifact_path=str(
                (
                    home
                    / ".codex"
                    / "sessions"
                    / "2026"
                    / "03"
                    / "08"
                    / f"rollout-2026-03-08T01-05-38-{codex_session_id}.jsonl"
                ).resolve()
            ),
            canonical_finding_count=1,
            thread_name=codex_thread_name,
        )
    ]
    assert providers["copilot-cli"]["session_ids"] == [copilot_session_id]
    assert providers["gemini-cli"]["session_ids"] == [gemini_session_id]
    assert providers["opencode"]["session_ids"] == [opencode_session_id]
    assert providers["openclaw"]["session_ids"] == [openclaw_session_id]


def test_chat_session_list_includes_configured_extra_codex_home(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "agentos-home"))

    default_session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    extra_session_id = "119ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    extra_codex_home = tmp_path / "codex-alt"

    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "08" / f"rollout-2026-03-08T01-05-38-{default_session_id}.jsonl",
        session_id=default_session_id,
    )
    _write_codex_rollout(
        extra_codex_home
        / "sessions"
        / "2026"
        / "03"
        / "09"
        / f"rollout-2026-03-09T01-05-38-{extra_session_id}.jsonl",
        session_id=extra_session_id,
    )
    _write_global_config(
        tmp_path / "agentos-home" / "config.json",
        provider_instances=[{"provider": "codex", "home": str(extra_codex_home)}],
    )

    assert main(["chat", "session", "list", "--provider", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)

    codex_provider = payload["providers"][0]
    assert payload["provider_count"] == 1
    assert codex_provider["provider"] == "codex"
    assert codex_provider["session_ids"] == [default_session_id, extra_session_id]
    assert str((extra_codex_home / "sessions").resolve()) in codex_provider["searched_targets"]


def test_chat_session_list_includes_configured_claude_code_homes(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "agentos-home"))

    session_id = "663f2740-5d31-4098-af41-66b3389adb24"
    extra_claude_home = tmp_path / "claude-alt"
    _write_claude_project_session(
        extra_claude_home / "projects" / "workspace" / f"{session_id}.jsonl",
        session_id=session_id,
    )
    _write_global_config(
        tmp_path / "agentos-home" / "config.json",
        provider_instances=[{"provider": "claude-code", "homes": {"cli": str(extra_claude_home)}}],
    )

    assert main(["chat", "session", "list", "--provider", "claude-code"]) == 0
    payload = json.loads(capsys.readouterr().out)

    claude_provider = payload["providers"][0]
    assert payload["provider_count"] == 1
    assert claude_provider["provider"] == "claude-code"
    assert claude_provider["session_ids"] == [session_id]
    assert str((extra_claude_home / "projects").resolve()) in claude_provider["searched_targets"]


def test_chat_session_list_rejects_single_home_for_multi_root_claude_code_provider(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "agentos-home"))

    _write_global_config(
        tmp_path / "agentos-home" / "config.json",
        provider_instances=[{"provider": "claude-code", "home": str(tmp_path / "claude-alt")}],
    )

    assert main(["chat", "session", "list"]) == 1
    error_output = capsys.readouterr().err
    assert "chat.provider_instances[0].home is only supported for providers with a single home root" in error_output
    assert "chat.provider_instances[0].homes" in error_output
    assert "cli, desktop" in error_output


def test_chat_session_list_rejects_homes_for_single_root_provider(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "agentos-home"))

    _write_global_config(
        tmp_path / "agentos-home" / "config.json",
        provider_instances=[{"provider": "codex", "homes": {"home": str(tmp_path / "codex-alt")}}],
    )

    assert main(["chat", "session", "list"]) == 1
    error_output = capsys.readouterr().err
    assert "chat.provider_instances[0].homes is only supported for providers with multiple home roots" in error_output
    assert "chat.provider_instances[0].home" in error_output


def test_chat_session_list_full_output_keeps_zero_session_providers(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    assert main(["chat", "session", "list"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_count"] == 0
    assert payload["providers"] == []

    assert main(["chat", "session", "list", "--full-output"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["provider_count"] == 6
    assert len(payload["providers"]) == 6
    assert all(provider["session_count"] == 0 for provider in payload["providers"])


def test_chat_session_list_can_filter_providers_and_limit_results(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    claude_ids = [
        "8948fa51-ae3d-4a28-bf5c-d9d8d8069a6b",
        "9958fa51-ae3d-4a28-bf5c-d9d8d8069a6b",
    ]
    codex_ids = [
        "019ccafa-7835-7fc3-ac17-0e0a0f675fd5",
        "119ccafa-7835-7fc3-ac17-0e0a0f675fd5",
    ]
    codex_names = {
        codex_ids[0]: "tape-uri-discovery-refactor",
        codex_ids[1]: "tape-uri-discovery-followup",
    }

    for session_id in claude_ids:
        _write(
            home / ".claude" / "projects" / "workspace" / f"{session_id}.jsonl",
            json.dumps(
                {
                    "sessionId": session_id,
                    "timestamp": "2026-03-08T12:05:12.017Z",
                }
            )
            + "\n",
        )

    for session_id in codex_ids:
        _write_codex_rollout(
            home
            / ".codex"
            / "sessions"
            / "2026"
            / "03"
            / "08"
            / f"rollout-2026-03-08T01-05-38-{session_id}.jsonl",
            session_id=session_id,
        )
    _write(
        home / ".codex" / "session_index.jsonl",
        "\n".join(
            json.dumps(
                {
                    "id": session_id,
                    "thread_name": codex_names[session_id],
                    "updated_at": "2026-03-10T12:13:33.263726Z",
                }
            )
            for session_id in codex_ids
        )
        + "\n",
    )

    assert (
        main(
            [
                "chat",
                "session",
                "list",
                "--provider",
                "claude-code",
                "--provider",
                "codex",
                "--limit",
                "1",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["provider_count"] == 2
    assert payload["session_count"] == 2
    providers = {provider["provider"]: provider for provider in payload["providers"]}
    assert providers["claude-code"]["session_ids"] == [claude_ids[0]]
    assert providers["claude-code"]["session_count"] == 1
    assert providers["codex"]["session_ids"] == [codex_ids[0]]
    assert providers["codex"]["sessions"] == [
        _expected_session_summary(
            provider="codex",
            session_id=codex_ids[0],
            display_name=codex_names[codex_ids[0]],
            display_name_field="thread_name",
            updated_at="2026-03-10T12:13:33.263Z",
            extractable=True,
            primary_artifact_path=str(
                (
                    home
                    / ".codex"
                    / "sessions"
                    / "2026"
                    / "03"
                    / "08"
                    / f"rollout-2026-03-08T01-05-38-{codex_ids[0]}.jsonl"
                ).resolve()
            ),
            canonical_finding_count=1,
            thread_name=codex_names[codex_ids[0]],
        )
    ]
    assert providers["codex"]["session_count"] == 1


def test_chat_session_list_deduplicates_gemini_sessions_and_supports_sorting(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    first_session_id = "aba05f70-c886-4d1b-9b34-b95402476b94"
    second_session_id = "b653c0d2-d75a-494b-bcfa-9b0556a24a48"

    _write_gemini_session(
        home / ".gemini" / "tmp" / "workspace" / "chats" / "session-2026-01-12T01-54-aba05f70.json",
        session_id=first_session_id,
        last_updated="2026-01-12T01:54:42.513Z",
    )
    _write_gemini_session(
        home / ".gemini" / "tmp" / "workspace" / "chats" / "session-2026-01-28T16-02-b653c0d2.json",
        session_id=second_session_id,
        last_updated="2026-01-28T16:02:00.000Z",
    )
    _write_gemini_session(
        home / ".gemini" / "tmp" / "workspace" / "chats" / "session-2026-01-28T16-45-b653c0d2.json",
        session_id=second_session_id,
        last_updated="2026-01-28T16:45:00.000Z",
    )

    assert main(["chat", "session", "list"]) == 0
    payload = json.loads(capsys.readouterr().out)
    gemini_provider = next(provider for provider in payload["providers"] if provider["provider"] == "gemini-cli")
    assert gemini_provider["session_ids"] == [first_session_id, second_session_id]
    assert gemini_provider["session_count"] == 2

    assert main(["chat", "session", "list", "--sort", "newest"]) == 0
    payload = json.loads(capsys.readouterr().out)
    gemini_provider = next(provider for provider in payload["providers"] if provider["provider"] == "gemini-cli")
    assert gemini_provider["session_ids"] == [second_session_id, first_session_id]

    assert main(["chat", "session", "list", "--sort", "oldest"]) == 0
    payload = json.loads(capsys.readouterr().out)
    gemini_provider = next(provider for provider in payload["providers"] if provider["provider"] == "gemini-cli")
    assert gemini_provider["session_ids"] == [first_session_id, second_session_id]


def test_chat_session_list_rejects_non_positive_limit(capsys) -> None:
    assert main(["chat", "session", "list", "--limit", "0"]) == 1
    assert "session limit must be greater than 0" in capsys.readouterr().err


def test_chat_session_list_can_filter_extractable_sessions(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    extractable_id = "061729c9-f0c0-4d62-a3fb-1d21553fc0e4"
    non_extractable_id = "42e3cbf6-5ea7-42bd-a537-40fb04af7ce5"
    _write_openclaw_session(
        home / ".openclaw" / "agents" / "main" / "sessions",
        session_id=extractable_id,
    )
    _write(
        home / ".openclaw" / "agents" / "oba" / "sessions" / "sessions.json",
        json.dumps(
            {
                "agent:oba:notes": {
                    "sessionId": non_extractable_id,
                    "updatedAt": 1772996011170,
                    "sessionFile": None,
                }
            }
        ),
    )

    assert main(["chat", "session", "list", "--provider", "openclaw", "--extractable"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["extractable_only"] is True
    assert payload["session_count"] == 1
    provider = payload["providers"][0]
    assert provider["provider"] == "openclaw"
    assert provider["session_ids"] == [extractable_id]


def test_chat_session_list_can_filter_updated_since(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr("agentos.chat.commands.time.time", lambda: 1_741_694_400.0)  # 2025-03-11T12:00:00Z

    recent_session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    old_session_id = "119ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2025" / "03" / "10" / f"rollout-2025-03-10T01-05-38-{recent_session_id}.jsonl",
        session_id=recent_session_id,
    )
    _set_iso_mtime(
        home / ".codex" / "sessions" / "2025" / "03" / "10" / f"rollout-2025-03-10T01-05-38-{recent_session_id}.jsonl",
        "2025-03-10T01:05:38.000Z",
    )
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2025" / "03" / "01" / f"rollout-2025-03-01T01-05-38-{old_session_id}.jsonl",
        session_id=old_session_id,
    )
    _set_iso_mtime(
        home / ".codex" / "sessions" / "2025" / "03" / "01" / f"rollout-2025-03-01T01-05-38-{old_session_id}.jsonl",
        "2025-03-01T01:05:38.000Z",
    )
    _write(
        home / ".codex" / "session_index.jsonl",
        "\n".join(
            [
                json.dumps(
                    {
                        "id": recent_session_id,
                        "thread_name": "recent-thread",
                        "updated_at": "2025-03-10T12:13:33.263726Z",
                    }
                ),
                json.dumps(
                    {
                        "id": old_session_id,
                        "thread_name": "old-thread",
                        "updated_at": "2025-03-01T12:13:33.263726Z",
                    }
                ),
            ]
        )
        + "\n",
    )

    assert main(["chat", "session", "list", "--provider", "codex", "--updated-since", "3d"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["updated_after"] == "2025-03-08T12:00:00.000Z"
    assert payload["session_count"] == 1
    provider = payload["providers"][0]
    assert provider["provider"] == "codex"
    assert provider["session_ids"] == [recent_session_id]


def test_chat_session_stats_summarizes_provider_inventory(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    claude_session_id = "8948fa51-ae3d-4a28-bf5c-d9d8d8069a6b"
    claude_title = "Claude Session Title"
    codex_session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    codex_thread_name = "tape-uri-discovery-refactor"
    openclaw_extractable_id = "061729c9-f0c0-4d62-a3fb-1d21553fc0e4"
    openclaw_non_extractable_id = "42e3cbf6-5ea7-42bd-a537-40fb04af7ce5"

    claude_project_path = home / ".claude" / "projects" / "workspace" / f"{claude_session_id}.jsonl"
    _write(
        claude_project_path,
        json.dumps(
            {
                "sessionId": claude_session_id,
                "timestamp": "2026-03-08T12:05:12.017Z",
            }
        )
        + "\n",
    )
    _set_iso_mtime(claude_project_path, "2026-03-08T12:05:12.017Z")
    _write_claude_desktop_session(
        home
        / "Library"
        / "Application Support"
        / "Claude"
        / "claude-code-sessions"
        / "workspace"
        / f"{claude_session_id}.json",
        session_id=claude_session_id,
        title=claude_title,
        created_at="2026-03-07T12:05:12.017Z",
    )
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "08" / f"rollout-2026-03-08T01-05-38-{codex_session_id}.jsonl",
        session_id=codex_session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=codex_session_id,
        thread_name=codex_thread_name,
        updated_at="2026-03-08T01:08:59.089Z",
    )
    _write_openclaw_session(
        home / ".openclaw" / "agents" / "main" / "sessions",
        session_id=openclaw_extractable_id,
    )
    _write(
        home / ".openclaw" / "agents" / "oba" / "sessions" / "sessions.json",
        json.dumps(
            {
                "agent:oba:notes": {
                    "sessionId": openclaw_non_extractable_id,
                    "updatedAt": 1772996011170,
                    "sessionFile": None,
                }
            }
        ),
    )

    assert main(["chat", "session", "stats"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "ok"
    assert payload["command"] == "chat session stats"
    assert payload["provider_count"] == 3
    assert payload["session_count"] == 4
    assert payload["extractable_session_count"] == 3
    assert payload["non_extractable_session_count"] == 1

    providers = {provider["provider"]: provider for provider in payload["providers"]}
    assert providers["claude-code"]["session_count"] == 1
    assert providers["claude-code"]["session_examples"] == [
        _expected_session_summary(
            provider="claude-code",
            session_id=claude_session_id,
            display_name=claude_title,
            display_name_field="title",
            updated_at="2026-03-08T12:05:12.017Z",
            extractable=True,
                primary_artifact_path=str(
                claude_project_path.resolve()
            ),
            canonical_finding_count=2,
            title=claude_title,
        )
    ]
    assert providers["claude-code"]["oldest_session_name"] == claude_title
    assert providers["claude-code"]["latest_session_name"] == claude_title
    assert providers["codex"]["session_count"] == 1
    assert providers["codex"]["extractable_session_count"] == 1
    assert providers["codex"]["non_extractable_session_count"] == 0
    assert providers["codex"]["session_id_examples"] == [codex_session_id]
    assert providers["codex"]["session_examples"] == [
        _expected_session_summary(
            provider="codex",
            session_id=codex_session_id,
            display_name=codex_thread_name,
            display_name_field="thread_name",
            updated_at="2026-03-08T01:08:59.089Z",
            extractable=True,
            primary_artifact_path=str(
                (
                    home
                    / ".codex"
                    / "sessions"
                    / "2026"
                    / "03"
                    / "08"
                    / f"rollout-2026-03-08T01-05-38-{codex_session_id}.jsonl"
                ).resolve()
            ),
            canonical_finding_count=1,
            thread_name=codex_thread_name,
        )
    ]
    assert providers["codex"]["oldest_session_name"] == codex_thread_name
    assert providers["codex"]["latest_session_name"] == codex_thread_name

    assert providers["openclaw"]["session_count"] == 2
    assert providers["openclaw"]["extractable_session_count"] == 1
    assert providers["openclaw"]["non_extractable_session_count"] == 1
    assert providers["openclaw"]["session_id_examples"] == [
        openclaw_extractable_id,
        openclaw_non_extractable_id,
    ]
    assert providers["openclaw"]["canonical_finding_count"] == 2


def test_chat_session_stats_full_output_and_provider_filtering(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    assert main(["chat", "session", "stats"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_count"] == 0
    assert payload["providers"] == []

    assert main(["chat", "session", "stats", "--full-output"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_count"] == 6
    assert len(payload["providers"]) == 6
    assert all(provider["session_count"] == 0 for provider in payload["providers"])

    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "08" / "rollout-2026-03-08T01-05-38-019ccafa-7835-7fc3-ac17-0e0a0f675fd5.jsonl",
        session_id="019ccafa-7835-7fc3-ac17-0e0a0f675fd5",
    )
    assert main(["chat", "session", "stats", "--provider", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_count"] == 1
    assert payload["providers"][0]["provider"] == "codex"


def test_chat_session_stats_supports_markdown_output(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    claude_session_id = "8948fa51-ae3d-4a28-bf5c-d9d8d8069a6b"
    claude_title = "Claude Session Title"
    codex_session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    codex_thread_name = "tape-uri-discovery-refactor"
    _write_claude_desktop_session(
        home
        / "Library"
        / "Application Support"
        / "Claude"
        / "claude-code-sessions"
        / "workspace"
        / f"{claude_session_id}.json",
        session_id=claude_session_id,
        title=claude_title,
    )
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "08" / f"rollout-2026-03-08T01-05-38-{codex_session_id}.jsonl",
        session_id=codex_session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=codex_session_id,
        thread_name=codex_thread_name,
    )

    assert main(["chat", "session", "stats", "--output", "markdown"]) == 0
    output = capsys.readouterr().out

    assert "# Chat Session Stats" in output
    assert "## claude-code" in output
    assert "## codex" in output
    assert "- Sessions: 1" in output
    assert f"- Examples: {codex_session_id}" in output
    assert f"- Named examples: {claude_session_id} ({claude_title})" in output
    assert f"{codex_session_id} ({codex_thread_name})" in output


def test_chat_session_stats_supports_unique_codex_session_queries(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "019cd2fe-ff22-70f2-a131-2c00c0b21166"
    thread_name = "tape-uri-discovery-refactor"
    rollout_path = (
        home / ".codex" / "sessions" / "2026" / "03" / "10" / f"rollout-2026-03-10T12-13-33-{session_id}.jsonl"
    )
    _write_codex_rollout_with_records(
        rollout_path,
        session_id=session_id,
        records=[
            {
                "timestamp": "2026-03-08T01:09:00.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello from user"}],
                },
            },
            {
                "timestamp": "2026-03-08T01:09:10.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "hello from assistant"}],
                },
            },
            {
                "timestamp": "2026-03-08T01:09:20.000Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "arguments": "{\"cmd\":\"pwd\"}",
                    "call_id": "call_1",
                },
            },
            {
                "timestamp": "2026-03-08T01:09:30.000Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": "Chunk ID: 123\nProcess exited with code 0\nOutput:\n/work\n",
                },
            },
            {
                "timestamp": "2026-03-08T01:09:35.000Z",
                "type": "response_item",
                "payload": {
                    "type": "reasoning",
                    "summary": [],
                    "content": None,
                },
            },
            {
                "timestamp": "2026-03-08T01:09:40.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {},
                },
            },
        ],
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(["chat", "session", "stats", thread_name]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "ok"
    assert payload["command"] == "chat session stats"
    assert payload["query"] == thread_name
    assert payload["session"] == {
        "provider": "codex",
        "session_id": session_id,
        "display_name": thread_name,
        "display_name_field": "thread_name",
        "matched_field": "thread_name",
        "matched_value": thread_name,
        "updated_at": "2026-03-10T12:13:33.263Z",
        "extractable": True,
        "primary_artifact_path": str(rollout_path.resolve()),
        "canonical_finding_count": 1,
    }
    assert payload["provider_stats"] == {
        "rollout_artifact_count": 1,
        "session_index_count": 1,
        "has_rollout_artifact": True,
        "record_count": 7,
        "session_meta_count": 1,
        "response_item_count": 5,
        "event_message_count": 1,
        "message_count": 2,
        "user_message_count": 1,
        "assistant_message_count": 1,
        "developer_message_count": 0,
        "tool_call_count": 1,
        "tool_call_output_count": 1,
        "reasoning_item_count": 1,
        "dialog_turn_count": 2,
        "user_turn_count": 1,
        "assistant_turn_count": 1,
        "first_record_at": "2026-03-08T01:08:59.089Z",
        "last_record_at": "2026-03-08T01:09:40.000Z",
        "first_turn_at": "2026-03-08T01:09:00.000Z",
        "last_turn_at": "2026-03-08T01:09:10.000Z",
    }

    assert main(["chat", "session", "stats", thread_name, "--output", "markdown"]) == 0
    output = capsys.readouterr().out
    assert "# Chat Session Stats" in output
    assert f"- Query: {thread_name}" in output
    assert "- Provider: codex" in output
    assert f"- Session ID: {session_id}" in output
    assert f"- Name: {thread_name}" in output
    assert "- Tool calls: 1" in output
    assert "- Dialog turns: 2" in output


def test_chat_session_stats_rejects_ambiguous_session_queries(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    thread_name = "duplicate-thread-name"
    session_ids = [
        "019cd2fe-ff22-70f2-a131-2c00c0b21166",
        "019cd2fe-ff22-70f2-a131-2c00c0b21167",
    ]
    for index, session_id in enumerate(session_ids, start=10):
        _write_codex_rollout(
            home / ".codex" / "sessions" / "2026" / "03" / str(index) / f"rollout-2026-03-{index}T12-13-33-{session_id}.jsonl",
            session_id=session_id,
        )
        _write(
            home / ".codex" / "session_index.jsonl",
            "\n".join(
                json.dumps(
                    {
                        "id": current_id,
                        "thread_name": thread_name,
                        "updated_at": "2026-03-10T12:13:33.263726Z",
                    }
                )
                for current_id in session_ids[:index - 9]
            )
            + "\n",
        )

    assert main(["chat", "session", "stats", thread_name]) == 1
    stderr = capsys.readouterr().err
    assert "multiple sessions matched query duplicate-thread-name" in stderr


def test_chat_session_stats_supports_unique_claude_session_queries(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "8948fa51-ae3d-4a28-bf5c-d9d8d8069a6b"
    title = "Claude Session Title"
    project_path = home / ".claude" / "projects" / "workspace" / f"{session_id}.jsonl"
    desktop_path = (
        home
        / "Library"
        / "Application Support"
        / "Claude"
        / "claude-code-sessions"
        / "workspace"
        / f"{session_id}.json"
    )
    _write_claude_project_session(project_path, session_id=session_id)
    _write_claude_desktop_session(
        desktop_path,
        session_id=session_id,
        title=title,
    )
    _set_iso_mtime(desktop_path, "2026-03-08T12:05:12.017Z")

    assert main(["chat", "session", "stats", title]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["session"]["provider"] == "claude-code"
    assert payload["session"]["session_id"] == session_id
    assert payload["session"]["display_name"] == title
    assert payload["session"]["display_name_field"] == "title"
    assert payload["session"]["matched_field"] == "title"
    assert payload["session"]["matched_value"] == title
    assert payload["session"]["extractable"] is True
    assert payload["session"]["primary_artifact_path"] == str(project_path.resolve())
    assert payload["session"]["canonical_finding_count"] == 2
    assert payload["provider_stats"] == {
        "artifact_count": 2,
        "source_kind": "mixed",
        "has_extractable_artifact": True,
        "record_count": 2,
        "message_record_count": 2,
        "user_message_count": 1,
        "assistant_message_count": 1,
        "first_record_at": "2026-03-08T12:05:12.017Z",
        "last_record_at": "2026-03-08T12:05:18.000Z",
        "dialog_turn_count": 2,
        "user_turn_count": 1,
        "assistant_turn_count": 1,
        "first_turn_at": "2026-03-08T12:05:12.017Z",
        "last_turn_at": "2026-03-08T12:05:18.000Z",
    }

    assert main(["chat", "session", "stats", title, "--output", "markdown"]) == 0
    output = capsys.readouterr().out
    assert "# Chat Session Stats" in output
    assert "- Provider: claude-code" in output
    assert f"- Session ID: {session_id}" in output
    assert f"- Name: {title}" in output
    assert "- Artifacts: 2" in output
    assert "- Source kind: mixed" in output


def test_chat_session_stats_uses_clean_claude_dialog_as_count_source_of_truth(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "claude-noise-test"
    project_path = home / ".claude" / "projects" / "workspace" / f"{session_id}.jsonl"
    _write(
        project_path,
        "\n".join(
            [
                json.dumps(
                    {
                        "sessionId": session_id,
                        "version": "1.0.0",
                        "timestamp": "2026-03-08T12:05:00.000Z",
                        "isMeta": True,
                        "message": {
                            "role": "user",
                            "content": "Base directory for this skill: /tmp/project",
                        },
                    }
                ),
                json.dumps(
                    {
                        "sessionId": session_id,
                        "version": "1.0.0",
                        "timestamp": "2026-03-08T12:05:12.017Z",
                        "message": {
                            "role": "user",
                            "content": "real user message",
                        },
                    }
                ),
            ]
        )
        + "\n",
    )
    _set_iso_mtime(project_path, "2026-03-08T12:05:12.017Z")

    assert main(["chat", "session", "stats", session_id]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["provider_stats"] == {
        "artifact_count": 1,
        "source_kind": "project",
        "has_extractable_artifact": True,
        "record_count": 2,
        "message_record_count": 1,
        "user_message_count": 1,
        "assistant_message_count": 0,
        "first_record_at": "2026-03-08T12:05:12.017Z",
        "last_record_at": "2026-03-08T12:05:12.017Z",
        "dialog_turn_count": 1,
        "user_turn_count": 1,
        "assistant_turn_count": 0,
        "first_turn_at": "2026-03-08T12:05:12.017Z",
        "last_turn_at": "2026-03-08T12:05:12.017Z",
    }


def test_chat_session_stats_supports_unique_copilot_session_queries(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "663f2740-5d31-4098-af41-66b3389adb24"
    session_root = home / ".copilot" / "session-state" / session_id
    events_path = _write_copilot_session_events(session_root, session_id=session_id)

    assert main(["chat", "session", "stats", session_id]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["session"]["provider"] == "copilot-cli"
    assert payload["session"]["session_id"] == session_id
    assert payload["session"]["display_name"] is None
    assert payload["session"]["display_name_field"] is None
    assert payload["session"]["matched_field"] == "session_id"
    assert payload["session"]["matched_value"] == session_id
    assert payload["session"]["extractable"] is True
    assert payload["session"]["primary_artifact_path"] == str(events_path.resolve())
    assert payload["session"]["canonical_finding_count"] == 1
    assert payload["provider_stats"] == {
        "session_root_present": True,
        "session_file_present": False,
        "event_count": 5,
        "session_start_count": 1,
        "user_message_event_count": 1,
        "assistant_message_event_count": 1,
        "tool_event_count": 1,
        "skill_invoked_count": 1,
        "first_event_at": "2026-03-08T12:00:00.000Z",
        "last_event_at": "2026-03-08T12:00:15.000Z",
        "dialog_turn_count": 2,
        "user_turn_count": 1,
        "assistant_turn_count": 1,
        "first_turn_at": "2026-03-08T12:00:05.000Z",
        "last_turn_at": "2026-03-08T12:00:10.000Z",
    }


def test_chat_session_stats_returns_partial_payload_for_malformed_copilot_artifacts(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "bad-copilot"
    session_root = home / ".copilot" / "session-state" / session_id
    _write(session_root / "events.jsonl", '{"event":"started"}\n')

    assert main(["chat", "session", "stats", session_id]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["session"]["provider"] == "copilot-cli"
    assert payload["session"]["session_id"] == session_id
    assert payload["provider_stats"] == {
        "session_root_present": True,
        "session_file_present": False,
    }


def test_chat_session_stats_supports_unique_gemini_session_queries(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "aba05f70-c886-4d1b-9b34-b95402476b94"
    session_path = (
        home / ".gemini" / "tmp" / "workspace" / "chats" / "session-2026-03-07T11-47-aba05f70.json"
    )
    _write_gemini_session(
        session_path,
        session_id=session_id,
        start_time="2026-03-07T11:40:00.000Z",
        last_updated="2026-03-07T11:47:42.513Z",
        messages=[
            {
                "type": "user",
                "timestamp": "2026-03-07T11:40:00.000Z",
                "content": "hello from gemini user",
            },
            {
                "type": "gemini",
                "timestamp": "2026-03-07T11:40:10.000Z",
                "content": "hello from gemini assistant",
                "thoughts": [{"subject": "plan"}],
                "toolCalls": [{"name": "search"}],
            },
        ],
    )

    assert main(["chat", "session", "stats", session_id]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["session"]["provider"] == "gemini-cli"
    assert payload["session"]["session_id"] == session_id
    assert payload["session"]["display_name"] is None
    assert payload["session"]["display_name_field"] is None
    assert payload["session"]["matched_field"] == "session_id"
    assert payload["session"]["matched_value"] == session_id
    assert payload["session"]["extractable"] is True
    assert payload["session"]["primary_artifact_path"] == str(session_path.resolve())
    assert payload["session"]["canonical_finding_count"] == 1
    assert payload["provider_stats"] == {
        "artifact_count": 1,
        "message_count": 2,
        "user_message_count": 1,
        "assistant_message_count": 1,
        "thought_count": 1,
        "tool_call_count": 1,
        "start_time": "2026-03-07T11:40:00.000Z",
        "last_updated": "2026-03-07T11:47:42.513Z",
        "dialog_turn_count": 2,
        "user_turn_count": 1,
        "assistant_turn_count": 1,
        "first_turn_at": "2026-03-07T11:40:00.000Z",
        "last_turn_at": "2026-03-07T11:40:10.000Z",
    }


def test_chat_session_stats_returns_partial_payload_for_malformed_gemini_artifacts(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "bad-gemini"
    session_path = home / ".gemini" / "tmp" / "workspace" / "chats" / "session-2026-03-07T11-47-bad.json"
    _write(
        session_path,
        json.dumps(
            {
                "sessionId": session_id,
                "lastUpdated": "2026-03-07T11:47:42.513Z",
            }
        ),
    )
    _set_iso_mtime(session_path, "2026-03-07T11:47:42.513Z")

    assert main(["chat", "session", "stats", session_id]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["session"]["provider"] == "gemini-cli"
    assert payload["session"]["session_id"] == session_id
    assert payload["provider_stats"] == {
        "artifact_count": 1,
    }


def test_chat_session_stats_supports_unique_openclaw_session_queries(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "061729c9-f0c0-4d62-a3fb-1d21553fc0e4"
    session_key = "agent:main:telegram:direct:734641842"
    sessions_dir = home / ".openclaw" / "agents" / "main" / "sessions"
    transcript_path = _write_openclaw_session(
        sessions_dir,
        session_id=session_id,
        agent_key=session_key,
        extra_records=[
            {
                "type": "message",
                "id": "msg-assistant-1",
                "timestamp": "2026-03-08T12:05:18.000Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "[[reply_to_current]] hello from assistant"}],
                },
            }
        ],
    )
    _set_iso_mtime(sessions_dir / "sessions.json", "2026-03-08T12:05:18.000Z")

    assert main(["chat", "session", "stats", session_key]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["session"]["provider"] == "openclaw"
    assert payload["session"]["session_id"] == session_id
    assert payload["session"]["display_name"] is None
    assert payload["session"]["display_name_field"] is None
    assert payload["session"]["matched_field"] == "session_key"
    assert payload["session"]["matched_value"] == session_key
    assert payload["session"]["extractable"] is True
    assert payload["session"]["primary_artifact_path"] == str(transcript_path.resolve())
    assert payload["session"]["canonical_finding_count"] == 1
    assert payload["provider_stats"] == {
        "has_transcript": True,
        "has_sessions_index": True,
        "session_key_count": 1,
        "agent_id": "main",
        "record_count": 3,
        "session_record_count": 1,
        "message_record_count": 2,
        "user_message_count": 1,
        "assistant_message_count": 1,
        "first_record_at": "2026-03-08T12:05:10.000Z",
        "last_record_at": "2026-03-08T12:05:18.000Z",
        "dialog_turn_count": 2,
        "user_turn_count": 1,
        "assistant_turn_count": 1,
        "first_turn_at": "2026-03-08T12:05:12.017Z",
        "last_turn_at": "2026-03-08T12:05:18.000Z",
    }


def test_chat_session_stats_returns_partial_payload_for_malformed_openclaw_artifacts(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "bad-openclaw"
    transcript_path = home / ".openclaw" / "agents" / "main" / "sessions" / f"{session_id}.jsonl"
    _write(transcript_path, '{"type":"message","message":{"role":"user","content":[]}}\n')

    assert main(["chat", "session", "stats", session_id]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["session"]["provider"] == "openclaw"
    assert payload["session"]["session_id"] == session_id
    assert payload["provider_stats"] == {
        "has_transcript": True,
        "has_sessions_index": False,
        "session_key_count": 0,
        "agent_id": "main",
    }


def test_chat_session_stats_supports_unique_opencode_session_queries(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "ses_3386643b2ffegZgI4IgNfmL9n3"
    diff_path = home / ".local" / "share" / "opencode" / "storage" / "session_diff" / f"{session_id}.json"
    db_path = home / ".local" / "share" / "opencode" / "opencode.db"
    _write(diff_path, "[]\n")
    _set_iso_mtime(diff_path, "2026-03-08T12:08:58.498Z")
    _write_opencode_session_db(db_path, session_id=session_id)
    _set_iso_mtime(db_path, "2026-03-08T12:09:00.000Z")

    assert main(["chat", "session", "stats", session_id]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["session"]["provider"] == "opencode"
    assert payload["session"]["session_id"] == session_id
    assert payload["session"]["display_name"] is None
    assert payload["session"]["display_name_field"] is None
    assert payload["session"]["matched_field"] == "session_id"
    assert payload["session"]["matched_value"] == session_id
    assert payload["session"]["extractable"] is True
    assert payload["session"]["primary_artifact_path"] == str(diff_path.resolve())
    assert payload["session"]["canonical_finding_count"] == 2
    assert payload["provider_stats"] == {
        "has_diff_artifact": True,
        "has_sqlite_db": True,
        "message_count": 2,
        "user_message_count": 1,
        "assistant_message_count": 1,
        "part_count": 2,
        "text_part_count": 2,
        "non_text_part_count": 0,
        "first_message_at": "2026-03-08T12:08:58.498Z",
        "last_message_at": "2026-03-08T12:09:00.000Z",
        "dialog_turn_count": 2,
        "user_turn_count": 1,
        "assistant_turn_count": 1,
        "first_turn_at": "2026-03-08T12:08:58.498Z",
        "last_turn_at": "2026-03-08T12:09:00.000Z",
    }


def test_chat_session_stats_returns_partial_payload_for_malformed_opencode_artifacts(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "ses_bad_opencode"
    diff_path = home / ".local" / "share" / "opencode" / "storage" / "session_diff" / f"{session_id}.json"
    db_path = home / ".local" / "share" / "opencode" / "opencode.db"
    _write(diff_path, "[]\n")
    _write(db_path, "not a sqlite database\n")

    assert main(["chat", "session", "stats", session_id]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["session"]["provider"] == "opencode"
    assert payload["session"]["session_id"] == session_id
    assert payload["provider_stats"] == {
        "has_diff_artifact": True,
        "has_sqlite_db": True,
    }


def test_chat_session_find_supports_full_gemini_session_ids(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "aba05f70-c886-4d1b-9b34-b95402476b94"
    session_path = (
        home
        / ".gemini"
        / "tmp"
        / "workspace"
        / "chats"
        / "session-2026-01-12T01-54-aba05f70.json"
    )
    _write_gemini_session(
        session_path,
        session_id=session_id,
        last_updated="2026-01-12T01:54:42.513Z",
    )

    assert main(["chat", "session", "find", session_id]) == 0
    payload = json.loads(capsys.readouterr().out)

    gemini_findings = [finding for finding in payload["findings"] if finding["provider"] == "gemini-cli"]
    assert payload["provider_count"] == 1
    assert [finding["path"] for finding in gemini_findings] == [str(session_path.resolve())]


def test_chat_session_find_uses_configured_extra_codex_home(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "agentos-home"))

    session_id = "119ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    extra_codex_home = tmp_path / "codex-alt"
    rollout_path = (
        extra_codex_home
        / "sessions"
        / "2026"
        / "03"
        / "09"
        / f"rollout-2026-03-09T01-05-38-{session_id}.jsonl"
    )
    _write_codex_rollout(rollout_path, session_id=session_id)
    _write_global_config(
        tmp_path / "agentos-home" / "config.json",
        provider_instances=[{"provider": "codex", "home": str(extra_codex_home)}],
    )

    assert main(["chat", "session", "find", session_id]) == 0
    payload = json.loads(capsys.readouterr().out)

    codex_finding = next(finding for finding in payload["findings"] if finding["provider"] == "codex")
    assert payload["provider_count"] == 1
    assert codex_finding["path"] == str(rollout_path.resolve())


def test_chat_session_find_returns_direct_copilot_artifacts(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "663f2740-5d31-4098-af41-66b3389adb24"
    session_root = home / ".copilot" / "session-state" / session_id
    _write(session_root / "events.jsonl", '{"event":"started"}\n')
    _write(session_root / "plan.md", "# plan\n")
    _write(session_root / "checkpoints" / "index.md", "# checkpoints\n")

    assert main(["chat", "session", "find", session_id]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "ok"
    assert payload["command"] == "chat session find"
    assert payload["query"] == session_id
    assert payload["grep_enabled"] is False
    assert payload["provider_count"] == 1

    copilot_provider = next(item for item in payload["providers"] if item["provider"] == "copilot-cli")
    assert copilot_provider["finding_count"] == 1
    assert copilot_provider["strategies_attempted"] == ["path"]

    found_paths = {finding["path"] for finding in payload["findings"] if finding["provider"] == "copilot-cli"}
    assert str(session_root.resolve()) in found_paths
    assert str((session_root / "events.jsonl").resolve()) not in found_paths
    assert str((session_root / "plan.md").resolve()) not in found_paths
    assert str((session_root / "checkpoints").resolve()) not in found_paths
    assert str((session_root / "checkpoints" / "index.md").resolve()) not in found_paths


def test_chat_session_find_returns_opencode_sqlite_row(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    db_path = home / ".local" / "share" / "opencode" / "opencode.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    session_id = "ses_3386643b2ffegZgI4IgNfmL9n3"

    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("CREATE TABLE session (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO session (id) VALUES (?)", (session_id,))
        connection.commit()
    finally:
        connection.close()

    assert main(["chat", "session", "find", session_id]) == 0
    payload = json.loads(capsys.readouterr().out)

    sqlite_finding = next(
        finding
        for finding in payload["findings"]
        if finding["provider"] == "opencode" and finding["match_kind"] == "sqlite_row"
    )
    assert sqlite_finding["strategy"] == "sqlite"
    assert sqlite_finding["path"] == str(db_path.resolve())

    opencode_provider = next(item for item in payload["providers"] if item["provider"] == "opencode")
    assert payload["provider_count"] == 1
    assert opencode_provider["sqlite_db_exists"] is True
    assert "sqlite" in opencode_provider["strategies_attempted"]


def test_chat_session_find_returns_openclaw_transcript_artifact(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "061729c9-f0c0-4d62-a3fb-1d21553fc0e4"
    transcript_path = _write_openclaw_session(
        home / ".openclaw" / "agents" / "main" / "sessions",
        session_id=session_id,
    )

    assert main(["chat", "session", "find", session_id]) == 0
    payload = json.loads(capsys.readouterr().out)

    openclaw_findings = [finding for finding in payload["findings"] if finding["provider"] == "openclaw"]
    assert payload["provider_count"] == 1
    assert [finding["path"] for finding in openclaw_findings] == [str(transcript_path.resolve())]

    openclaw_provider = next(item for item in payload["providers"] if item["provider"] == "openclaw")
    assert openclaw_provider["finding_count"] == 1
    assert openclaw_provider["strategies_attempted"] == ["path"]


def test_chat_session_find_only_returns_canonical_claude_session_artifacts_by_default(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "663f2740-5d31-4098-af41-66b3389adb24"
    project_file = home / ".claude" / "projects" / "workspace" / f"{session_id}.jsonl"
    _write(project_file, '{"event":"message"}\n')
    _write(home / ".claude" / "file-history" / session_id / "foo@v1", "history\n")
    _write(home / ".claude" / "session-env" / session_id, "env\n")
    _write(home / ".claude" / "debug" / f"{session_id}.txt", "debug\n")

    assert main(["chat", "session", "find", session_id]) == 0
    payload = json.loads(capsys.readouterr().out)

    claude_findings = [finding for finding in payload["findings"] if finding["provider"] == "claude-code"]
    assert [finding["path"] for finding in claude_findings] == [str(project_file.resolve())]

    claude_provider = next(item for item in payload["providers"] if item["provider"] == "claude-code")
    assert payload["provider_count"] == 1
    assert claude_provider["finding_count"] == 1
    assert claude_provider["strategies_attempted"] == ["path"]


def test_chat_session_find_supports_exact_claude_name_matches(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "663f2740-5d31-4098-af41-66b3389adb24"
    title = "Claude Session Title"
    desktop_path = (
        home
        / "Library"
        / "Application Support"
        / "Claude"
        / "claude-code-sessions"
        / "workspace"
        / f"{session_id}.json"
    )
    _write_claude_desktop_session(
        desktop_path,
        session_id=session_id,
        title=title,
    )

    assert main(["chat", "session", "find", title]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["query"] == title
    assert payload["provider_count"] == 1
    claude_provider = next(item for item in payload["providers"] if item["provider"] == "claude-code")
    assert claude_provider["finding_count"] == 1
    claude_finding = next(finding for finding in payload["findings"] if finding["provider"] == "claude-code")
    assert claude_finding["matched_field"] == "title"
    assert claude_finding["matched_value"] == title
    assert claude_finding["session_id"] == session_id
    assert claude_finding["title"] == title
    assert claude_finding["path"] == str(desktop_path.resolve())


def test_chat_session_find_supports_exact_codex_name_matches(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "019cd2fe-ff22-70f2-a131-2c00c0b21166"
    thread_name = "tape-uri-discovery-refactor"
    rollout_path = (
        home / ".codex" / "sessions" / "2026" / "03" / "10" / f"rollout-2026-03-10T12-13-33-{session_id}.jsonl"
    )
    _write_codex_rollout(rollout_path, session_id=session_id)
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(["chat", "session", "find", thread_name]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["query"] == thread_name
    assert payload["provider_count"] == 1
    codex_provider = next(item for item in payload["providers"] if item["provider"] == "codex")
    assert codex_provider["finding_count"] == 1
    codex_finding = next(finding for finding in payload["findings"] if finding["provider"] == "codex")
    assert codex_finding["matched_field"] == "thread_name"
    assert codex_finding["matched_value"] == thread_name
    assert codex_finding["session_id"] == session_id
    assert codex_finding["thread_name"] == thread_name
    assert codex_finding["path"] == str(rollout_path.resolve())


def test_chat_session_find_includes_grep_results_only_when_requested(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "663f2740-5d31-4098-af41-66b3389adb24"
    index_path = home / ".codex" / "session_index.jsonl"
    _write(index_path, f'{{"session_id":"{session_id}"}}\n')

    assert main(["chat", "session", "find", session_id]) == 0
    payload_without_grep = json.loads(capsys.readouterr().out)

    assert payload_without_grep["grep_enabled"] is False
    assert payload_without_grep["provider_count"] == 0
    assert payload_without_grep["providers"] == []
    assert not any(finding["provider"] == "codex" for finding in payload_without_grep["findings"])

    assert main(["chat", "session", "find", session_id, "--grep"]) == 0
    payload_with_grep = json.loads(capsys.readouterr().out)

    codex_provider = next(item for item in payload_with_grep["providers"] if item["provider"] == "codex")
    assert payload_with_grep["grep_enabled"] is True
    assert payload_with_grep["provider_count"] == 1
    assert codex_provider["strategies_attempted"] == ["path", "grep"]
    assert codex_provider["finding_count"] == 1
    grep_finding = next(
        finding
        for finding in payload_with_grep["findings"]
        if finding["provider"] == "codex" and finding["match_kind"] == "grep_content"
    )
    assert grep_finding["strategy"] == "grep"
    assert grep_finding["path"] == str(index_path.resolve())
    assert grep_finding["line_number"] == 1


def test_chat_session_find_grep_uses_declared_grep_roots_without_scanning_nested_direct_targets(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "663f2740-5d31-4098-af41-66b3389adb24"
    project_root = home / ".claude" / "projects" / "workspace"
    desktop_root = home / "Library" / "Application Support" / "Claude" / "claude-code-sessions" / "workspace"
    _write(project_root / f"{session_id}.jsonl", '{"event":"message"}\n')
    _write(desktop_root / f"{session_id}.json", '{"sessionId":"x","title":"x"}\n')

    scanned_targets: list[Path] = []
    original_scan = core._scan_grep_findings

    def _recording_scan(*, provider: str, target: Path, session_id: str) -> list[dict[str, object]]:
        scanned_targets.append(target)
        return original_scan(provider=provider, target=target, session_id=session_id)

    monkeypatch.setattr(core, "_scan_grep_findings", _recording_scan)

    assert main(["chat", "session", "find", session_id, "--grep"]) == 0
    _ = json.loads(capsys.readouterr().out)

    scanned_target_paths = {path.resolve() for path in scanned_targets}
    assert (home / ".claude").resolve() in scanned_target_paths
    assert (home / "Library" / "Application Support" / "Claude" / "claude-code-sessions").resolve() in scanned_target_paths
    assert project_root.resolve() not in scanned_target_paths


def test_chat_session_find_returns_empty_payload_when_no_provider_matches(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    assert main(["chat", "session", "find", "663f2740-5d31-4098-af41-66b3389adb24"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["finding_count"] == 0
    assert payload["provider_count"] == 0
    assert payload["providers"] == []


def test_chat_session_find_full_output_keeps_zero_finding_providers(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    assert main(["chat", "session", "find", "--full-output", "663f2740-5d31-4098-af41-66b3389adb24"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["finding_count"] == 0
    assert payload["provider_count"] == 6
    assert len(payload["providers"]) == 6
    assert all(provider["finding_count"] == 0 for provider in payload["providers"])


def test_chat_session_find_rejects_path_separators(capsys) -> None:
    assert main(["chat", "session", "find", "bad/id"]) == 1
    stderr = capsys.readouterr().err
    assert "session query must not contain path separators" in stderr


def test_chat_session_find_supports_openclaw_logical_session_keys(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "9ce6dc88-dd77-4ea1-9c6b-2c4e9fd5d401"
    session_key = "agent:main:telegram:direct:734641842"
    transcript_path = _write_openclaw_session(
        home / ".openclaw" / "agents" / "main" / "sessions",
        session_id=session_id,
        agent_key=session_key,
    )

    assert main(["chat", "session", "find", session_key]) == 0
    payload = json.loads(capsys.readouterr().out)

    openclaw_finding = next(finding for finding in payload["findings"] if finding["provider"] == "openclaw")
    assert payload["provider_count"] == 1
    assert openclaw_finding["path"] == str(transcript_path.resolve())
    assert openclaw_finding["matched_field"] == "session_key"
    assert openclaw_finding["matched_value"] == session_key
    assert openclaw_finding["session_id"] == session_id
    assert openclaw_finding["session_keys"] == [session_key]
