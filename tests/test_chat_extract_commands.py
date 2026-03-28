from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from agentos.cli import main


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_codex_rollout(
    path: Path,
    *,
    session_id: str,
    user_text: str = "hello from codex",
    assistant_text: str = "codex reply",
    originator: str = "codex_cli_rs",
) -> None:
    records = [
        {
            "timestamp": "2026-03-08T01:08:59.089Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "originator": originator,
                "source": "cli",
            },
        },
        {
            "timestamp": "2026-03-08T01:08:59.091Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": "<permissions instructions>\ninternal developer message",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-03-08T01:08:59.092Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "# AGENTS.md instructions for /tmp/project",
                    }
                ],
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
    _write(
        path,
        "\n".join(json.dumps(record) for record in records) + "\n",
    )


def _write_global_config(path: Path, *, provider_instances: list[dict[str, object]]) -> None:
    _write(
        path,
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "chat": {
                    "session": {
                        "provider_instances": provider_instances,
                    },
                },
            }
        ),
    )


def _primary_backing_artifact_path(session: dict[str, object]) -> str | None:
    artifact = session.get("primary_backing_artifact")
    if not isinstance(artifact, dict):
        return None
    path = artifact.get("path")
    return path if isinstance(path, str) else None


def _write_claude_code_session(
    path: Path,
    *,
    session_id: str,
    user_text: str = "hello from claude",
    assistant_text: str = "claude reply",
) -> None:
    records = [
        {
            "type": "file-history-snapshot",
            "messageId": "snapshot-1",
            "snapshot": {
                "messageId": "snapshot-1",
                "trackedFileBackups": {},
                "timestamp": "2026-03-08T12:05:12.017Z",
            },
            "isSnapshotUpdate": False,
        },
        {
            "parentUuid": None,
            "isSidechain": False,
            "userType": "external",
            "cwd": "/tmp/project",
            "sessionId": session_id,
            "version": "2.1.69",
            "gitBranch": "main",
            "type": "user",
            "message": {
                "role": "user",
                "content": user_text,
            },
            "uuid": "user-1",
            "timestamp": "2026-03-08T12:05:12.017Z",
            "permissionMode": "bypassPermissions",
        },
        {
            "parentUuid": "user-1",
            "isSidechain": False,
            "userType": "external",
            "cwd": "/tmp/project",
            "sessionId": session_id,
            "version": "2.1.69",
            "gitBranch": "main",
            "message": {
                "model": "claude-opus-4-6",
                "id": "msg_tool",
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_123",
                        "name": "Read",
                        "input": {
                            "file_path": "/tmp/project/notes.md",
                        },
                    }
                ],
                "stop_reason": "tool_use",
                "stop_sequence": None,
            },
            "requestId": "req_tool",
            "type": "assistant",
            "uuid": "assistant-tool",
            "timestamp": "2026-03-08T12:05:14.815Z",
        },
        {
            "parentUuid": "assistant-tool",
            "isSidechain": False,
            "userType": "external",
            "cwd": "/tmp/project",
            "sessionId": session_id,
            "version": "2.1.69",
            "gitBranch": "main",
            "slug": "sample-slug",
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_123",
                        "content": "tool output body",
                    }
                ],
            },
            "uuid": "user-tool-result",
            "timestamp": "2026-03-08T12:05:16.444Z",
            "sourceToolAssistantUUID": "assistant-tool",
            "toolUseResult": {
                "type": "text",
            },
        },
        {
            "parentUuid": "user-tool-result",
            "isSidechain": False,
            "userType": "external",
            "cwd": "/tmp/project",
            "sessionId": session_id,
            "version": "2.1.69",
            "gitBranch": "main",
            "slug": "sample-slug",
            "message": {
                "model": "claude-opus-4-6",
                "id": "msg_text",
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "",
                        "signature": "sig",
                    },
                    {
                        "type": "text",
                        "text": assistant_text,
                    },
                ],
                "stop_reason": "end_turn",
                "stop_sequence": None,
            },
            "requestId": "req_text",
            "type": "assistant",
            "uuid": "assistant-text",
            "timestamp": "2026-03-08T12:05:24.928Z",
        },
        {
            "parentUuid": "assistant-text",
            "isSidechain": False,
            "userType": "external",
            "cwd": "/tmp/project",
            "sessionId": session_id,
            "version": "2.1.69",
            "gitBranch": "main",
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Base directory for this skill: /tmp/skill\n\nmetadata body",
                    }
                ],
            },
            "isMeta": True,
            "uuid": "user-meta",
            "timestamp": "2026-03-08T12:05:25.000Z",
            "sourceToolUseID": "toolu_skill",
        },
        {
            "parentUuid": "assistant-text",
            "isSidechain": False,
            "userType": "external",
            "cwd": "/tmp/project",
            "sessionId": session_id,
            "version": "2.1.69",
            "gitBranch": "main",
            "slug": "sample-slug",
            "type": "system",
            "subtype": "turn_duration",
            "durationMs": 1234,
            "timestamp": "2026-03-08T12:05:26.000Z",
            "uuid": "system-1",
            "isMeta": False,
        },
        {
            "parentUuid": "assistant-text",
            "isSidechain": False,
            "userType": "external",
            "cwd": "/tmp/project",
            "sessionId": session_id,
            "version": "2.1.69",
            "gitBranch": "main",
            "slug": "sample-slug",
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "[Request interrupted by user]",
                    }
                ],
            },
            "uuid": "user-interrupted",
            "timestamp": "2026-03-08T12:05:27.000Z",
        },
    ]
    _write(path, "\n".join(json.dumps(record) for record in records) + "\n")


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


def _write_opencode_session(
    root: Path,
    *,
    session_id: str,
    user_text: str = "hello from opencode",
    assistant_text: str = "opencode reply",
) -> tuple[Path, Path]:
    diff_path = root / "storage" / "session_diff" / f"{session_id}.json"
    _write(diff_path, "[]\n")

    db_path = root / "opencode.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute(
            """
            CREATE TABLE session (
                id TEXT PRIMARY KEY,
                time_updated INTEGER
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE message (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                time_created INTEGER NOT NULL,
                time_updated INTEGER NOT NULL,
                data TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE part (
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                time_created INTEGER NOT NULL,
                time_updated INTEGER NOT NULL,
                data TEXT NOT NULL
            )
            """
        )

        connection.execute(
            "INSERT INTO session (id, time_updated) VALUES (?, ?)",
            (session_id, 1772875306929),
        )

        connection.execute(
            "INSERT INTO message (id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?)",
            (
                "msg-user-1",
                session_id,
                1772875267171,
                1772875267171,
                json.dumps({"role": "user", "time": {"created": 1772875267171}}),
            ),
        )
        connection.execute(
            "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "part-user-1",
                "msg-user-1",
                session_id,
                1772875267175,
                1772875267175,
                json.dumps({"type": "text", "text": user_text}),
            ),
        )

        connection.execute(
            "INSERT INTO message (id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?)",
            (
                "msg-assistant-tool",
                session_id,
                1772875267182,
                1772875276063,
                json.dumps({"role": "assistant", "finish": "tool-calls"}),
            ),
        )
        connection.execute(
            "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "part-assistant-step-start",
                "msg-assistant-tool",
                session_id,
                1772875270660,
                1772875270661,
                json.dumps({"type": "step-start", "snapshot": "abc123"}),
            ),
        )
        connection.execute(
            "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "part-assistant-reasoning",
                "msg-assistant-tool",
                session_id,
                1772875272818,
                1772875273838,
                json.dumps({"type": "reasoning", "text": "checking OpenCode settings"}),
            ),
        )
        connection.execute(
            "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "part-assistant-tool",
                "msg-assistant-tool",
                session_id,
                1772875273839,
                1772875273857,
                json.dumps(
                    {
                        "type": "tool",
                        "tool": "read",
                        "state": {
                            "status": "completed",
                            "input": {"filePath": "/tmp/project/README.md"},
                        },
                    }
                ),
            ),
        )
        connection.execute(
            "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "part-assistant-step-finish",
                "msg-assistant-tool",
                session_id,
                1772875273860,
                1772875273860,
                json.dumps({"type": "step-finish"}),
            ),
        )

        connection.execute(
            "INSERT INTO message (id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?)",
            (
                "msg-assistant-final",
                session_id,
                1772875300147,
                1772875300147,
                json.dumps({"role": "assistant", "finish": "stop"}),
            ),
        )
        connection.execute(
            "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "part-assistant-final-text",
                "msg-assistant-final",
                session_id,
                1772875300147,
                1772875300147,
                json.dumps({"type": "text", "text": assistant_text}),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    return diff_path, db_path


def _write_gemini_cli_session(
    path: Path,
    *,
    session_id: str,
    user_text: str = "hello from gemini",
    assistant_text: str = "gemini reply",
) -> None:
    payload = {
        "sessionId": session_id,
        "startTime": "2026-03-08T12:05:12.017Z",
        "lastUpdated": "2026-03-08T12:05:24.928Z",
        "messages": [
            {
                "id": "user-1",
                "timestamp": "2026-03-08T12:05:12.017Z",
                "type": "user",
                "content": [
                    {"text": user_text},
                    {"text": "\n--- Content from referenced files ---"},
                    {"text": "\nContent from @notes.md:\n"},
                    {"text": "referenced file body"},
                    {"text": "\n--- End of content ---"},
                ],
            },
            {
                "id": "gemini-tool",
                "timestamp": "2026-03-08T12:05:18.000Z",
                "type": "gemini",
                "content": "",
                "thoughts": [
                    {
                        "subject": "Investigating",
                        "description": "checking Gemini workspace context",
                        "timestamp": "2026-03-08T12:05:18.500Z",
                    }
                ],
                "toolCalls": [
                    {
                        "id": "read-1",
                        "name": "read",
                        "args": {"file_path": "/tmp/project/notes.md"},
                        "result": [
                            {
                                "functionResponse": {
                                    "id": "read-1",
                                    "name": "read",
                                    "response": {"output": "tool output body"},
                                }
                            }
                        ],
                        "status": "success",
                        "timestamp": "2026-03-08T12:05:19.000Z",
                    }
                ],
            },
            {
                "id": "gemini-text",
                "timestamp": "2026-03-08T12:05:24.928Z",
                "type": "gemini",
                "content": assistant_text,
                "thoughts": [
                    {
                        "subject": "Complete",
                        "description": "ready to answer",
                        "timestamp": "2026-03-08T12:05:24.500Z",
                    }
                ],
                "tokens": {
                    "input": 10,
                    "output": 5,
                    "total": 15,
                },
                "model": "gemini-2.5-flash",
            },
            {
                "id": "info-1",
                "timestamp": "2026-03-08T12:05:25.000Z",
                "type": "info",
                "content": "Connected to VS Code",
            },
            {
                "id": "error-1",
                "timestamp": "2026-03-08T12:05:26.000Z",
                "type": "error",
                "content": "[API Error: synthetic failure]",
            },
        ],
    }
    _write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _write_copilot_cli_session(
    path: Path,
    *,
    session_id: str,
    user_text: str = "hello from copilot",
    assistant_text: str = "copilot reply",
) -> None:
    records = [
        {
            "type": "session.start",
            "data": {
                "sessionId": session_id,
                "version": 1,
                "producer": "copilot-agent",
                "copilotVersion": "0.0.418",
                "startTime": "2026-03-08T12:05:10.000Z",
            },
            "id": "session-start",
            "timestamp": "2026-03-08T12:05:10.000Z",
            "parentId": None,
        },
        {
            "type": "session.info",
            "data": {
                "infoType": "authentication",
                "message": "Logged in with GitHub Copilot",
            },
            "id": "session-info",
            "timestamp": "2026-03-08T12:05:11.000Z",
            "parentId": "session-start",
        },
        {
            "type": "user.message",
            "data": {
                "content": user_text,
                "transformedContent": (
                    "<current_datetime>2026-03-08T12:05:12.017Z</current_datetime>\n\n"
                    f"{user_text}"
                ),
                "attachments": [],
            },
            "id": "user-1",
            "timestamp": "2026-03-08T12:05:12.017Z",
            "parentId": "session-info",
        },
        {
            "type": "assistant.turn_start",
            "data": {
                "turnId": "0",
            },
            "id": "assistant-turn-start-1",
            "timestamp": "2026-03-08T12:05:13.000Z",
            "parentId": "user-1",
        },
        {
            "type": "assistant.message",
            "data": {
                "messageId": "assistant-tool",
                "content": "",
                "toolRequests": [
                    {
                        "toolCallId": "call_1",
                        "name": "bash",
                        "arguments": {
                            "command": "ls",
                            "description": "Inspect workspace files",
                        },
                        "type": "function",
                    }
                ],
                "reasoningText": "Planning workspace inspection",
            },
            "id": "assistant-message-tool",
            "timestamp": "2026-03-08T12:05:14.000Z",
            "parentId": "assistant-turn-start-1",
        },
        {
            "type": "tool.execution_start",
            "data": {
                "toolCallId": "call_1",
                "toolName": "bash",
                "arguments": {
                    "command": "ls",
                    "description": "Inspect workspace files",
                },
            },
            "id": "tool-start-1",
            "timestamp": "2026-03-08T12:05:15.000Z",
            "parentId": "assistant-message-tool",
        },
        {
            "type": "tool.execution_complete",
            "data": {
                "toolCallId": "call_1",
                "toolName": "bash",
                "model": "gpt-5.3-codex",
                "success": True,
                "result": {
                    "content": "README.md\nplan.md",
                    "detailedContent": "README.md\nplan.md\n<exited with exit code 0>",
                },
            },
            "id": "tool-complete-1",
            "timestamp": "2026-03-08T12:05:16.000Z",
            "parentId": "tool-start-1",
        },
        {
            "type": "assistant.turn_end",
            "data": {
                "turnId": "0",
            },
            "id": "assistant-turn-end-1",
            "timestamp": "2026-03-08T12:05:17.000Z",
            "parentId": "tool-complete-1",
        },
        {
            "type": "assistant.turn_start",
            "data": {
                "turnId": "1",
            },
            "id": "assistant-turn-start-2",
            "timestamp": "2026-03-08T12:05:18.000Z",
            "parentId": "assistant-turn-end-1",
        },
        {
            "type": "assistant.message",
            "data": {
                "messageId": "assistant-final",
                "content": assistant_text,
                "toolRequests": [],
                "reasoningText": "Ready to answer",
            },
            "id": "assistant-message-final",
            "timestamp": "2026-03-08T12:05:24.928Z",
            "parentId": "assistant-turn-start-2",
        },
        {
            "type": "assistant.turn_end",
            "data": {
                "turnId": "1",
            },
            "id": "assistant-turn-end-2",
            "timestamp": "2026-03-08T12:05:25.000Z",
            "parentId": "assistant-message-final",
        },
    ]
    _write(path, "\n".join(json.dumps(record) for record in records) + "\n")


def _write_openclaw_session(
    sessions_dir: Path,
    *,
    session_id: str,
    agent_key: str = "agent:main:main",
    user_text: str = "hello from openclaw",
    assistant_text: str = "openclaw reply",
) -> Path:
    transcript_path = sessions_dir / f"{session_id}.jsonl"
    records = [
        {
            "type": "session",
            "version": 3,
            "id": session_id,
            "timestamp": "2026-03-08T12:05:10.000Z",
            "cwd": "/Users/pereiro/.openclaw/workspace",
        },
        {
            "type": "model_change",
            "id": "model-1",
            "timestamp": "2026-03-08T12:05:11.000Z",
            "provider": "openai-codex",
            "modelId": "gpt-5.3-codex",
        },
        {
            "type": "message",
            "id": "msg-user-1",
            "timestamp": "2026-03-08T12:05:12.017Z",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Sender (untrusted metadata):\n```json\n{\"label\":\"openclaw-tui\"}\n```\n\n"
                            f"{user_text}"
                        ),
                    }
                ],
            },
        },
        {
            "type": "message",
            "id": "msg-assistant-1",
            "timestamp": "2026-03-08T12:05:24.928Z",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Planning OpenClaw response",
                    },
                    {
                        "type": "text",
                        "text": f"[[reply_to_current]] {assistant_text}",
                    },
                ],
            },
        },
    ]
    _write(transcript_path, "\n".join(json.dumps(record) for record in records) + "\n")
    _write(
        sessions_dir / "sessions.json",
        json.dumps(
            {
                agent_key: {
                    "sessionId": session_id,
                    "updatedAt": 1772995738498,
                    "sessionFile": str(transcript_path.resolve()),
                }
            }
        ),
    )
    return transcript_path


def test_chat_session_extract_codex_uses_provider_specific_lookup(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    codex_path = (
        home
        / ".codex"
        / "sessions"
        / "2026"
        / "03"
        / "08"
        / f"rollout-2026-03-08T01-05-38-{session_id}.jsonl"
    )
    _write_codex_rollout(codex_path, session_id=session_id)
    _write(
        home / ".claude" / "projects" / "workspace" / f"{session_id}.jsonl",
        '{"timestamp":"2026-03-08T01:08:59.000Z","type":"message"}\n',
    )

    assert main(["chat", "session", "extract", session_id]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload == [
        {
            "role": "user",
            "timestamp": "2026-03-08T01:08:59.093Z",
            "text": "hello from codex",
        },
        {
            "role": "assistant",
            "timestamp": "2026-03-08T01:08:59.094Z",
            "text": "codex reply",
        },
    ]


def test_chat_session_extract_codex_supports_thread_name_queries(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "019cd2fe-ff22-70f2-a131-2c00c0b21166"
    thread_name = "tape-uri-discovery-refactor"
    codex_path = (
        home
        / ".codex"
        / "sessions"
        / "2026"
        / "03"
        / "10"
        / f"rollout-2026-03-10T12-13-33-{session_id}.jsonl"
    )
    _write_codex_rollout(codex_path, session_id=session_id)
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(["chat", "session", "extract", thread_name]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload[0]["text"] == "hello from codex"
    assert payload[1]["text"] == "codex reply"


def test_chat_session_extract_uses_configured_extra_codex_home(
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
    codex_path = (
        extra_codex_home
        / "sessions"
        / "2026"
        / "03"
        / "09"
        / f"rollout-2026-03-09T01-05-38-{session_id}.jsonl"
    )
    _write_codex_rollout(codex_path, session_id=session_id)
    _write_global_config(
        tmp_path / "agentos-home" / "config.json",
        provider_instances=[{"provider": "codex", "home": str(extra_codex_home)}],
    )

    assert main(["chat", "session", "extract", session_id]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload[0]["text"] == "hello from codex"
    assert payload[1]["text"] == "codex reply"


def test_chat_session_extract_supports_uri_resolution_for_duplicate_codex_session_ids(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "agentos-home"))

    session_id = "119ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    default_codex_path = (
        home
        / ".codex"
        / "sessions"
        / "2026"
        / "03"
        / "08"
        / f"rollout-2026-03-08T01-05-38-{session_id}.jsonl"
    )
    extra_codex_home = tmp_path / "codex-alt"
    extra_codex_path = (
        extra_codex_home
        / "sessions"
        / "2026"
        / "03"
        / "09"
        / f"rollout-2026-03-09T01-05-38-{session_id}.jsonl"
    )
    _write_codex_rollout(
        default_codex_path,
        session_id=session_id,
        user_text="default codex user",
        assistant_text="default codex assistant",
    )
    _write_codex_rollout(
        extra_codex_path,
        session_id=session_id,
        user_text="extra codex user",
        assistant_text="extra codex assistant",
    )
    _write_global_config(
        tmp_path / "agentos-home" / "config.json",
        provider_instances=[{"provider": "codex", "home": str(extra_codex_home)}],
    )

    assert main(["chat", "session", "extract", session_id]) == 1
    assert f"multiple extractable backing artifacts found for query {session_id}" in capsys.readouterr().err

    assert main(["chat", "session", "list", "--provider", "codex", "--output", "json"]) == 0
    list_payload = json.loads(capsys.readouterr().out)
    target_session = next(
        session
        for session in list_payload["sessions"]
        if _primary_backing_artifact_path(session) == str(extra_codex_path.resolve())
    )
    uri = target_session["uri"]
    uri_prefix, fingerprint, uri_session_id = uri.rsplit("/", 2)
    short_uri = f"{uri_prefix}/{fingerprint[:12]}/{uri_session_id}"

    assert main(["chat", "session", "extract", short_uri]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload[0]["text"] == "extra codex user"
    assert payload[1]["text"] == "extra codex assistant"


def test_chat_session_extract_uses_configured_claude_code_homes(
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
    claude_path = extra_claude_home / "projects" / "workspace" / f"{session_id}.jsonl"
    _write_claude_code_session(claude_path, session_id=session_id)
    _write_global_config(
        tmp_path / "agentos-home" / "config.json",
        provider_instances=[{"provider": "claude-code", "homes": {"cli": str(extra_claude_home)}}],
    )

    assert main(["chat", "session", "extract", session_id]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload[0]["text"] == "hello from claude"
    assert payload[1]["text"] == "claude reply"


def test_chat_session_extract_codex_file_mode_does_not_require_session_id(
    tmp_path: Path,
    capsys,
) -> None:
    rollout_path = tmp_path / "codex-rollout.jsonl"
    _write_codex_rollout(
        rollout_path,
        session_id="019ccafa-7835-7fc3-ac17-0e0a0f675fd5",
        user_text="markdown user",
        assistant_text="markdown assistant",
    )

    assert (
        main(
            [
                "chat",
                "session",
                "extract",
                "--format",
                "markdown",
                "--file",
                str(rollout_path),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out

    assert "### USER [2026-03-08T01:08:59.093Z]" in output
    assert "```markdown" in output
    assert "markdown assistant" in output


def test_chat_session_extract_codex_raw_includes_developer_content(
    tmp_path: Path,
    capsys,
) -> None:
    rollout_path = tmp_path / "codex-rollout.jsonl"
    _write_codex_rollout(
        rollout_path,
        session_id="019ccafa-7835-7fc3-ac17-0e0a0f675fd5",
    )

    assert (
        main(
            [
                "chat",
                "session",
                "extract",
                "--raw",
                "--file",
                str(rollout_path),
            ]
        )
        == 0
    )
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert [turn["role"] for turn in payload[:3]] == ["developer", "user", "user"]


def test_chat_session_extract_claude_code_uses_provider_specific_lookup(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "8948fa51-ae3d-4a28-bf5c-d9d8d8069a6b"
    claude_path = home / ".claude" / "projects" / "workspace" / f"{session_id}.jsonl"
    _write_claude_code_session(claude_path, session_id=session_id)

    assert main(["chat", "session", "extract", session_id]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload == [
        {
            "role": "user",
            "timestamp": "2026-03-08T12:05:12.017Z",
            "text": "hello from claude",
        },
        {
            "role": "assistant",
            "timestamp": "2026-03-08T12:05:24.928Z",
            "text": "claude reply",
        },
    ]


def test_chat_session_extract_claude_code_file_mode_infers_provenance(
    tmp_path: Path,
    capsys,
) -> None:
    claude_path = tmp_path / "claude-session.jsonl"
    _write_claude_code_session(
        claude_path,
        session_id="8948fa51-ae3d-4a28-bf5c-d9d8d8069a6b",
        user_text="claude markdown user",
        assistant_text="claude markdown assistant",
    )

    assert main(["chat", "session", "extract", "--format", "markdown", "--file", str(claude_path)]) == 0
    output = capsys.readouterr().out

    assert "### USER [2026-03-08T12:05:12.017Z]" in output
    assert "```markdown" in output
    assert "claude markdown assistant" in output


def test_chat_session_extract_claude_code_raw_includes_tool_blocks(
    tmp_path: Path,
    capsys,
) -> None:
    claude_path = tmp_path / "claude-session.jsonl"
    _write_claude_code_session(
        claude_path,
        session_id="8948fa51-ae3d-4a28-bf5c-d9d8d8069a6b",
    )

    assert main(["chat", "session", "extract", "--raw", "--file", str(claude_path)]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload[0]["role"] == "user"
    assert payload[0]["text"] == "hello from claude"
    assert payload[1]["role"] == "assistant"
    assert '"type": "tool_use"' in payload[1]["text"]
    assert payload[2]["role"] == "user"
    assert payload[2]["text"] == "tool output body"


def test_chat_session_extract_opencode_uses_provider_specific_lookup(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "ses_3386643b2ffegZgI4IgNfmL9n3"
    _write_opencode_session(home / ".local" / "share" / "opencode", session_id=session_id)

    assert main(["chat", "session", "extract", session_id]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload == [
        {
            "role": "user",
            "timestamp": "2026-03-07T09:21:07.171Z",
            "text": "hello from opencode",
        },
        {
            "role": "assistant",
            "timestamp": "2026-03-07T09:21:40.147Z",
            "text": "opencode reply",
        },
    ]


def test_chat_session_extract_opencode_file_mode_infers_provenance(
    tmp_path: Path,
    capsys,
) -> None:
    session_id = "ses_3386643b2ffegZgI4IgNfmL9n3"
    diff_path, _ = _write_opencode_session(
        tmp_path / "opencode",
        session_id=session_id,
        user_text="markdown user",
        assistant_text="markdown assistant",
    )

    assert main(["chat", "session", "extract", "--format", "markdown", "--file", str(diff_path)]) == 0
    output = capsys.readouterr().out

    assert "### USER [2026-03-07T09:21:07.171Z]" in output
    assert "```markdown" in output
    assert "markdown assistant" in output


def test_chat_session_extract_opencode_db_backing_artifact_requires_session_id(
    tmp_path: Path,
    capsys,
) -> None:
    session_id = "ses_3386643b2ffegZgI4IgNfmL9n3"
    _, db_path = _write_opencode_session(
        tmp_path / "opencode",
        session_id=session_id,
    )

    assert main(["chat", "session", "extract", "--file", str(db_path)]) == 1
    assert (
        f"session id is required when extracting from backing artifact: {db_path.resolve()}"
        in capsys.readouterr().err
    )


def test_chat_session_extract_opencode_raw_includes_reasoning_and_tool_blocks(
    tmp_path: Path,
    capsys,
) -> None:
    session_id = "ses_3386643b2ffegZgI4IgNfmL9n3"
    diff_path, _ = _write_opencode_session(
        tmp_path / "opencode",
        session_id=session_id,
    )

    assert main(["chat", "session", "extract", "--raw", "--file", str(diff_path)]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload[0]["role"] == "user"
    assert payload[0]["text"] == "hello from opencode"
    assert any(turn["text"] == "checking OpenCode settings" for turn in payload)
    assert any('"type": "tool"' in turn["text"] for turn in payload)
    assert any('"type": "step-start"' in turn["text"] for turn in payload)


def test_chat_session_extract_gemini_cli_uses_provider_specific_lookup(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "aba05f70-c886-4d1b-9b34-b95402476b94"
    gemini_path = (
        home
        / ".gemini"
        / "tmp"
        / "workspace"
        / "chats"
        / "session-2026-03-08T12-05-aba05f70.json"
    )
    _write_gemini_cli_session(gemini_path, session_id=session_id)

    assert main(["chat", "session", "extract", session_id]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload == [
        {
            "role": "user",
            "timestamp": "2026-03-08T12:05:12.017Z",
            "text": "hello from gemini",
        },
        {
            "role": "assistant",
            "timestamp": "2026-03-08T12:05:24.928Z",
            "text": "gemini reply",
        },
    ]


def test_chat_session_extract_gemini_cli_file_mode_infers_provenance(
    tmp_path: Path,
    capsys,
) -> None:
    session_id = "aba05f70-c886-4d1b-9b34-b95402476b94"
    gemini_path = tmp_path / "gemini-session.json"
    _write_gemini_cli_session(
        gemini_path,
        session_id=session_id,
        user_text="gemini markdown user",
        assistant_text="gemini markdown assistant",
    )

    assert main(["chat", "session", "extract", "--format", "markdown", "--file", str(gemini_path)]) == 0
    output = capsys.readouterr().out

    assert "### USER [2026-03-08T12:05:12.017Z]" in output
    assert "```markdown" in output
    assert "gemini markdown assistant" in output


def test_chat_session_extract_gemini_cli_raw_includes_thoughts_tools_info_and_error(
    tmp_path: Path,
    capsys,
) -> None:
    session_id = "aba05f70-c886-4d1b-9b34-b95402476b94"
    gemini_path = tmp_path / "gemini-session.json"
    _write_gemini_cli_session(gemini_path, session_id=session_id)

    assert main(["chat", "session", "extract", "--raw", "--file", str(gemini_path)]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload[0]["role"] == "user"
    assert payload[0]["text"] == "hello from gemini"
    assert any(turn["text"] == "checking Gemini workspace context" for turn in payload)
    assert any('"name": "read"' in turn["text"] for turn in payload)
    assert any(turn["role"] == "info" and turn["text"] == "Connected to VS Code" for turn in payload)
    assert any(turn["role"] == "error" and turn["text"] == "[API Error: synthetic failure]" for turn in payload)


def test_chat_session_extract_copilot_cli_uses_provider_specific_lookup(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "663f2740-5d31-4098-af41-66b3389adb24"
    copilot_path = home / ".copilot" / "session-state" / session_id / "events.jsonl"
    _write_copilot_cli_session(copilot_path, session_id=session_id)

    assert main(["chat", "session", "extract", session_id]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload == [
        {
            "role": "user",
            "timestamp": "2026-03-08T12:05:12.017Z",
            "text": "hello from copilot",
        },
        {
            "role": "assistant",
            "timestamp": "2026-03-08T12:05:24.928Z",
            "text": "copilot reply",
        },
    ]


def test_chat_session_extract_copilot_cli_file_mode_infers_provenance(
    tmp_path: Path,
    capsys,
) -> None:
    session_id = "663f2740-5d31-4098-af41-66b3389adb24"
    copilot_path = tmp_path / "copilot-session.jsonl"
    _write_copilot_cli_session(
        copilot_path,
        session_id=session_id,
        user_text="copilot markdown user",
        assistant_text="copilot markdown assistant",
    )

    assert main(["chat", "session", "extract", "--format", "markdown", "--file", str(copilot_path)]) == 0
    output = capsys.readouterr().out

    assert "### USER [2026-03-08T12:05:12.017Z]" in output
    assert "```markdown" in output
    assert "copilot markdown assistant" in output


def test_chat_session_extract_copilot_cli_raw_includes_reasoning_tools_and_info(
    tmp_path: Path,
    capsys,
) -> None:
    session_id = "663f2740-5d31-4098-af41-66b3389adb24"
    copilot_path = tmp_path / "copilot-session.jsonl"
    _write_copilot_cli_session(copilot_path, session_id=session_id)

    assert main(["chat", "session", "extract", "--raw", "--file", str(copilot_path)]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert any(turn["role"] == "info" and turn["text"] == "Logged in with GitHub Copilot" for turn in payload)
    assert any(turn["role"] == "user" and turn["text"] == "hello from copilot" for turn in payload)
    assert any(turn["role"] == "assistant" and turn["text"] == "Planning workspace inspection" for turn in payload)
    assert any('"name": "bash"' in turn["text"] for turn in payload)
    assert any('"toolName": "bash"' in turn["text"] for turn in payload)
    assert any("README.md\\nplan.md" in turn["text"] for turn in payload)


def test_chat_session_extract_openclaw_uses_provider_specific_lookup(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "061729c9-f0c0-4d62-a3fb-1d21553fc0e4"
    _write_openclaw_session(
        home / ".openclaw" / "agents" / "main" / "sessions",
        session_id=session_id,
    )

    assert main(["chat", "session", "extract", session_id]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload == [
        {
            "role": "user",
            "timestamp": "2026-03-08T12:05:12.017Z",
            "text": "hello from openclaw",
        },
        {
            "role": "assistant",
            "timestamp": "2026-03-08T12:05:24.928Z",
            "text": "openclaw reply",
        },
    ]


def test_chat_session_extract_openclaw_supports_logical_session_keys(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "9ce6dc88-dd77-4ea1-9c6b-2c4e9fd5d401"
    session_key = "agent:main:telegram:direct:734641842"
    _write_openclaw_session(
        home / ".openclaw" / "agents" / "main" / "sessions",
        session_id=session_id,
        agent_key=session_key,
    )

    assert main(["chat", "session", "extract", session_key]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload[0]["text"] == "hello from openclaw"
    assert payload[1]["text"] == "openclaw reply"


def test_chat_session_extract_claude_code_supports_title_queries(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "8948fa51-ae3d-4a28-bf5c-d9d8d8069a6b"
    title = "Claude Session Title"
    claude_path = home / ".claude" / "projects" / "workspace" / f"{session_id}.jsonl"
    _write_claude_code_session(claude_path, session_id=session_id)
    _write_claude_desktop_session(
        home
        / "Library"
        / "Application Support"
        / "Claude"
        / "claude-code-sessions"
        / "workspace"
        / f"{session_id}.json",
        session_id=session_id,
        title=title,
    )

    assert main(["chat", "session", "extract", title]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload[0]["text"] == "hello from claude"
    assert payload[1]["text"] == "claude reply"


def test_chat_session_extract_openclaw_file_mode_infers_provenance(
    tmp_path: Path,
    capsys,
) -> None:
    session_id = "061729c9-f0c0-4d62-a3fb-1d21553fc0e4"
    transcript_path = _write_openclaw_session(
        tmp_path / "openclaw" / "agents" / "main" / "sessions",
        session_id=session_id,
        user_text="openclaw markdown user",
        assistant_text="openclaw markdown assistant",
    )

    assert main(["chat", "session", "extract", "--format", "markdown", "--file", str(transcript_path)]) == 0
    output = capsys.readouterr().out

    assert "### USER [2026-03-08T12:05:12.017Z]" in output
    assert "```markdown" in output
    assert "openclaw markdown assistant" in output


def test_chat_session_extract_openclaw_raw_includes_thinking_and_system_records(
    tmp_path: Path,
    capsys,
) -> None:
    session_id = "061729c9-f0c0-4d62-a3fb-1d21553fc0e4"
    transcript_path = _write_openclaw_session(
        tmp_path / "openclaw" / "agents" / "main" / "sessions",
        session_id=session_id,
    )

    assert main(["chat", "session", "extract", "--raw", "--file", str(transcript_path)]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert any(turn["role"] == "system" and '"type": "session"' in turn["text"] for turn in payload)
    assert any(turn["role"] == "assistant" and turn["text"] == "Planning OpenClaw response" for turn in payload)
    assert any(turn["role"] == "assistant" and turn["text"] == "[[reply_to_current]] openclaw reply" for turn in payload)


def test_chat_session_extract_rejects_unknown_file_provenance(
    tmp_path: Path,
    capsys,
) -> None:
    unknown_path = tmp_path / "unknown-session.jsonl"
    _write(
        unknown_path,
        '{"timestamp":"2026-03-08T01:08:59.000Z","type":"random","payload":{"hello":"world"}}\n',
    )

    assert (
        main(
            [
                "chat",
                "session",
                "extract",
                "--file",
                str(unknown_path),
            ]
    )
        == 1
    )
    assert "unable to infer extractor from backing artifact provenance" in capsys.readouterr().err


def test_chat_session_extract_accepts_codex_tui_rollout_from_file(
    tmp_path: Path,
    capsys,
) -> None:
    session_id = "019d0716-7a2d-7902-ab86-163b76f68ee9"
    rollout_path = tmp_path / "codex" / "sessions" / "2026" / "03" / "19" / "rollout.jsonl"
    _write_codex_rollout(
        rollout_path,
        session_id=session_id,
        user_text="hello from codex-tui",
        assistant_text="codex-tui reply",
        originator="codex-tui",
    )

    assert main(["chat", "session", "extract", "--file", str(rollout_path)]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload == [
        {
            "role": "user",
            "timestamp": "2026-03-08T01:08:59.093Z",
            "text": "hello from codex-tui",
        },
        {
            "role": "assistant",
            "timestamp": "2026-03-08T01:08:59.094Z",
            "text": "codex-tui reply",
        },
    ]


def test_chat_session_extract_requires_session_query_without_file(capsys) -> None:
    assert main(["chat", "session", "extract"]) == 1
    assert "session query is required unless --file is provided" in capsys.readouterr().err
