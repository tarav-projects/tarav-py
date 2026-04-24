from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentos.cli import main
from _helpers import write_text_file as _write


_DEFAULT_CHATLAS_INSTANCE_IDS = object()


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


def _write_codex_dialog_rollout_with_invalid_line(
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
                "content": [{"type": "input_text", "text": user_text}],
            },
        },
        {
            "timestamp": "2026-03-08T01:08:59.094Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": assistant_text}],
            },
        },
    ]
    lines = [
        json.dumps(records[0]),
        "{not-json",
        json.dumps(records[1]),
        json.dumps(records[2]),
    ]
    _write(path, "\n".join(lines) + "\n")
    _set_iso_mtime(path, records[-1]["timestamp"])


def _write_codex_context_rollout(
    path: Path,
    *,
    session_id: str,
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
            "timestamp": "2026-03-08T01:08:59.090Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": "developer instruction"}],
            },
        },
        {
            "timestamp": "2026-03-08T01:08:59.091Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "<environment_context>\nctx"}],
            },
        },
        {
            "timestamp": "2026-03-08T01:08:59.092Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "custom_payload", "value": {"status": "ok"}}],
            },
        },
    ]
    _write(path, "\n".join(json.dumps(record) for record in records) + "\n")
    _set_iso_mtime(path, records[-1]["timestamp"])


def _write_codex_tool_rollout(
    path: Path,
    *,
    session_id: str,
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
            "timestamp": "2026-03-08T01:08:59.090Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "turn-1",
                "started_at": 1772946539,
                "model_context_window": 258400,
                "collaboration_mode_kind": "default",
            },
        },
        {
            "timestamp": "2026-03-08T01:08:59.095Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 10,
                        "output_tokens": 2,
                        "total_tokens": 12,
                    }
                },
                "rate_limits": {
                    "limit_id": "codex",
                    "primary": {
                        "used_percent": 58.0,
                    },
                },
            },
        },
        {
            "timestamp": "2026-03-08T01:08:59.100Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "run pwd"}],
            },
        },
        {
            "timestamp": "2026-03-08T01:09:00.000Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "call-complete",
                "arguments": json.dumps(
                    {
                        "cmd": "pwd",
                        "workdir": "/tmp",
                    }
                ),
            },
        },
        {
            "timestamp": "2026-03-08T01:09:01.000Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-complete",
                "output": "Chunk ID: abc\nOutput:\n/tmp\n",
            },
        },
        {
            "timestamp": "2026-03-08T01:09:01.100Z",
            "type": "event_msg",
            "payload": {
                "type": "exec_command_end",
                "call_id": "call-complete",
                "command": ["/bin/zsh", "-lc", "pwd"],
                "cwd": "/tmp",
                "status": "completed",
                "exit_code": 0,
                "duration": {
                    "secs": 1,
                    "nanos": 250_000_000,
                },
                "stdout": "",
                "stderr": "",
                "aggregated_output": "/tmp\n",
                "turn_id": "turn-1",
            },
        },
        {
            "timestamp": "2026-03-08T01:09:02.000Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "call-incomplete",
                "arguments": "{bad-json",
            },
        },
    ]
    _write(path, "\n".join(json.dumps(record) for record in records) + "\n")
    _set_iso_mtime(path, records[-1]["timestamp"])


def _write_codex_model_run_rollout(
    path: Path,
    *,
    session_id: str,
) -> None:
    records = [
        {
            "timestamp": "2026-03-08T01:08:58.000Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "originator": "codex_cli_rs",
                "source": "cli",
                "model_provider": "openai",
            },
        },
        {
            "timestamp": "2026-03-08T01:08:59.000Z",
            "type": "turn_context",
            "payload": {
                "turn_id": "turn-1",
                "model": "gpt-5.4-mini",
                "effort": "high",
                "cwd": "/tmp/project",
                "approval_policy": "never",
                "sandbox_policy": {"type": "workspace-write"},
                "collaboration_mode": {
                    "mode": "default",
                    "settings": {
                        "model": "gpt-5.4-mini",
                        "reasoning_effort": "high",
                        "developer_instructions": "do not expose this",
                    },
                },
                "current_date": "2026-03-08",
                "timezone": "UTC",
                "truncation_policy": {"mode": "tokens", "limit": 10000},
                "realtime_active": False,
                "summary": "prior summary should stay raw-only",
                "user_instructions": "do not expose this either",
            },
        },
        {
            "timestamp": "2026-03-08T01:09:00.000Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "turn-1",
                "started_at": 1772946540,
                "model_context_window": 258400,
                "collaboration_mode_kind": "default",
            },
        },
        {
            "timestamp": "2026-03-08T01:09:01.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "explain model run"}],
            },
        },
        {
            "timestamp": "2026-03-08T01:09:02.000Z",
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "check context"}],
                "content": None,
                "encrypted_content": "encrypted-reasoning",
            },
        },
        {
            "timestamp": "2026-03-08T01:09:03.000Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "call-run",
                "arguments": json.dumps({"cmd": "pwd", "workdir": "/tmp/project"}),
            },
        },
        {
            "timestamp": "2026-03-08T01:09:04.000Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-run",
                "output": "Output:\n/tmp/project\n",
            },
        },
        {
            "timestamp": "2026-03-08T01:09:04.100Z",
            "type": "event_msg",
            "payload": {
                "type": "exec_command_end",
                "call_id": "call-run",
                "turn_id": "turn-1",
                "command": ["/bin/zsh", "-lc", "pwd"],
                "cwd": "/tmp/project",
                "status": "completed",
                "exit_code": 0,
                "duration": {"secs": 0, "nanos": 500_000_000},
                "aggregated_output": "/tmp/project\n",
            },
        },
        {
            "timestamp": "2026-03-08T01:09:05.000Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-1",
                "completed_at": 1772946545,
                "duration_ms": 5000,
            },
        },
    ]
    _write(path, "\n".join(json.dumps(record) for record in records) + "\n")
    _set_iso_mtime(path, records[-1]["timestamp"])


def _write_codex_multi_turn_model_run_rollout(
    path: Path,
    *,
    session_id: str,
) -> None:
    records = [
        {
            "timestamp": "2026-03-08T01:08:58.000Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "originator": "codex_cli_rs",
                "source": "cli",
                "model_provider": "openai",
            },
        },
        {
            "timestamp": "2026-03-08T01:08:59.000Z",
            "type": "turn_context",
            "payload": {
                "turn_id": "turn-1",
                "model": "gpt-5.4-mini",
                "effort": "high",
            },
        },
        {
            "timestamp": "2026-03-08T01:09:00.000Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "turn-1",
                "started_at": 1772946540,
            },
        },
        {
            "timestamp": "2026-03-08T01:09:01.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "first turn question"}],
            },
        },
        {
            "timestamp": "2026-03-08T01:09:02.000Z",
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "content": None,
                "encrypted_content": "first turn reasoning",
            },
        },
        {
            "timestamp": "2026-03-08T01:09:03.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "first turn answer"}],
            },
        },
        {
            "timestamp": "2026-03-08T01:09:04.000Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-1",
                "completed_at": 1772946544,
                "duration_ms": 4000,
            },
        },
        {
            "timestamp": "2026-03-08T01:09:05.000Z",
            "type": "turn_context",
            "payload": {
                "turn_id": "turn-2",
                "model": "gpt-5.4-mini",
                "effort": "medium",
            },
        },
        {
            "timestamp": "2026-03-08T01:09:06.000Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "turn-2",
                "started_at": 1772946546,
            },
        },
        {
            "timestamp": "2026-03-08T01:09:07.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "second turn question"}],
            },
        },
        {
            "timestamp": "2026-03-08T01:09:08.000Z",
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "content": None,
                "encrypted_content": "second turn reasoning",
            },
        },
        {
            "timestamp": "2026-03-08T01:09:09.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "second turn answer"}],
            },
        },
        {
            "timestamp": "2026-03-08T01:09:10.000Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-2",
                "completed_at": 1772946550,
                "duration_ms": 4000,
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
    cwd: str = "/Users/pereiro/projects/agentos-project/agentos-iterante-dev",
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
            "id": "event-start",
            "timestamp": "2026-04-18T11:00:00.000Z",
            "data": {
                "sessionId": session_id,
                "producer": "copilot-agent",
            },
        },
        {
            "type": "session.model_change",
            "id": "event-model-change",
            "parentId": "event-start",
            "timestamp": "2026-04-18T11:00:00.250Z",
            "data": {
                "newModel": "gpt-4.1",
            },
        },
        {
            "type": "system.message",
            "id": "event-system",
            "parentId": "event-model-change",
            "timestamp": "2026-04-18T11:00:00.500Z",
            "data": {
                "role": "system",
                "content": "copilot system prompt",
            },
        },
        {
            "type": "user.message",
            "id": "event-user",
            "parentId": "event-system",
            "timestamp": "2026-04-18T11:00:01.000Z",
            "data": {
                "content": [{"type": "text", "text": user_text}],
                "transformedContent": f"<context>\n{user_text}\n</context>",
                "interactionId": "copilot-interaction-1",
            },
        },
        {
            "type": "assistant.turn_start",
            "id": "event-turn-start-1",
            "parentId": "event-user",
            "timestamp": "2026-04-18T11:00:01.500Z",
            "data": {
                "turnId": "0",
                "interactionId": "copilot-interaction-1",
            },
        },
        {
            "type": "assistant.message",
            "id": "event-assistant-1",
            "parentId": "event-turn-start-1",
            "timestamp": "2026-04-18T11:00:02.000Z",
            "data": {
                "content": [{"type": "text", "text": assistant_text}],
                "reasoningText": "check repository state",
                "reasoningOpaque": "opaque-reasoning",
                "encryptedContent": "encrypted-reasoning",
                "messageId": "assistant-message-1",
                "requestId": "assistant-request-1",
                "outputTokens": 17,
                "interactionId": "copilot-interaction-1",
                "toolRequests": [
                    {
                        "toolCallId": "tool-call-1",
                        "name": "shell",
                        "arguments": {"cmd": "git status"},
                    }
                ],
            },
        },
        {
            "type": "tool.execution_start",
            "id": "event-tool-start-1",
            "parentId": "event-assistant-1",
            "timestamp": "2026-04-18T11:00:03.000Z",
            "data": {
                "toolCallId": "tool-call-1",
                "toolName": "shell",
                "arguments": {"cmd": "git status"},
                "interactionId": "copilot-interaction-1",
            },
        },
        {
            "type": "tool.execution_complete",
            "id": "event-tool-complete-1",
            "parentId": "event-tool-start-1",
            "timestamp": "2026-04-18T11:00:03.500Z",
            "data": {
                "toolCallId": "tool-call-1",
                "success": True,
                "model": "gpt-4.1",
                "interactionId": "copilot-interaction-1",
                "result": {
                    "content": "On branch main",
                    "detailedContent": "On branch main\nnothing to commit, working tree clean",
                },
            },
        },
        {
            "type": "assistant.turn_end",
            "id": "event-turn-end-1",
            "parentId": "event-tool-complete-1",
            "timestamp": "2026-04-18T11:00:03.700Z",
            "data": {
                "turnId": "0",
            },
        },
        {
            "type": "session.shutdown",
            "id": "event-shutdown",
            "parentId": "event-turn-end-1",
            "timestamp": "2026-04-18T11:00:04.000Z",
            "data": {
                "totalPremiumRequests": 1,
                "currentTokens": 12,
                "systemTokens": 4,
                "conversationTokens": 5,
                "toolDefinitionsTokens": 3,
                "currentModel": "gpt-4.1",
                "modelMetrics": {
                    "gpt-4.1": {
                        "requests": {"count": 1, "cost": 1},
                        "usage": {
                            "inputTokens": 12,
                            "outputTokens": 34,
                            "cacheReadTokens": 0,
                            "cacheWriteTokens": 0,
                            "reasoningTokens": 5,
                        },
                    }
                },
            },
        },
    ]
    _write(path, "\n".join(json.dumps(record) for record in records) + "\n")
    _set_iso_mtime(path, "2026-04-18T11:00:04.000Z")


def _write_claude_session(
    path: Path,
    *,
    session_id: str,
    user_text: str = "hello from claude",
    assistant_text: str = "claude reply",
    include_tool_roundtrip: bool = False,
    include_followup_reply: bool = False,
    include_reasoning_usage: bool = False,
) -> None:
    records = [
        {
            "parentUuid": None,
            "isSidechain": False,
            "userType": "external",
            "cwd": "/tmp/project",
            "sessionId": session_id,
            "version": "2.1.69",
            "message": {
                "role": "user",
                "content": user_text,
            },
            "uuid": "msg-user-1",
            "timestamp": "2026-04-18T11:00:00.000Z",
        },
        {
            "parentUuid": "msg-user-1",
            "isSidechain": False,
            "userType": "external",
            "cwd": "/tmp/project",
            "sessionId": session_id,
            "version": "2.1.69",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": assistant_text},
                    {"type": "text", "text": "tool summary"},
                ],
            },
            "uuid": "msg-assistant-1",
            "timestamp": "2026-04-18T11:00:01.000Z",
        },
    ]
    if include_followup_reply:
        assert include_tool_roundtrip
        records[1]["type"] = "assistant"
        records[1]["message"] = {
            "model": "claude-opus-4-6",
            "id": "msg-tool-assistant-1",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": assistant_text},
                {"type": "text", "text": "tool summary"},
            ],
            "stop_reason": None,
            "stop_sequence": None,
            "stop_details": None,
        }
        records[1]["requestId"] = "req-claude-1"
        if include_reasoning_usage:
            records[1]["message"]["content"] = [
                {
                    "type": "thinking",
                    "thinking": "inspect repository layout before replying",
                    "signature": "claude-thinking-signature-1",
                },
                {"type": "text", "text": assistant_text},
                {"type": "text", "text": "tool summary"},
            ]
    if include_tool_roundtrip:
        records.extend(
            [
                {
                    "parentUuid": "msg-assistant-1",
                    "isSidechain": False,
                    "userType": "external",
                    "cwd": "/tmp/project",
                    "sessionId": session_id,
                    "version": "2.1.69",
                    "type": "assistant",
                    "message": {
                        "model": "claude-opus-4-6",
                        "id": "msg-tool-assistant-1",
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu-claude-1",
                                "name": "Bash",
                                "input": {
                                    "command": "ls /tmp/project",
                                    "description": "List project",
                                },
                                "caller": {"type": "direct"},
                            }
                        ],
                        "stop_reason": "tool_use",
                        "stop_sequence": None,
                        "stop_details": None,
                    },
                    "requestId": "req-claude-1",
                    "uuid": "msg-assistant-tool-1",
                    "timestamp": "2026-04-18T11:00:02.000Z",
                },
                {
                    "parentUuid": "msg-assistant-tool-1",
                    "isSidechain": False,
                    "userType": "external",
                    "cwd": "/tmp/project",
                    "sessionId": session_id,
                    "version": "2.1.69",
                    "type": "progress",
                    "data": {
                        "type": "hook_progress",
                        "hookEvent": "PreToolUse",
                        "hookName": "PreToolUse:Bash",
                        "command": "bash -x ~/.claude/hooks/random-sound.sh&",
                    },
                    "toolUseID": "toolu-claude-1",
                    "parentToolUseID": "toolu-claude-1",
                    "uuid": "progress-pre-1",
                    "timestamp": "2026-04-18T11:00:02.050Z",
                },
                {
                    "parentUuid": "msg-assistant-tool-1",
                    "isSidechain": False,
                    "userType": "external",
                    "cwd": "/tmp/project",
                    "sessionId": session_id,
                    "version": "2.1.69",
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "tool_use_id": "toolu-claude-1",
                                "type": "tool_result",
                                "content": "AGENTS.md\nsrc\ntests",
                                "is_error": False,
                            }
                        ],
                    },
                    "toolUseResult": {
                        "stdout": "AGENTS.md\nsrc\ntests",
                        "stderr": "",
                        "interrupted": False,
                        "isImage": False,
                        "noOutputExpected": False,
                    },
                    "sourceToolAssistantUUID": "msg-assistant-tool-1",
                    "uuid": "msg-user-tool-result-1",
                    "timestamp": "2026-04-18T11:00:02.450Z",
                },
                {
                    "parentUuid": "msg-user-tool-result-1",
                    "isSidechain": False,
                    "userType": "external",
                    "cwd": "/tmp/project",
                    "sessionId": session_id,
                    "version": "2.1.69",
                    "type": "progress",
                    "data": {
                        "type": "hook_progress",
                        "hookEvent": "PostToolUse",
                        "hookName": "PostToolUse:Bash",
                        "command": "bash -x ~/.claude/hooks/random-sound.sh&",
                    },
                    "toolUseID": "toolu-claude-1",
                    "parentToolUseID": "toolu-claude-1",
                    "uuid": "progress-post-1",
                    "timestamp": "2026-04-18T11:00:02.500Z",
                },
            ]
        )
        if include_reasoning_usage:
            records[2]["message"]["usage"] = {
                "input_tokens": 10,
                "output_tokens": 20,
                "cache_creation_input_tokens": 5,
                "cache_read_input_tokens": 7,
                "cache_creation": {
                    "ephemeral_1h_input_tokens": 5,
                    "ephemeral_5m_input_tokens": 0,
                },
                "service_tier": "standard",
                "inference_geo": "not_available",
            }
        if include_followup_reply:
            records.append(
                {
                    "parentUuid": "msg-user-tool-result-1",
                    "isSidechain": False,
                    "userType": "external",
                    "cwd": "/tmp/project",
                    "sessionId": session_id,
                    "version": "2.1.69",
                    "type": "assistant",
                    "message": {
                        "model": "claude-opus-4-6",
                        "id": "msg-assistant-final-1",
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "final claude answer"},
                        ],
                        "stop_reason": "end_turn",
                        "stop_sequence": None,
                        "stop_details": None,
                    },
                    "requestId": "req-claude-2",
                    "uuid": "msg-assistant-final-1",
                    "timestamp": "2026-04-18T11:00:02.800Z",
                }
            )
            if include_reasoning_usage:
                records[-1]["message"]["usage"] = {
                    "input_tokens": 14,
                    "output_tokens": 7,
                    "cache_creation_input_tokens": 2,
                    "cache_read_input_tokens": 11,
                    "cache_creation": {
                        "ephemeral_1h_input_tokens": 2,
                        "ephemeral_5m_input_tokens": 0,
                    },
                    "service_tier": "standard",
                    "inference_geo": "not_available",
                    "speed": "standard",
                    "iterations": [],
                    "server_tool_use": {
                        "web_search_requests": 0,
                        "web_fetch_requests": 0,
                    },
                }
    _write(path, "\n".join(json.dumps(record) for record in records) + "\n")
    _set_iso_mtime(
        path,
        (
            "2026-04-18T11:00:02.800Z"
            if include_followup_reply
            else "2026-04-18T11:00:02.500Z"
            if include_tool_roundtrip
            else "2026-04-18T11:00:01.000Z"
        ),
    )


def _write_opencode_db(
    path: Path,
    *,
    session_id: str,
    user_text: str = "hello from opencode",
    assistant_text: str = "opencode reply",
    keep_wal: bool = False,
) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    if keep_wal:
        connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(
        """
        CREATE TABLE session (
            id text PRIMARY KEY,
            time_updated integer NOT NULL
        );
        CREATE TABLE message (
            id text PRIMARY KEY,
            session_id text NOT NULL,
            time_created integer NOT NULL,
            data text NOT NULL
        );
        CREATE TABLE part (
            id text PRIMARY KEY,
            message_id text NOT NULL,
            session_id text NOT NULL,
            time_created integer NOT NULL,
            data text NOT NULL
        );
        """
    )
    connection.execute(
        "INSERT INTO session (id, time_updated) VALUES (?, ?)",
        (session_id, 1776302575996),
    )
    messages = [
        (
            "msg-user-1",
            1776302575000,
            {"role": "user"},
            "part-user-1",
            {"type": "text", "text": user_text},
        ),
        (
            "msg-assistant-1",
            1776302575996,
            {"role": "assistant"},
            "part-assistant-1",
            {"type": "text", "text": assistant_text},
        ),
    ]
    for message_id, timestamp, message_data, part_id, part_data in messages:
        connection.execute(
            "INSERT INTO message (id, session_id, time_created, data) VALUES (?, ?, ?, ?)",
            (message_id, session_id, timestamp, json.dumps(message_data)),
        )
        connection.execute(
            "INSERT INTO part (id, message_id, session_id, time_created, data) VALUES (?, ?, ?, ?, ?)",
            (part_id, message_id, session_id, timestamp, json.dumps(part_data)),
        )
    connection.commit()
    return connection


def _write_global_config(
    path: Path,
    *,
    provider_instances: list[dict[str, object]] | None = None,
    chatlas_instance_ids: list[str] | None | object = _DEFAULT_CHATLAS_INSTANCE_IDS,
) -> None:
    home = path.parent.parent / "home"
    configured_instances = [
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
    payload: dict[str, object] = {
        "class": "agentos.global.config",
        "schema_version": 1,
        "agent": {
            "instances": configured_instances,
        },
    }
    if chatlas_instance_ids is _DEFAULT_CHATLAS_INSTANCE_IDS:
        payload["chatlas"] = {
            "instance_ids": [
                instance_id
                for instance in configured_instances
                if isinstance((instance_id := instance.get("id")), str)
            ],
        }
    elif chatlas_instance_ids is not None:
        payload["chatlas"] = {
            "instance_ids": chatlas_instance_ids,
        }
    _write(
        path,
        json.dumps(payload),
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
    _write(home / ".codex" / "history.jsonl", '{"session_id":"019ccafa","ts":1,"text":"hello"}\n')
    _write(home / ".codex" / "AGENTS.md", "Say hello first.\n")
    _write(home / ".codex" / "rules" / "default.rules", 'prefix_rule(pattern=["git","commit"], decision="allow")\n')
    _write(home / ".codex" / "notes.md", "# notes\n")
    _write(home / ".codex" / "log" / "skip.txt", "skip\n")
    _write(home / ".codex" / "auth.json", '{"token":"secret"}\n')
    _write(home / ".codex" / "_auth-demo.json", '{"token":"secret"}\n')

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
    assert payload["instances"][0]["includes"] == [
        "sessions/**/*.jsonl",
        "archived_sessions/**/*.jsonl",
        "session_index.jsonl",
        "history.jsonl",
        "AGENTS.md",
        "rules/*.rules",
    ]
    assert payload["instances"][0]["excludes"] == [
        "log/",
        "vendor_imports/",
        "worktrees/",
        "shell_snapshots/",
        "models_cache.json",
        "sqlite/",
        "tmp/",
        "auth.json",
        "skills",
        "_auth*.json",
    ]
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
    assert (destination_root / "session_index.jsonl").exists()
    assert (destination_root / "history.jsonl").exists()
    assert (destination_root / "AGENTS.md").exists()
    assert (destination_root / "rules" / "default.rules").exists()
    assert not (destination_root / "notes.md").exists()
    assert not (destination_root / "log" / "skip.txt").exists()
    assert not (destination_root / "auth.json").exists()
    assert not (destination_root / "_auth-demo.json").exists()
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
        / "--Users-pereiro-projects-agentos-project-agentos-iterante-dev--"
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
        "cwd": "/Users/pereiro/projects/agentos-project/agentos-iterante-dev",
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


def test_chatlas_update_copilot_replaces_archived_instruction_symlink(
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
    _write_copilot_events(
        copilot_home / "session-state" / session_id / "events.jsonl",
        session_id=session_id,
    )
    instruction_target = tmp_path / "shared" / "copilot-instructions.md"
    _write(instruction_target, "Prefer concise answers.\n")
    (copilot_home / "copilot-instructions.md").symlink_to(instruction_target)

    assert main(_chatlas_update_argv("--provider", "copilot-cli")) == 0
    _ = json.loads(capsys.readouterr().out)

    chatlas_root = _default_chatlas_root(home)
    archived_instructions = _chatlas_home_root(home, copilot_home) / "copilot-instructions.md"
    assert archived_instructions.is_file()
    assert not archived_instructions.is_symlink()
    assert archived_instructions.read_text(encoding="utf-8") == "Prefer concise answers.\n"

    archived_instructions.unlink()
    archived_instructions.symlink_to(instruction_target)
    assert archived_instructions.is_symlink()
    _git_output(chatlas_root, "add", "-A")
    _git_output(
        chatlas_root,
        "-c",
        "user.name=agentos",
        "-c",
        "user.email=agentos@local.invalid",
        "commit",
        "-m",
        "simulate archived copilot instruction symlink",
    )

    assert main(_chatlas_update_argv("--provider", "copilot-cli")) == 0
    payload = json.loads(capsys.readouterr().out)
    home_status = payload["instances"][0]["homes_status"][0]

    assert payload["scan_cache_enabled"] is True
    assert payload["changes_detected"] is True
    assert payload["committed"] is True
    assert home_status["updated_file_count"] == 1
    assert archived_instructions.is_file()
    assert not archived_instructions.is_symlink()
    assert archived_instructions.read_text(encoding="utf-8") == "Prefer concise answers.\n"


def test_chatlas_update_claude_uses_raw_retention_whitelist(
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
    project_dir = claude_cli_home / "projects" / "-tmp-project"
    archive_dir = claude_cli_home / "archive" / "-"
    desktop_session_dir = (
        claude_desktop_home
        / "claude-code-sessions"
        / "workspace-a"
        / "conversation-b"
        / "session-c"
    )
    cli_session_id = "11111111-1111-4111-8111-111111111111"
    desktop_session_id = "22222222-2222-4222-8222-222222222222"

    _write_claude_session(
        project_dir / f"{cli_session_id}.jsonl",
        session_id=cli_session_id,
        user_text="retain claude cli user input",
        assistant_text="retain claude cli assistant output",
    )
    _write(project_dir / "sessions-index.json", '{"latest":"11111111"}\n')
    _write_claude_session(
        archive_dir / "archived-session.jsonl",
        session_id="33333333-3333-4333-8333-333333333333",
        user_text="retain claude archive user input",
        assistant_text="retain claude archive assistant output",
    )
    _write_claude_session(
        desktop_session_dir / "desktop-session.json",
        session_id=desktop_session_id,
        user_text="retain claude desktop user input",
        assistant_text="retain claude desktop assistant output",
    )
    _write(
        claude_cli_home / "usage-data" / "session-meta" / "meta-1.json",
        '{"session_id":"11111111","toolCallCount":4}\n',
    )
    _write(
        claude_cli_home / "usage-data" / "facets" / "facet-1.json",
        '{"session_id":"11111111","outcome":"achieved"}\n',
    )
    _write(
        claude_cli_home / "tasks" / "task-1" / "1.json",
        '{"id":"1","subject":"retain task planning"}\n',
    )
    _write(
        claude_cli_home / "todos" / "todo-1.json",
        '[{"content":"retain todo context","status":"completed"}]\n',
    )
    _write(claude_cli_home / "settings.json", '{"model":"opus"}\n')
    _write(claude_cli_home / "CLAUDE.md", "Local behavioral guidance\n")

    _write(
        claude_cli_home / "file-history" / "file-1" / "snapshot@v1",
        "workspace copy\n",
    )
    _write(
        claude_cli_home / "backups" / ".claude.json.backup.1",
        '{"numStartups":1}\n',
    )
    _write(
        claude_cli_home / "history.jsonl",
        '{"display":"should be excluded","sessionId":"11111111"}\n',
    )
    _write(claude_cli_home / "sessions" / "123.json", '{"pid":123}\n')
    _write(claude_cli_home / "debug" / "session.txt", "debug noise\n")
    _write(claude_cli_home / "telemetry" / "event.json", '{"kind":"analytics"}\n')
    _write(claude_cli_home / "tasks" / "task-1" / ".lock", "")
    _write(claude_cli_home / "tasks" / "task-1" / ".highwatermark", "")
    _write(claude_cli_home / "mcp-needs-auth-cache.json", '{"gmail":{"timestamp":1}}\n')
    _write(claude_cli_home / "plugins" / "installed_plugins.json", "[]\n")
    _write(claude_cli_home / "hooks" / "random-sound.sh", "#!/bin/sh\n")
    _write(claude_cli_home / "statusline", "#!/bin/sh\n")
    _write(claude_cli_home / "statusline.dump", "dump\n")
    _write(claude_cli_home / ".example-claude-statusline.json", '{"demo":true}\n')
    _write(claude_cli_home / "stats-cache.json", '{"dailyActivity":[]}\n')

    _write(
        claude_desktop_home / "config.json",
        '{"oauth:tokenCache":"secret","locale":"en-US"}\n',
    )
    _write(claude_desktop_home / "claude_desktop_config.json", "{}\n")
    _write(claude_desktop_home / "git-worktrees.json", "[]\n")
    _write(claude_desktop_home / "extensions-blocklist.json", "[]\n")
    _write(claude_desktop_home / "window-state.json", "{}\n")
    _write(claude_desktop_home / "Cache" / "cache.bin", "noise\n")
    _write(claude_desktop_home / "vm_bundles" / "vm" / "rootfs.img", "vm\n")

    assert main(_chatlas_update_argv("--provider", "claude-code")) == 0
    payload = json.loads(capsys.readouterr().out)

    chatlas_root = _default_chatlas_root(home)
    destination_cli_root = _chatlas_home_root(home, claude_cli_home)
    destination_desktop_root = _chatlas_home_root(home, claude_desktop_home)
    instance_payload = payload["instances"][0]
    expected_includes = [
        "projects/**/*.jsonl",
        "projects/**/sessions-index.json",
        "archive/**/*.jsonl",
        "usage-data/session-meta/*.json",
        "usage-data/facets/*.json",
        "tasks/**/[0-9]*.json",
        "todos/*.json",
        "settings.json",
        "CLAUDE.md",
        "claude-code-sessions/**/*.json",
    ]
    expected_excludes = [
        "debug/",
        "telemetry/",
        "cache/",
        "Cache/",
        "Code Cache/",
        "Cookies",
        "Cookies-journal",
        "Crashpad/",
        "DIPS",
        "DawnGraphiteCache/",
        "DawnWebGPUCache/",
        "GPUCache/",
        "Local Storage/",
        "Network Persistent State",
        "Preferences",
        "Session Storage/",
        "Shared Dictionary/",
        "SharedStorage",
        "TransportSecurity",
        "Trust Tokens",
        "Trust Tokens-journal",
        "WebStorage/",
        "ant-did",
        "blob_storage/",
        "claude-code/",
        "claude-code-vm/",
        "statsig/",
        "sentry/",
        "shell-snapshots/",
        "paste-cache/",
        "session-env/",
        "downloads/",
        "ide/",
        "plugins/",
        "skills",
        "vm_bundles/",
        "file-history/",
        "backups/",
        "history.jsonl",
        "sessions/",
        "tasks/**/*.lock",
        "tasks/**/.highwatermark",
        "mcp-needs-auth-cache.json",
        "hooks/",
        "statusline",
        "statusline.dump",
        ".example-claude-statusline.json",
        "stats-cache.json",
        "config.json",
        "claude_desktop_config.json",
        "git-worktrees.json",
        "extensions-blocklist.json",
        "window-state.json",
    ]

    assert payload["command"] == "chatlas update"
    assert payload["committed"] is True
    assert payload["changes_detected"] is True
    assert payload["synced_instance_count"] == 1
    assert payload["normalized_session_count"] == 1
    assert payload["derived_transcript_session_count"] == 1
    assert instance_payload["instance"] == "claude-main"
    assert instance_payload["destination_root"] is None
    assert instance_payload["destination_roots"] == {
        "cli": str(destination_cli_root),
        "desktop": str(destination_desktop_root),
    }
    assert instance_payload["includes"] == expected_includes
    assert instance_payload["excludes"] == expected_excludes

    assert (destination_cli_root / "projects" / "-tmp-project" / f"{cli_session_id}.jsonl").is_file()
    assert (destination_cli_root / "projects" / "-tmp-project" / "sessions-index.json").is_file()
    assert (destination_cli_root / "archive" / "-" / "archived-session.jsonl").is_file()
    assert (destination_cli_root / "usage-data" / "session-meta" / "meta-1.json").is_file()
    assert (destination_cli_root / "usage-data" / "facets" / "facet-1.json").is_file()
    assert (destination_cli_root / "tasks" / "task-1" / "1.json").is_file()
    assert (destination_cli_root / "todos" / "todo-1.json").is_file()
    assert (destination_cli_root / "settings.json").is_file()
    assert (destination_cli_root / "CLAUDE.md").is_file()
    assert (
        destination_desktop_root
        / "claude-code-sessions"
        / "workspace-a"
        / "conversation-b"
        / "session-c"
        / "desktop-session.json"
    ).is_file()

    assert not (destination_cli_root / "file-history").exists()
    assert not (destination_cli_root / "backups").exists()
    assert not (destination_cli_root / "history.jsonl").exists()
    assert not (destination_cli_root / "sessions").exists()
    assert not (destination_cli_root / "debug").exists()
    assert not (destination_cli_root / "telemetry").exists()
    assert not (destination_cli_root / "tasks" / "task-1" / ".lock").exists()
    assert not (destination_cli_root / "tasks" / "task-1" / ".highwatermark").exists()
    assert not (destination_cli_root / "mcp-needs-auth-cache.json").exists()
    assert not (destination_cli_root / "plugins").exists()
    assert not (destination_cli_root / "hooks").exists()
    assert not (destination_cli_root / "statusline").exists()
    assert not (destination_cli_root / "statusline.dump").exists()
    assert not (destination_cli_root / ".example-claude-statusline.json").exists()
    assert not (destination_cli_root / "stats-cache.json").exists()
    assert not (destination_desktop_root / "config.json").exists()
    assert not (destination_desktop_root / "claude_desktop_config.json").exists()
    assert not (destination_desktop_root / "git-worktrees.json").exists()
    assert not (destination_desktop_root / "extensions-blocklist.json").exists()
    assert not (destination_desktop_root / "window-state.json").exists()
    assert not (destination_desktop_root / "Cache").exists()
    assert not (destination_desktop_root / "vm_bundles").exists()

    normalized_rows = [
        json.loads(line)
        for line in Path(payload["normalized_sessions_path"])
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    normalized_by_session_id = {row["session_id"]: row for row in normalized_rows}
    assert sorted(normalized_by_session_id) == [cli_session_id]
    assert normalized_by_session_id[cli_session_id]["provider"] == "claude-code"
    assert normalized_by_session_id[cli_session_id]["instance"] == "claude-main"

    cli_transcript_path = (
        chatlas_root
        / "derived"
        / "transcripts"
        / "claude-code"
        / normalized_by_session_id[cli_session_id]["provider_instance_fingerprint"]
        / f"{cli_session_id}.md"
    )
    assert "retain claude cli user input" in cli_transcript_path.read_text(encoding="utf-8")
    assert "retain claude cli assistant output" in cli_transcript_path.read_text(encoding="utf-8")


def test_chatlas_update_opencode_uses_raw_retention_policy(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    opencode_home = home / ".local" / "share" / "opencode"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "opencode",
                "id": "opencode-main",
                "home": str(opencode_home),
            }
        ],
    )

    session_id = "ses_3388ec792ffegkjQiBxLCMs3MX"
    db_connection = _write_opencode_db(
        opencode_home / "opencode.db",
        session_id=session_id,
        user_text="retain opencode user input",
        assistant_text="retain opencode assistant output",
        keep_wal=True,
    )
    _write(
        opencode_home / "storage" / "session_diff" / f"{session_id}.json",
        json.dumps(
            [
                {
                    "file": "app.py",
                    "before": "",
                    "after": "print('hello')\n",
                    "additions": 1,
                    "deletions": 0,
                    "status": "added",
                }
            ]
        )
        + "\n",
    )
    _write(opencode_home / "tool-output" / "tool_123", "tool result\n")

    _write(
        opencode_home / "auth.json",
        json.dumps(
            {
                "github-copilot": {
                    "access": "secret-access",
                    "refresh": "secret-refresh",
                }
            }
        )
        + "\n",
    )
    _write(opencode_home / "log" / "2026-04-20T000000.log", "runtime token noise\n")
    _write(opencode_home / "snapshot" / "global" / "objects" / "aa" / "bb", "workspace copy\n")
    _write(opencode_home / "storage" / "migration", "1")
    _write(opencode_home / "bin" / "opencode", "runtime binary\n")

    try:
        assert (opencode_home / "opencode.db-wal").is_file()
        assert (opencode_home / "opencode.db-shm").is_file()
        assert main(_chatlas_update_argv("--provider", "opencode")) == 0
    finally:
        db_connection.close()

    payload = json.loads(capsys.readouterr().out)
    chatlas_root = _default_chatlas_root(home)
    destination_root = _chatlas_home_root(home, opencode_home)
    instance_payload = payload["instances"][0]
    expected_includes = [
        "opencode.db",
        "opencode.db-wal",
        "storage/session_diff/*.json",
        "tool-output/tool_*",
    ]
    expected_excludes = [
        "auth.json",
        "log/",
        "snapshot/",
        "opencode.db-shm",
        "storage/migration",
        "bin/",
    ]

    assert payload["command"] == "chatlas update"
    assert payload["committed"] is True
    assert payload["changes_detected"] is True
    assert payload["synced_instance_count"] == 1
    assert payload["normalized_session_count"] == 1
    assert payload["derived_transcript_session_count"] == 1
    assert instance_payload["instance"] == "opencode-main"
    assert instance_payload["destination_root"] == str(destination_root)
    assert instance_payload["includes"] == expected_includes
    assert instance_payload["excludes"] == expected_excludes

    assert (destination_root / "opencode.db").is_file()
    assert (destination_root / "opencode.db-wal").is_file()
    assert (destination_root / "storage" / "session_diff" / f"{session_id}.json").is_file()
    assert (destination_root / "tool-output" / "tool_123").is_file()
    assert not (destination_root / "auth.json").exists()
    assert not (destination_root / "log").exists()
    assert not (destination_root / "snapshot").exists()
    assert not (destination_root / "opencode.db-shm").exists()
    assert not (destination_root / "storage" / "migration").exists()
    assert not (destination_root / "bin" / "opencode").exists()

    normalized_rows = [
        json.loads(line)
        for line in Path(payload["normalized_sessions_path"])
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert len(normalized_rows) == 1
    normalized_row = normalized_rows[0]
    assert normalized_row["provider"] == "opencode"
    assert normalized_row["instance"] == "opencode-main"
    assert normalized_row["session_id"] == session_id

    derived_md_path = (
        chatlas_root
        / "derived"
        / "transcripts"
        / "opencode"
        / normalized_row["provider_instance_fingerprint"]
        / f"{session_id}.md"
    )
    transcript_markdown = derived_md_path.read_text(encoding="utf-8")
    assert "retain opencode user input" in transcript_markdown
    assert "retain opencode assistant output" in transcript_markdown


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

    def fail_source_hash(*args, **kwargs):
        raise AssertionError("expected transcript cache to reuse normalized source metadata")

    monkeypatch.setattr(chatlas_raw, "_chatlas_archive_files_match", fail_match)
    monkeypatch.setattr(chatlas_core, "_normalized_session_record", fail_normalized_record)
    monkeypatch.setattr(chatlas_core, "_render_transcript", fail_render)
    monkeypatch.setattr(chatlas_core, "_chatlas_cache_path_signature", fail_source_hash)

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["scan_cache_enabled"] is True
    assert payload["normalized_cache_enabled"] is True
    assert payload["transcript_cache_enabled"] is True
    assert payload["changes_detected"] is False
    assert payload["committed"] is False
    assert _git_output(chatlas_root, "status", "--porcelain") == ""


def test_chatlas_derived_transcript_cache_matches_legacy_rich_signatures() -> None:
    from agentos.chatlas import core as chatlas_core

    source_signature = {
        "source_path": "/tmp/chatlas/session/events.jsonl",
        "size": 256,
        "mtime_ns": 42,
        "signature_version": 2,
        "derivation_version": chatlas_core._DERIVED_TRANSCRIPT_DERIVATION_VERSION,
    }
    legacy_cache_entry = {
        "source_path": "/tmp/chatlas/session/events.jsonl",
        "size": 256,
        "mtime_ns": 42,
        "tail_sha256": "legacy-rich-tail-hash",
        "derivation_version": chatlas_core._DERIVED_TRANSCRIPT_DERIVATION_VERSION,
    }

    assert chatlas_core._derived_transcript_cache_entry_matches(
        legacy_cache_entry,
        source_signature,
    )


@pytest.mark.parametrize(
    "cache_flag, expected_scan, expected_normalized, expected_transcript, patched_targets",
    [
        pytest.param(
            "--scan-cache=false",
            False, True, True,
            ("raw._chatlas_archive_files_match",),
            id="scan",
        ),
        pytest.param(
            "--transcript-cache=false",
            True, True, False,
            ("core._render_transcript",),
            id="transcript",
        ),
        pytest.param(
            "--normalized-cache=false",
            True, False, True,
            ("core._normalized_session_record",),
            id="normalized",
        ),
        pytest.param(
            "--disable-cache",
            False, False, False,
            ("raw._chatlas_archive_files_match", "core._normalized_session_record", "core._render_transcript"),
            id="disable-all",
        ),
    ],
)
def test_chatlas_update_can_disable_caches(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
    cache_flag: str,
    expected_scan: bool,
    expected_normalized: bool,
    expected_transcript: bool,
    patched_targets: tuple[str, ...],
) -> None:
    from agentos.chatlas import core as chatlas_core
    from agentos.chatlas import raw as chatlas_raw

    modules = {"raw": chatlas_raw, "core": chatlas_core}

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
        thread_name="cache-disable-thread",
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    counters: dict[str, int] = {}
    for target in patched_targets:
        mod_key, attr = target.split(".")
        mod = modules[mod_key]
        original = getattr(mod, attr)
        counters[target] = 0

        def make_counter(orig, key):
            def counting(*args, **kwargs):
                counters[key] += 1
                return orig(*args, **kwargs)
            return counting

        monkeypatch.setattr(mod, attr, make_counter(original, target))

    extra_argv = ["--provider", "codex", cache_flag]
    if cache_flag == "--disable-cache":
        extra_argv += ["--scan-cache=true", "--normalized-cache=true", "--transcript-cache=true"]

    assert main(_chatlas_update_argv(*extra_argv)) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["scan_cache_enabled"] is expected_scan
    assert payload["normalized_cache_enabled"] is expected_normalized
    assert payload["transcript_cache_enabled"] is expected_transcript
    assert payload["changes_detected"] is False
    assert payload["committed"] is False
    for target in patched_targets:
        assert counters[target] > 0, f"expected {target} to be called"


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
    assert home_status["skipped_file_count"] == 0
    assert home_status["skipped_file_examples"] == []


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


def test_chatlas_update_respects_chatlas_instance_selection(
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
        chatlas_instance_ids=["jp"],
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["instance_count"] == 1
    assert payload["synced_instance_count"] == 1
    assert payload["normalized_session_count"] == 1
    assert [instance["instance"] for instance in payload["instances"]] == ["jp"]
    assert not _chatlas_home_root(home, home / ".codex").exists()
    assert (
        _chatlas_home_root(home, extra_codex_home)
        / "sessions"
        / "2026"
        / "03"
        / "26"
        / f"rollout-2026-03-26T01-05-38-{extra_session_id}.jsonl"
    ).exists()


@pytest.mark.parametrize(
    "chatlas_instance_ids",
    [
        pytest.param(None, id="missing-selector"),
        pytest.param([], id="empty-selector"),
    ],
)
def test_chatlas_update_requires_explicit_chatlas_instance_selection(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
    chatlas_instance_ids: list[str] | None,
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(
        agentos_home / "config.json",
        chatlas_instance_ids=chatlas_instance_ids,
    )

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["instance_count"] == 0
    assert payload["synced_instance_count"] == 0
    assert payload["skipped_instance_count"] == 0
    assert payload["normalized_session_count"] == 0
    assert payload["instances"] == []
    assert not _chatlas_home_root(home, home / ".codex").exists()


def test_chatlas_update_without_selection_preserves_existing_dataset(
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
    first_payload = json.loads(capsys.readouterr().out)
    assert first_payload["normalized_session_count"] == 1

    _write_global_config(agentos_home / "config.json", chatlas_instance_ids=None)

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["instance_count"] == 0
    assert payload["normalized_session_count"] == 1
    assert payload["derived_transcript_session_count"] == 1
    assert payload["changes_detected"] is False
    assert payload["committed"] is False
    assert _chatlas_home_root(home, home / ".codex").exists()


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
    assert not (destination_cli_root / "README.md").exists()
    assert not (destination_desktop_root / "desktop-state.json").exists()
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


def test_chatlas_experimental_export_emits_session_model_json(
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
    thread_name = "experimental-export-thread"
    rollout_path = home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    _write_codex_dialog_rollout(
        rollout_path,
        session_id=session_id,
        user_text="experimental export user",
        assistant_text="experimental export assistant",
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "experimental", "export", thread_name, "--provider", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["class"] == "agentos.chatlas.experimental.session_model"
    assert payload["schema_version"] == 1
    assert payload["experimental"] is True
    assert payload["session"]["provider"] == "codex"
    assert payload["session"]["session_id"] == session_id
    assert payload["session"]["display_name"] == thread_name
    assert payload["agent_instance"]["provider_family"] == "codex"
    assert (
        payload["agent_instance"]["provider_instance_fingerprint"]
        == payload["session"]["provider_instance_fingerprint"]
    )
    assert any(source["role"] == "transcript" for source in payload["sources"])
    assert payload["chat"]["model_runs"] == []
    assert payload["chat"]["tool_invocations"] == []
    assert payload["chat"]["events"] == []
    assert payload["chat"]["usage"] == []
    assert [message["role"] for message in payload["chat"]["messages"]] == ["user", "assistant"]
    assert payload["chat"]["messages"][0]["content"] == [
        {
            "type": "text",
            "text": "experimental export user<system-reminder>\nmetadata tail",
            "origin": "input",
        }
    ]
    assert payload["chat"]["messages"][1]["content"] == [
        {
            "type": "text",
            "text": "experimental export assistant",
            "origin": "output",
        }
    ]
    assert payload["chat"]["messages"][0]["visibility"] == "conversation"
    assert payload["chat"]["messages"][0]["native"]["content_types"] == ["input_text"]
    assert payload["chat"]["messages"][1]["native"]["content_types"] == ["output_text"]
    assert payload["chat"]["messages"][0]["source_refs"] == [
        {"source_ref_id": "source-1", "record_index": 2, "line": 2}
    ]
    assert payload["normalization"]["normalizer"] == "codex.raw_rollout.experimental.v1"
    assert payload["normalization"]["source_mode"] == "codex_raw_rollout"
    assert (
        "codex raw rollout parsed for future normalization: 3 records"
        in payload["normalization"]["warnings"]
    )
    assert (
        "codex raw rollout messages normalized from response_item.message: 2 messages"
        in payload["normalization"]["warnings"]
    )
    assert "messages" not in payload["normalization"]["unsupported_concepts"]
    assert "model_runs" in payload["normalization"]["unsupported_concepts"]


def test_chatlas_experimental_export_loads_claude_raw_session(
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

    session_id = "5dbf4437-633e-4039-a627-0459d85e9ecc"
    _write_claude_session(
        home / ".claude" / "projects" / "-tmp-project" / f"{session_id}.jsonl",
        session_id=session_id,
        user_text="claude experimental user",
        assistant_text="claude experimental assistant",
    )

    assert main(_chatlas_update_argv("--provider", "claude-code")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert (
        main(
            [
                "chatlas",
                "experimental",
                "export",
                session_id,
                "--provider",
                "claude-code",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["session"]["provider"] == "claude-code"
    assert payload["normalization"]["normalizer"] == "claude-code.raw_session.experimental.v1"
    assert payload["normalization"]["source_mode"] == "claude_code_raw_session"
    assert payload["chat"]["messages"] == [
        {
            "message_id": "message-1",
            "role": "user",
            "visibility": "conversation",
            "content": [{"type": "text", "text": "claude experimental user"}],
            "native": {
                "record_index": 1,
                "line": 1,
                "record_type": "message",
                "uuid": "msg-user-1",
                "message_role": "user",
                "role": "user",
                "content_types": ["string"],
            },
            "timestamp": "2026-04-18T11:00:00.000Z",
            "source_refs": [{"source_ref_id": "source-1", "record_index": 1, "line": 1}],
        },
        {
            "message_id": "message-2",
            "role": "assistant",
            "visibility": "conversation",
            "content": [
                {"type": "text", "text": "claude experimental assistant"},
                {"type": "text", "text": "tool summary"},
            ],
            "native": {
                "record_index": 2,
                "line": 2,
                "record_type": "message",
                "uuid": "msg-assistant-1",
                "parent_uuid": "msg-user-1",
                "message_role": "assistant",
                "role": "assistant",
                "content_types": ["text", "text"],
            },
            "timestamp": "2026-04-18T11:00:01.000Z",
            "source_refs": [{"source_ref_id": "source-1", "record_index": 2, "line": 2}],
        },
    ]
    assert payload["chat"]["model_runs"] == []
    assert payload["chat"]["tool_invocations"] == []
    assert payload["chat"]["events"] == [
        {
            "event_id": "event-1",
            "type": "claude-code.user.message",
            "data": {
                "message": {
                    "role": "user",
                    "content": "claude experimental user",
                },
                "session_id": session_id,
                "cwd": "/tmp/project",
                "version": "2.1.69",
                "is_sidechain": False,
                "user_type": "external",
            },
            "native": {
                "record_index": 1,
                "line": 1,
                "record_type": "message",
                "uuid": "msg-user-1",
                "message_role": "user",
            },
            "timestamp": "2026-04-18T11:00:00.000Z",
            "source_refs": [{"source_ref_id": "source-1", "record_index": 1, "line": 1}],
        },
        {
            "event_id": "event-2",
            "type": "claude-code.assistant.message",
            "data": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "claude experimental assistant"},
                        {"type": "text", "text": "tool summary"},
                    ],
                },
                "session_id": session_id,
                "cwd": "/tmp/project",
                "version": "2.1.69",
                "is_sidechain": False,
                "user_type": "external",
            },
            "native": {
                "record_index": 2,
                "line": 2,
                "record_type": "message",
                "uuid": "msg-assistant-1",
                "parent_uuid": "msg-user-1",
                "message_role": "assistant",
            },
            "timestamp": "2026-04-18T11:00:01.000Z",
            "source_refs": [{"source_ref_id": "source-1", "record_index": 2, "line": 2}],
            "parent_uuid": "msg-user-1",
        },
    ]
    assert payload["chat"]["usage"] == []
    assert payload["normalization"]["unsupported_concepts"] == []
    assert payload["normalization"]["deferred_concepts"] == []
    assert payload["normalization"]["counts"] == {
        "messages": 2,
        "model_runs": 0,
        "tool_invocations": 0,
        "events": 2,
        "usage": 0,
        "reasoning_traces": 0,
    }
    assert payload["normalization"]["raw_counts"] == {
        "records": 2,
        "record_types": {
            "assistant": 1,
            "user": 1,
        },
        "parse_warning_count": 0,
        "visible_message_record_count": 2,
        "tool_use_count": 0,
        "tool_result_count": 0,
        "progress_count": 0,
        "reasoning_evidence_count": 0,
        "usage_evidence_count": 0,
        "distinct_request_count": 0,
    }
    assert payload["normalization"]["coverage"] == {
        "messages": {
            "status": "normalized",
            "raw_visible_message_record_count": 2,
            "normalized_count": 2,
        },
        "model_runs": {
            "status": "missing",
            "raw_request_count": 0,
            "normalized_count": 0,
        },
        "tool_invocations": {
            "status": "missing",
            "raw_tool_use_count": 0,
            "raw_tool_result_count": 0,
            "normalized_count": 0,
        },
        "events": {
            "status": "normalized",
            "raw_record_count": 2,
            "raw_canonical_candidate_count": 2,
            "raw_progress_count": 0,
            "normalized_count": 2,
        },
        "reasoning": {
            "status": "missing",
            "raw_evidence_count": 0,
            "normalized_count": 0,
        },
        "usage": {
            "status": "missing",
            "raw_evidence_count": 0,
            "normalized_count": 0,
        },
    }
    assert (
        "claude raw session parsed for future normalization: 2 records"
        in payload["normalization"]["warnings"]
    )
    assert (
        "claude raw session messages normalized from visible message records: 2 messages"
        in payload["normalization"]["warnings"]
    )
    assert (
        "claude raw session events normalized from raw records: 2 events"
        in payload["normalization"]["warnings"]
    )
    assert (
        "claude raw session normalization covers messages, events, tool invocations, model runs, reasoning, and usage"
        in payload["normalization"]["warnings"]
    )


def test_chatlas_experimental_export_normalizes_claude_tool_invocations(
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

    session_id = "5dbf4437-633e-4039-a627-0459d85e9ecc"
    _write_claude_session(
        home / ".claude" / "projects" / "-tmp-project" / f"{session_id}.jsonl",
        session_id=session_id,
        user_text="claude experimental user",
        assistant_text="claude experimental assistant",
        include_tool_roundtrip=True,
    )

    assert main(_chatlas_update_argv("--provider", "claude-code")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert (
        main(
            [
                "chatlas",
                "experimental",
                "export",
                session_id,
                "--provider",
                "claude-code",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert len(payload["chat"]["messages"]) == 2
    assert payload["chat"]["model_runs"] == [
        {
            "model_run_id": "model-run-1",
            "provider": "claude-code",
            "status": "completed",
            "native": {
                "request_record_count": 1,
                "assistant_record_indices": [3],
                "first_request_record_index": 3,
                "last_request_record_index": 3,
                "span_start_record_index": 1,
                "span_end_record_index": 6,
                "assistant_message_ids": ["msg-tool-assistant-1"],
                "stop_reason": "tool_use",
            },
            "request_id": "req-claude-1",
            "model": "claude-opus-4-6",
            "started_at": "2026-04-18T11:00:02.000Z",
            "ended_at": "2026-04-18T11:00:02.500Z",
            "source_refs": [
                {"source_ref_id": "source-1", "record_index": 3, "line": 3},
                {"source_ref_id": "source-1", "record_index": 6, "line": 6},
            ],
            "message_refs": ["message-1", "message-2"],
            "tool_invocation_refs": ["tool-invocation-1"],
            "event_refs": [
                "event-1",
                "event-2",
                "event-3",
                "event-4",
                "event-5",
                "event-6",
            ],
        }
    ]
    assert payload["chat"]["tool_invocations"] == [
        {
            "tool_invocation_id": "tool-invocation-1",
            "call_id": "toolu-claude-1",
            "tool_name": "Bash",
            "status": "completed",
            "native": {
                "request_present": True,
                "result_present": True,
                "pre_progress_present": True,
                "post_progress_present": True,
                "record_indices": {
                    "tool_use": [{"record_index": 3, "content_index": 1}],
                    "tool_result": [{"record_index": 5, "content_index": 1}],
                    "progress.pre": [4],
                    "progress.post": [6],
                },
                "tool_use": {
                    "type": "tool_use",
                    "id": "toolu-claude-1",
                    "name": "Bash",
                    "input": {
                        "command": "ls /tmp/project",
                        "description": "List project",
                    },
                    "caller": {"type": "direct"},
                },
                "tool_result": {
                    "tool_use_id": "toolu-claude-1",
                    "type": "tool_result",
                    "content": "AGENTS.md\nsrc\ntests",
                    "is_error": False,
                },
                "tool_use_result": {
                    "stdout": "AGENTS.md\nsrc\ntests",
                    "stderr": "",
                    "interrupted": False,
                    "isImage": False,
                    "noOutputExpected": False,
                },
                "source_tool_assistant_uuid": "msg-assistant-tool-1",
                "progress_pre": {
                    "type": "hook_progress",
                    "hookEvent": "PreToolUse",
                    "hookName": "PreToolUse:Bash",
                    "command": "bash -x ~/.claude/hooks/random-sound.sh&",
                },
                "progress_post": {
                    "type": "hook_progress",
                    "hookEvent": "PostToolUse",
                    "hookName": "PostToolUse:Bash",
                    "command": "bash -x ~/.claude/hooks/random-sound.sh&",
                },
            },
            "started_at": "2026-04-18T11:00:02.000Z",
            "ended_at": "2026-04-18T11:00:02.500Z",
            "input": {
                "arguments": {
                    "command": "ls /tmp/project",
                    "description": "List project",
                }
            },
            "output": {"content": "AGENTS.md\nsrc\ntests"},
            "execution": {
                "stdout": "AGENTS.md\nsrc\ntests",
                "stderr": "",
                "interrupted": False,
                "is_image": False,
                "no_output_expected": False,
            },
            "model": "claude-opus-4-6",
            "request_id": "req-claude-1",
            "message_id": "msg-tool-assistant-1",
            "source_refs": [
                {"source_ref_id": "source-1", "record_index": 3, "line": 3, "content_index": 1},
                {"source_ref_id": "source-1", "record_index": 4, "line": 4},
                {"source_ref_id": "source-1", "record_index": 5, "line": 5, "content_index": 1},
                {"source_ref_id": "source-1", "record_index": 6, "line": 6},
            ],
            "event_refs": ["event-3", "event-4", "event-5", "event-6"],
        }
    ]
    assert [event.get("tool_invocation_ref") for event in payload["chat"]["events"]] == [
        None,
        None,
        "tool-invocation-1",
        "tool-invocation-1",
        "tool-invocation-1",
        "tool-invocation-1",
    ]
    assert [event.get("model_run_ref") for event in payload["chat"]["events"]] == [
        "model-run-1",
        "model-run-1",
        "model-run-1",
        "model-run-1",
        "model-run-1",
        "model-run-1",
    ]
    assert payload["normalization"]["unsupported_concepts"] == []
    assert payload["normalization"]["deferred_concepts"] == []
    assert payload["normalization"]["counts"] == {
        "messages": 2,
        "model_runs": 1,
        "tool_invocations": 1,
        "events": 6,
        "usage": 0,
        "reasoning_traces": 0,
    }
    assert payload["normalization"]["raw_counts"] == {
        "records": 6,
        "record_types": {
            "assistant": 2,
            "progress": 2,
            "user": 2,
        },
        "parse_warning_count": 0,
        "visible_message_record_count": 2,
        "tool_use_count": 1,
        "tool_result_count": 1,
        "progress_count": 2,
        "reasoning_evidence_count": 0,
        "usage_evidence_count": 0,
        "distinct_request_count": 1,
    }
    assert payload["normalization"]["coverage"] == {
        "messages": {
            "status": "normalized",
            "raw_visible_message_record_count": 2,
            "normalized_count": 2,
        },
        "model_runs": {
            "status": "normalized",
            "raw_request_count": 1,
            "normalized_count": 1,
        },
        "tool_invocations": {
            "status": "normalized",
            "raw_tool_use_count": 1,
            "raw_tool_result_count": 1,
            "normalized_count": 1,
        },
        "events": {
            "status": "normalized",
            "raw_record_count": 6,
            "raw_canonical_candidate_count": 6,
            "raw_progress_count": 2,
            "normalized_count": 6,
        },
        "reasoning": {
            "status": "missing",
            "raw_evidence_count": 0,
            "normalized_count": 0,
        },
        "usage": {
            "status": "missing",
            "raw_evidence_count": 0,
            "normalized_count": 0,
        },
    }
    assert (
        "claude raw session tool invocations normalized by tool_use.id: 1 invocations"
        in payload["normalization"]["warnings"]
    )
    assert (
        "claude raw session model runs normalized by requestId: 1 runs"
        in payload["normalization"]["warnings"]
    )
    assert not any(
        "missing assistant tool_use record" in warning
        or "missing user tool_result record" in warning
        or "missing PreToolUse progress record" in warning
        or "missing PostToolUse progress record" in warning
        for warning in payload["normalization"]["warnings"]
    )


def test_chatlas_experimental_export_normalizes_claude_model_runs(
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

    session_id = "5dbf4437-633e-4039-a627-0459d85e9ecc"
    _write_claude_session(
        home / ".claude" / "projects" / "-tmp-project" / f"{session_id}.jsonl",
        session_id=session_id,
        user_text="claude experimental user",
        assistant_text="claude experimental assistant",
        include_tool_roundtrip=True,
        include_followup_reply=True,
    )

    assert main(_chatlas_update_argv("--provider", "claude-code")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert (
        main(
            [
                "chatlas",
                "experimental",
                "export",
                session_id,
                "--provider",
                "claude-code",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["normalization"]["counts"] == {
        "messages": 3,
        "model_runs": 2,
        "tool_invocations": 1,
        "events": 7,
        "usage": 0,
        "reasoning_traces": 0,
    }
    assert payload["normalization"]["raw_counts"]["distinct_request_count"] == 2
    assert payload["normalization"]["coverage"]["model_runs"] == {
        "status": "normalized",
        "raw_request_count": 2,
        "normalized_count": 2,
    }
    assert payload["normalization"]["unsupported_concepts"] == []
    assert payload["normalization"]["deferred_concepts"] == []

    assert payload["chat"]["model_runs"] == [
        {
            "model_run_id": "model-run-1",
            "provider": "claude-code",
            "status": "completed",
            "native": {
                "request_record_count": 2,
                "assistant_record_indices": [2, 3],
                "first_request_record_index": 2,
                "last_request_record_index": 3,
                "span_start_record_index": 1,
                "span_end_record_index": 6,
                "assistant_message_ids": ["msg-tool-assistant-1"],
                "stop_reason": "tool_use",
            },
            "request_id": "req-claude-1",
            "model": "claude-opus-4-6",
            "started_at": "2026-04-18T11:00:01.000Z",
            "ended_at": "2026-04-18T11:00:02.500Z",
            "source_refs": [
                {"source_ref_id": "source-1", "record_index": 2, "line": 2},
                {"source_ref_id": "source-1", "record_index": 6, "line": 6},
            ],
            "message_refs": ["message-1", "message-2"],
            "tool_invocation_refs": ["tool-invocation-1"],
            "event_refs": [
                "event-1",
                "event-2",
                "event-3",
                "event-4",
                "event-5",
                "event-6",
            ],
        },
        {
            "model_run_id": "model-run-2",
            "provider": "claude-code",
            "status": "completed",
            "native": {
                "request_record_count": 1,
                "assistant_record_indices": [7],
                "first_request_record_index": 7,
                "last_request_record_index": 7,
                "span_start_record_index": 7,
                "span_end_record_index": 7,
                "assistant_message_ids": ["msg-assistant-final-1"],
                "stop_reason": "end_turn",
            },
            "request_id": "req-claude-2",
            "model": "claude-opus-4-6",
            "started_at": "2026-04-18T11:00:02.800Z",
            "ended_at": "2026-04-18T11:00:02.800Z",
            "source_refs": [
                {"source_ref_id": "source-1", "record_index": 7, "line": 7}
            ],
            "message_refs": ["message-3"],
            "event_refs": ["event-7"],
        },
    ]
    assert [event.get("model_run_ref") for event in payload["chat"]["events"]] == [
        "model-run-1",
        "model-run-1",
        "model-run-1",
        "model-run-1",
        "model-run-1",
        "model-run-1",
        "model-run-2",
    ]
    assert (
        "claude raw session model runs normalized by requestId: 2 runs"
        in payload["normalization"]["warnings"]
    )


def test_chatlas_experimental_export_normalizes_claude_reasoning_and_usage(
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

    session_id = "5dbf4437-633e-4039-a627-0459d85e9ecc"
    _write_claude_session(
        home / ".claude" / "projects" / "-tmp-project" / f"{session_id}.jsonl",
        session_id=session_id,
        user_text="claude experimental user",
        assistant_text="claude experimental assistant",
        include_tool_roundtrip=True,
        include_followup_reply=True,
        include_reasoning_usage=True,
    )

    assert main(_chatlas_update_argv("--provider", "claude-code")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert (
        main(
            [
                "chatlas",
                "experimental",
                "export",
                session_id,
                "--provider",
                "claude-code",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["normalization"]["unsupported_concepts"] == []
    assert payload["normalization"]["deferred_concepts"] == []
    assert payload["normalization"]["counts"] == {
        "messages": 3,
        "model_runs": 2,
        "tool_invocations": 1,
        "events": 7,
        "usage": 2,
        "reasoning_traces": 1,
    }
    assert payload["normalization"]["raw_counts"] == {
        "records": 7,
        "record_types": {
            "assistant": 3,
            "progress": 2,
            "user": 2,
        },
        "parse_warning_count": 0,
        "visible_message_record_count": 3,
        "tool_use_count": 1,
        "tool_result_count": 1,
        "progress_count": 2,
        "reasoning_evidence_count": 1,
        "usage_evidence_count": 2,
        "distinct_request_count": 2,
    }
    assert payload["normalization"]["coverage"] == {
        "messages": {
            "status": "normalized",
            "raw_visible_message_record_count": 3,
            "normalized_count": 3,
        },
        "model_runs": {
            "status": "normalized",
            "raw_request_count": 2,
            "normalized_count": 2,
        },
        "tool_invocations": {
            "status": "normalized",
            "raw_tool_use_count": 1,
            "raw_tool_result_count": 1,
            "normalized_count": 1,
        },
        "events": {
            "status": "normalized",
            "raw_record_count": 7,
            "raw_canonical_candidate_count": 7,
            "raw_progress_count": 2,
            "normalized_count": 7,
        },
        "reasoning": {
            "status": "normalized",
            "raw_evidence_count": 1,
            "normalized_count": 1,
        },
        "usage": {
            "status": "normalized",
            "raw_evidence_count": 2,
            "normalized_count": 2,
        },
    }

    model_runs = payload["chat"]["model_runs"]
    assert model_runs[0]["reasoning_trace"] == [
        {
            "reasoning_id": "reasoning-1-1",
            "visibility": "visible",
            "content": "inspect repository layout before replying",
            "native": {
                "record_index": 2,
                "line": 2,
                "record_type": "assistant",
                "uuid": "msg-assistant-1",
                "parent_uuid": "msg-user-1",
                "message_role": "assistant",
                "reasoning_key": "thinking",
                "content_index": 1,
                "message_id": "msg-tool-assistant-1",
                "request_id": "req-claude-1",
                "model": "claude-opus-4-6",
                "signature": "claude-thinking-signature-1",
            },
            "timestamp": "2026-04-18T11:00:01.000Z",
            "source_refs": [
                {
                    "source_ref_id": "source-1",
                    "record_index": 2,
                    "line": 2,
                    "content_index": 1,
                }
            ],
        }
    ]
    assert payload["chat"]["usage"] == [
        {
            "usage_id": "usage-1",
            "scope": "model_run",
            "provider": "claude-code",
            "native": {
                "record_index": 3,
                "line": 3,
                "record_type": "assistant",
                "uuid": "msg-assistant-tool-1",
                "parent_uuid": "msg-assistant-1",
                "message_role": "assistant",
                "request_id": "req-claude-1",
                "message_id": "msg-tool-assistant-1",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "cache_creation_input_tokens": 5,
                    "cache_read_input_tokens": 7,
                    "cache_creation": {
                        "ephemeral_1h_input_tokens": 5,
                        "ephemeral_5m_input_tokens": 0,
                    },
                    "service_tier": "standard",
                    "inference_geo": "not_available",
                },
            },
            "model": "claude-opus-4-6",
            "model_run_ref": "model-run-1",
            "input_tokens": 10,
            "output_tokens": 20,
            "cache_read_tokens": 7,
            "cache_write_tokens": 5,
            "request_count": 1,
            "source_refs": [
                {"source_ref_id": "source-1", "record_index": 3, "line": 3}
            ],
        },
        {
            "usage_id": "usage-2",
            "scope": "model_run",
            "provider": "claude-code",
            "native": {
                "record_index": 7,
                "line": 7,
                "record_type": "assistant",
                "uuid": "msg-assistant-final-1",
                "parent_uuid": "msg-user-tool-result-1",
                "message_role": "assistant",
                "request_id": "req-claude-2",
                "message_id": "msg-assistant-final-1",
                "usage": {
                    "input_tokens": 14,
                    "output_tokens": 7,
                    "cache_creation_input_tokens": 2,
                    "cache_read_input_tokens": 11,
                    "cache_creation": {
                        "ephemeral_1h_input_tokens": 2,
                        "ephemeral_5m_input_tokens": 0,
                    },
                    "service_tier": "standard",
                    "inference_geo": "not_available",
                    "speed": "standard",
                    "iterations": [],
                    "server_tool_use": {
                        "web_search_requests": 0,
                        "web_fetch_requests": 0,
                    },
                },
            },
            "model": "claude-opus-4-6",
            "model_run_ref": "model-run-2",
            "input_tokens": 14,
            "output_tokens": 7,
            "cache_read_tokens": 11,
            "cache_write_tokens": 2,
            "request_count": 1,
            "source_refs": [
                {"source_ref_id": "source-1", "record_index": 7, "line": 7}
            ],
        },
    ]
    assert (
        "claude raw session reasoning normalized from thinking blocks: 1 entries"
        in payload["normalization"]["warnings"]
    )
    assert (
        "claude raw session usage normalized from message.usage: 2 records"
        in payload["normalization"]["warnings"]
    )
    assert (
        "claude raw session normalization covers messages, events, tool invocations, model runs, reasoning, and usage"
        in payload["normalization"]["warnings"]
    )


def test_chatlas_experimental_export_loads_copilot_raw_events(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "copilot-cli",
                "id": "copilot-main",
                "home": str(home / ".copilot"),
            }
        ],
    )

    session_id = "d1d3f48b-4b29-4dfc-b551-5536b9677225"
    _write_copilot_events(
        home / ".copilot" / "session-state" / session_id / "events.jsonl",
        session_id=session_id,
        user_text="copilot experimental user",
        assistant_text="copilot experimental assistant",
    )

    assert main(_chatlas_update_argv("--provider", "copilot-cli")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert (
        main(
            [
                "chatlas",
                "experimental",
                "export",
                session_id,
                "--provider",
                "copilot-cli",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["session"]["provider"] == "copilot-cli"
    assert payload["normalization"]["normalizer"] == "copilot-cli.raw_events.experimental.v1"
    assert payload["normalization"]["source_mode"] == "copilot_cli_raw_events"
    assert payload["normalization"]["unsupported_concepts"] == []
    assert payload["normalization"]["deferred_concepts"] == []
    assert payload["normalization"]["counts"] == {
        "messages": 3,
        "model_runs": 1,
        "tool_invocations": 1,
        "events": 10,
        "usage": 1,
        "reasoning_traces": 3,
    }
    assert payload["normalization"]["raw_counts"] == {
        "records": 10,
        "event_types": {
            "assistant.message": 1,
            "assistant.turn_end": 1,
            "assistant.turn_start": 1,
            "session.model_change": 1,
            "session.shutdown": 1,
            "session.start": 1,
            "system.message": 1,
            "tool.execution_complete": 1,
            "tool.execution_start": 1,
            "user.message": 1,
        },
        "parse_warning_count": 0,
        "reasoning_evidence_count": 3,
        "usage_evidence_count": 2,
        "cost_evidence_count": 1,
        "tool_request_count": 1,
    }
    assert payload["normalization"]["coverage"]["messages"] == {
        "status": "normalized",
        "raw_message_event_count": 3,
        "normalized_count": 3,
    }
    assert payload["normalization"]["coverage"]["model_runs"] == {
        "status": "normalized",
        "raw_turn_start_count": 1,
        "raw_turn_end_count": 1,
        "normalized_count": 1,
    }
    assert payload["normalization"]["coverage"]["tool_invocations"] == {
        "status": "normalized",
        "raw_tool_request_count": 1,
        "raw_tool_execution_start_count": 1,
        "raw_tool_execution_complete_count": 1,
        "normalized_count": 1,
    }
    assert payload["normalization"]["coverage"]["events"] == {
        "status": "normalized",
        "raw_count": 10,
        "normalized_count": 10,
    }
    assert payload["normalization"]["coverage"]["reasoning"] == {
        "status": "normalized",
        "raw_evidence_count": 3,
        "normalized_count": 3,
    }
    assert payload["normalization"]["coverage"]["usage"] == {
        "status": "normalized",
        "raw_evidence_count": 2,
        "normalized_count": 1,
    }
    assert payload["normalization"]["coverage"]["cost"] == {
        "status": "normalized",
        "raw_evidence_count": 1,
        "normalized_count": 1,
    }
    events = payload["chat"]["events"]
    assert [event["type"] for event in events] == [
        "copilot-cli.session.start",
        "copilot-cli.session.model_change",
        "copilot-cli.system.message",
        "copilot-cli.user.message",
        "copilot-cli.assistant.turn_start",
        "copilot-cli.assistant.message",
        "copilot-cli.tool.execution_start",
        "copilot-cli.tool.execution_complete",
        "copilot-cli.assistant.turn_end",
        "copilot-cli.session.shutdown",
    ]
    assert events[0] == {
        "event_id": "event-1",
        "type": "copilot-cli.session.start",
        "timestamp": "2026-04-18T11:00:00.000Z",
        "data": {
            "sessionId": session_id,
            "producer": "copilot-agent",
        },
        "native": {
            "event_type": "session.start",
            "event_index": 1,
            "line": 1,
            "event_id": "event-start",
        },
        "source_refs": [
            {"source_ref_id": "source-1", "event_index": 1, "line": 1}
        ],
    }
    assert events[4]["turn_id"] == "0"
    assert events[5]["data"]["reasoningText"] == "check repository state"
    assert events[6]["data"] == {
        "toolCallId": "tool-call-1",
        "toolName": "shell",
        "arguments": {"cmd": "git status"},
        "interactionId": "copilot-interaction-1",
    }
    assert events[6]["call_id"] == "tool-call-1"
    assert events[6]["tool_invocation_ref"] == "tool-invocation-1"
    assert events[7]["data"] == {
        "toolCallId": "tool-call-1",
        "success": True,
        "model": "gpt-4.1",
        "interactionId": "copilot-interaction-1",
        "result": {
            "content": "On branch main",
            "detailedContent": "On branch main\nnothing to commit, working tree clean",
        },
    }
    assert events[7]["call_id"] == "tool-call-1"
    assert events[7]["tool_invocation_ref"] == "tool-invocation-1"
    messages = payload["chat"]["messages"]
    assert [message["role"] for message in messages] == ["system", "user", "assistant"]
    assert [message["visibility"] for message in messages] == [
        "context",
        "conversation",
        "conversation",
    ]
    assert messages[0]["content"] == [{"type": "text", "text": "copilot system prompt"}]
    assert messages[0]["native"]["content_types"] == ["string"]
    assert messages[1]["content"] == [
        {"type": "text", "text": "copilot experimental user"}
    ]
    assert (
        messages[1]["native"]["transformed_content"]
        == "<context>\ncopilot experimental user\n</context>"
    )
    assert messages[1]["source_refs"] == [
        {"source_ref_id": "source-1", "event_index": 4, "line": 4}
    ]
    assert messages[2]["content"] == [
        {"type": "text", "text": "copilot experimental assistant"},
        {
            "type": "tool_call",
            "native": {
                "toolCallId": "tool-call-1",
                "name": "shell",
                "arguments": {"cmd": "git status"},
            },
            "call_id": "tool-call-1",
            "tool_name": "shell",
            "arguments": {"cmd": "git status"},
        },
    ]
    assert messages[2]["native"]["content_types"] == ["text", "tool_request"]
    assert messages[2]["native"]["reasoning_text"] == "check repository state"
    assert messages[2]["native"]["reasoning_opaque"] == "opaque-reasoning"
    assert messages[2]["native"]["encrypted_content"] == "encrypted-reasoning"
    assert messages[2]["native"]["output_tokens"] == 17
    assert messages[2]["native"]["tool_requests"] == [
        {
            "toolCallId": "tool-call-1",
            "name": "shell",
            "arguments": {"cmd": "git status"},
        }
    ]
    tool_invocations = payload["chat"]["tool_invocations"]
    assert "interaction_id" not in tool_invocations[0]
    assert tool_invocations == [
        {
            "tool_invocation_id": "tool-invocation-1",
            "call_id": "tool-call-1",
            "tool_name": "shell",
            "status": "completed",
            "native": {
                "request_present": True,
                "execution_start_present": True,
                "execution_complete_present": True,
                "event_indices": {
                    "tool_request": [{"event_index": 6, "request_index": 1}],
                    "tool.execution_start": [7],
                    "tool.execution_complete": [8],
                },
                "request": {
                    "toolCallId": "tool-call-1",
                    "name": "shell",
                    "arguments": {"cmd": "git status"},
                },
                "execution_start": {
                    "toolCallId": "tool-call-1",
                    "toolName": "shell",
                    "arguments": {"cmd": "git status"},
                    "interactionId": "copilot-interaction-1",
                },
                "execution_complete": {
                    "toolCallId": "tool-call-1",
                    "success": True,
                    "model": "gpt-4.1",
                    "interactionId": "copilot-interaction-1",
                    "result": {
                        "content": "On branch main",
                        "detailedContent": "On branch main\nnothing to commit, working tree clean",
                    },
                },
                "interaction_id": "copilot-interaction-1",
            },
            "started_at": "2026-04-18T11:00:03.000Z",
            "ended_at": "2026-04-18T11:00:03.500Z",
            "input": {"arguments": {"cmd": "git status"}},
            "output": {
                "content": "On branch main",
                "detailed_content": "On branch main\nnothing to commit, working tree clean",
            },
            "model": "gpt-4.1",
            "source_refs": [
                {"source_ref_id": "source-1", "event_index": 6, "line": 6},
                {"source_ref_id": "source-1", "event_index": 7, "line": 7},
                {"source_ref_id": "source-1", "event_index": 8, "line": 8},
            ],
            "event_refs": ["event-7", "event-8"],
        }
    ]
    assert payload["chat"]["usage"] == [
        {
            "usage_id": "usage-1",
            "scope": "session",
            "provider": "copilot-cli",
            "model": "gpt-4.1",
            "native": {
                "event_type": "session.shutdown",
                "event_index": 10,
                "line": 10,
                "event_id": "event-shutdown",
                "parent_id": "event-turn-end-1",
                "model_metrics_key": "gpt-4.1",
                "model_metrics_entry": {
                    "requests": {"count": 1, "cost": 1},
                    "usage": {
                        "inputTokens": 12,
                        "outputTokens": 34,
                        "cacheReadTokens": 0,
                        "cacheWriteTokens": 0,
                        "reasoningTokens": 5,
                    },
                },
                "total_premium_requests": 1,
                "current_model": "gpt-4.1",
                "session_token_counters": {
                    "current_tokens": 12,
                    "system_tokens": 4,
                    "conversation_tokens": 5,
                    "tool_definitions_tokens": 3,
                },
            },
            "input_tokens": 12,
            "output_tokens": 34,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "reasoning_tokens": 5,
            "request_count": 1,
            "provider_billing_units": {
                "kind": "copilot_premium_request_cost",
                "value": 1,
            },
            "source_refs": [
                {"source_ref_id": "source-1", "event_index": 10, "line": 10}
            ],
        }
    ]
    assert "interaction_id" not in payload["chat"]["model_runs"][0]
    assert payload["chat"]["model_runs"] == [
        {
            "model_run_id": "model-run-1",
            "provider": "copilot-cli",
            "status": "completed",
            "native": {
                "turn_start_present": True,
                "turn_end_present": True,
                "turn_start_event_index": 5,
                "span_end_event_index": 9,
                "model_source": "session.model_change.newModel",
                "turn_start_event_id": "event-turn-start-1",
                "turn_end_event_index": 9,
                "turn_end_event_id": "event-turn-end-1",
                "interaction_id": "copilot-interaction-1",
            },
            "turn_id": "0",
            "started_at": "2026-04-18T11:00:01.500Z",
            "ended_at": "2026-04-18T11:00:03.700Z",
            "model": "gpt-4.1",
            "output_tokens": 17,
            "source_refs": [
                {"source_ref_id": "source-1", "event_index": 5, "line": 5},
                {"source_ref_id": "source-1", "event_index": 9, "line": 9},
            ],
            "message_refs": ["message-2", "message-3"],
            "tool_invocation_refs": ["tool-invocation-1"],
            "event_refs": [
                "event-5",
                "event-6",
                "event-7",
                "event-8",
                "event-9",
            ],
            "reasoning_trace": [
                {
                    "reasoning_id": "reasoning-1-1",
                    "visibility": "visible",
                    "content": "check repository state",
                    "native": {
                        "event_type": "assistant.message",
                        "event_index": 6,
                        "line": 6,
                        "event_id": "event-assistant-1",
                        "parent_id": "event-turn-start-1",
                        "reasoning_key": "reasoningText",
                        "message_id": "assistant-message-1",
                        "request_id": "assistant-request-1",
                        "interaction_id": "copilot-interaction-1",
                        "output_tokens": 17,
                    },
                    "timestamp": "2026-04-18T11:00:02.000Z",
                    "source_refs": [
                        {"source_ref_id": "source-1", "event_index": 6, "line": 6}
                    ],
                },
                {
                    "reasoning_id": "reasoning-1-2",
                    "visibility": "opaque",
                    "content": "opaque-reasoning",
                    "native": {
                        "event_type": "assistant.message",
                        "event_index": 6,
                        "line": 6,
                        "event_id": "event-assistant-1",
                        "parent_id": "event-turn-start-1",
                        "reasoning_key": "reasoningOpaque",
                        "message_id": "assistant-message-1",
                        "request_id": "assistant-request-1",
                        "interaction_id": "copilot-interaction-1",
                        "output_tokens": 17,
                    },
                    "timestamp": "2026-04-18T11:00:02.000Z",
                    "source_refs": [
                        {"source_ref_id": "source-1", "event_index": 6, "line": 6}
                    ],
                },
                {
                    "reasoning_id": "reasoning-1-3",
                    "visibility": "encrypted",
                    "content": "encrypted-reasoning",
                    "native": {
                        "event_type": "assistant.message",
                        "event_index": 6,
                        "line": 6,
                        "event_id": "event-assistant-1",
                        "parent_id": "event-turn-start-1",
                        "reasoning_key": "encryptedContent",
                        "message_id": "assistant-message-1",
                        "request_id": "assistant-request-1",
                        "interaction_id": "copilot-interaction-1",
                        "output_tokens": 17,
                    },
                    "timestamp": "2026-04-18T11:00:02.000Z",
                    "source_refs": [
                        {"source_ref_id": "source-1", "event_index": 6, "line": 6}
                    ],
                },
            ],
        }
    ]
    assert (
        "copilot raw events parsed for future normalization: 10 events"
        in payload["normalization"]["warnings"]
    )
    assert (
        "copilot raw events normalized from events.jsonl: 10 events"
        in payload["normalization"]["warnings"]
    )
    assert (
        "copilot raw events messages normalized from message events: 3 messages"
        in payload["normalization"]["warnings"]
    )
    assert (
        "copilot raw events tool invocations normalized by toolCallId: 1 invocations"
        in payload["normalization"]["warnings"]
    )
    assert (
        "copilot raw events model runs normalized from turn events: 1 runs"
        in payload["normalization"]["warnings"]
    )
    assert (
        "copilot raw events usage normalized from session.shutdown.modelMetrics: 1 records"
        in payload["normalization"]["warnings"]
    )


def test_chatlas_experimental_export_errors_for_missing_provider_normalizer(
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
    _write_pi_session(
        pi_home
        / "sessions"
        / "--Users-pereiro-projects-agentos-project-agentos-iterante-dev--"
        / f"2026-04-17T19-14-52-021Z_{session_id}.jsonl",
        session_id=session_id,
    )

    assert main(_chatlas_update_argv("--provider", "pi")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "experimental", "export", session_id, "--provider", "pi"]) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert (
        "experimental session model export has no provider-specific raw normalizer "
        "for provider pi"
    ) in captured.err


def test_chatlas_experimental_export_reports_invalid_codex_raw_lines(
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

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd6"
    thread_name = "experimental-invalid-raw-thread"
    rollout_path = home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    _write_codex_dialog_rollout_with_invalid_line(
        rollout_path,
        session_id=session_id,
        user_text="invalid raw user",
        assistant_text="invalid raw assistant",
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "experimental", "export", thread_name, "--provider", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["normalization"]["normalizer"] == "codex.raw_rollout.experimental.v1"
    assert payload["normalization"]["source_mode"] == "codex_raw_rollout"
    assert [message["role"] for message in payload["chat"]["messages"]] == ["user", "assistant"]
    assert any(
        warning.startswith("codex raw rollout line 2 is invalid json:")
        for warning in payload["normalization"]["warnings"]
    )
    assert (
        "codex raw rollout parsed for future normalization: 3 records"
        in payload["normalization"]["warnings"]
    )


def test_chatlas_experimental_export_preserves_codex_context_messages(
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

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd7"
    thread_name = "experimental-context-raw-thread"
    rollout_path = home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    _write_codex_context_rollout(rollout_path, session_id=session_id)
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "experimental", "export", thread_name, "--provider", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)

    messages = payload["chat"]["messages"]
    assert [message["role"] for message in messages] == ["developer", "user", "assistant"]
    assert [message["visibility"] for message in messages] == [
        "context",
        "context",
        "conversation",
    ]
    assert messages[0]["content"] == [
        {"type": "text", "text": "developer instruction", "origin": "input"}
    ]
    assert messages[1]["content"] == [
        {
            "type": "text",
            "text": "<environment_context>\nctx",
            "origin": "input",
        }
    ]
    assert messages[2]["content"] == [
        {
            "type": "unknown",
            "native": {"type": "custom_payload", "value": {"status": "ok"}},
        }
    ]
    assert any(
        "content item 1 has unsupported type custom_payload" in warning
        for warning in payload["normalization"]["warnings"]
    )


def test_chatlas_experimental_export_joins_codex_tool_invocations(
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

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd8"
    thread_name = "experimental-tool-raw-thread"
    rollout_path = home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    _write_codex_tool_rollout(rollout_path, session_id=session_id)
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "experimental", "export", thread_name, "--provider", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["normalization"]["source_mode"] == "codex_raw_rollout"
    assert payload["normalization"]["unsupported_concepts"] == ["usage"]
    assert payload["normalization"]["deferred_concepts"] == ["usage"]
    assert payload["normalization"]["counts"] == {
        "messages": 1,
        "model_runs": 1,
        "tool_invocations": 2,
        "events": 3,
        "usage": 0,
        "reasoning_traces": 0,
    }
    assert payload["normalization"]["raw_counts"] == {
        "records": 8,
        "record_types": {
            "event_msg": 3,
            "response_item": 4,
            "session_meta": 1,
        },
        "response_item_types": {
            "function_call": 2,
            "function_call_output": 1,
            "message": 1,
        },
        "event_msg_types": {
            "exec_command_end": 1,
            "task_started": 1,
            "token_count": 1,
        },
        "parse_warning_count": 0,
    }
    assert payload["normalization"]["coverage"]["usage"] == {
        "status": "event_only",
        "raw_token_count_event_count": 1,
        "normalized_count": 0,
    }
    assert (
        "codex raw rollout tool invocations normalized by call_id: 2 invocations"
        in payload["normalization"]["warnings"]
    )
    assert (
        "codex raw rollout events normalized from event_msg: 3 events"
        in payload["normalization"]["warnings"]
    )
    assert (
        "codex token_count events preserved as events only; stable usage projection is deferred: 1 events"
        in payload["normalization"]["warnings"]
    )

    complete, incomplete = payload["chat"]["tool_invocations"]
    assert complete["tool_invocation_id"] == "tool-invocation-1"
    assert complete["call_id"] == "call-complete"
    assert complete["tool_name"] == "exec_command"
    assert complete["status"] == "completed"
    assert complete["started_at"] == "2026-03-08T01:09:00.000Z"
    assert complete["ended_at"] == "2026-03-08T01:09:01.100Z"
    assert complete["turn_id"] == "turn-1"
    assert complete["event_refs"] == ["event-3"]
    assert complete["input"] == {
        "arguments": {
            "cmd": "pwd",
            "workdir": "/tmp",
        }
    }
    assert complete["output"] == {"content": "Chunk ID: abc\nOutput:\n/tmp\n"}
    assert complete["execution"] == {
        "command": ["/bin/zsh", "-lc", "pwd"],
        "cwd": "/tmp",
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
        "aggregated_output": "/tmp\n",
        "duration": 1.25,
    }
    assert complete["source_refs"] == [
        {"source_ref_id": "source-1", "record_index": 5, "line": 5},
        {"source_ref_id": "source-1", "record_index": 6, "line": 6},
        {"source_ref_id": "source-1", "record_index": 7, "line": 7},
    ]
    assert complete["native"] == {
        "response_call_present": True,
        "response_output_present": True,
        "exec_end_present": True,
        "record_indices": {
            "function_call": [5],
            "function_call_output": [6],
            "exec_command_end": [7],
        },
        "raw_status": "completed",
    }

    assert incomplete["tool_invocation_id"] == "tool-invocation-2"
    assert incomplete["call_id"] == "call-incomplete"
    assert incomplete["status"] == "requested"
    assert incomplete["input"] == {
        "arguments": "{bad-json",
        "arguments_format": "raw_string",
    }
    assert any(
        warning == "codex tool call_id call-incomplete missing function_call_output record"
        for warning in payload["normalization"]["warnings"]
    )
    assert any(
        warning == "codex tool call_id call-incomplete missing exec_command_end record"
        for warning in payload["normalization"]["warnings"]
    )
    assert any(
        warning == "codex tool call_id call-incomplete has invalid json arguments"
        for warning in payload["normalization"]["warnings"]
    )

    events = payload["chat"]["events"]
    assert [event["type"] for event in events] == [
        "codex.task_started",
        "codex.token_count",
        "codex.exec_command_end",
    ]
    assert events[0] == {
        "event_id": "event-1",
        "type": "codex.task_started",
        "timestamp": "2026-03-08T01:08:59.090Z",
        "turn_id": "turn-1",
        "data": {
            "turn_id": "turn-1",
            "started_at": 1772946539,
            "model_context_window": 258400,
            "collaboration_mode_kind": "default",
        },
        "native": {
            "record_type": "event_msg",
            "payload_type": "task_started",
            "record_index": 2,
        },
        "source_refs": [
            {"source_ref_id": "source-1", "record_index": 2, "line": 2}
        ],
    }
    assert events[1]["event_id"] == "event-2"
    assert events[1]["type"] == "codex.token_count"
    assert events[1]["data"]["info"]["total_token_usage"]["total_tokens"] == 12
    assert events[2]["event_id"] == "event-3"
    assert events[2]["type"] == "codex.exec_command_end"
    assert events[2]["call_id"] == "call-complete"
    assert events[2]["turn_id"] == "turn-1"
    assert events[2]["tool_invocation_ref"] == "tool-invocation-1"
    assert events[2]["data"]["duration"] == 1.25
    assert events[2]["data"]["aggregated_output"] == "/tmp\n"
    assert events[2]["source_refs"] == [
        {"source_ref_id": "source-1", "record_index": 7, "line": 7}
    ]


def test_chatlas_experimental_export_normalizes_codex_model_runs(
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

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd9"
    thread_name = "experimental-model-run-thread"
    rollout_path = home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    _write_codex_model_run_rollout(rollout_path, session_id=session_id)
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "experimental", "export", thread_name, "--provider", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["normalization"]["source_mode"] == "codex_raw_rollout"
    assert payload["normalization"]["unsupported_concepts"] == []
    assert payload["normalization"]["deferred_concepts"] == []
    assert payload["normalization"]["counts"] == {
        "messages": 1,
        "model_runs": 1,
        "tool_invocations": 1,
        "events": 3,
        "usage": 0,
        "reasoning_traces": 1,
    }
    assert payload["normalization"]["raw_counts"] == {
        "records": 9,
        "record_types": {
            "event_msg": 3,
            "response_item": 4,
            "session_meta": 1,
            "turn_context": 1,
        },
        "response_item_types": {
            "function_call": 1,
            "function_call_output": 1,
            "message": 1,
            "reasoning": 1,
        },
        "event_msg_types": {
            "exec_command_end": 1,
            "task_complete": 1,
            "task_started": 1,
        },
        "parse_warning_count": 0,
    }
    assert payload["normalization"]["coverage"]["model_runs"] == {
        "status": "normalized",
        "raw_turn_context_count": 1,
        "normalized_count": 1,
    }
    assert payload["normalization"]["coverage"]["reasoning"] == {
        "status": "normalized",
        "raw_count": 1,
        "normalized_count": 1,
    }
    assert payload["normalization"]["coverage"]["usage"] == {
        "status": "no_raw_evidence",
        "raw_token_count_event_count": 0,
        "normalized_count": 0,
    }
    assert (
        "codex raw rollout model runs normalized: 1 runs"
        in payload["normalization"]["warnings"]
    )

    model_runs = payload["chat"]["model_runs"]
    assert len(model_runs) == 1
    model_run = model_runs[0]
    assert model_run["model_run_id"] == "model-run-1"
    assert model_run["provider"] == "codex"
    assert model_run["model"] == "gpt-5.4-mini"
    assert model_run["turn_id"] == "turn-1"
    assert model_run["status"] == "completed"
    assert model_run["started_at"] == "2026-03-08T01:09:00.000Z"
    assert model_run["ended_at"] == "2026-03-08T01:09:05.000Z"
    assert "model_provider" not in model_run
    assert "reasoning_effort" not in model_run
    assert "duration_ms" not in model_run
    assert "model_context_window" not in model_run
    assert "cwd" not in model_run
    assert "approval_policy" not in model_run
    assert "sandbox_policy" not in model_run
    assert "collaboration_mode" not in model_run
    assert "user_instructions" not in model_run
    assert "summary" not in model_run
    assert model_run["message_refs"] == ["message-1"]
    assert model_run["tool_invocation_refs"] == ["tool-invocation-1"]
    assert model_run["event_refs"] == ["event-1", "event-2", "event-3"]
    assert model_run["native"] == {
        "model_provider": "openai",
        "reasoning_effort": "high",
        "cwd": "/tmp/project",
        "approval_policy": "never",
        "sandbox_policy": {"type": "workspace-write"},
        "current_date": "2026-03-08",
        "timezone": "UTC",
        "truncation_policy": {"mode": "tokens", "limit": 10000},
        "realtime_active": False,
        "collaboration_mode": {
            "mode": "default",
            "settings": {
                "model": "gpt-5.4-mini",
                "reasoning_effort": "high",
            },
        },
        "model_context_window": 258400,
        "duration_ms": 5000,
        "turn_context_present": True,
        "turn_context_record_index": 2,
        "span_start_record_index": 2,
        "span_end_record_index": 9,
    }
    assert "developer_instructions" not in json.dumps(model_run["native"]["collaboration_mode"])
    assert model_run["source_refs"] == [
        {"source_ref_id": "source-1", "record_index": 2, "line": 2}
    ]

    reasoning_trace = model_run["reasoning_trace"]
    assert reasoning_trace == [
        {
            "reasoning_id": "reasoning-1",
            "visibility": "encrypted",
            "native": {
                "record_type": "response_item",
                "payload_type": "reasoning",
                "record_index": 5,
                "summary": [{"type": "summary_text", "text": "check context"}],
            },
            "timestamp": "2026-03-08T01:09:02.000Z",
            "content": "encrypted-reasoning",
            "source_refs": [
                {"source_ref_id": "source-1", "record_index": 5, "line": 5}
            ],
        }
    ]


def test_chatlas_experimental_export_attaches_codex_multi_turn_model_runs(
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

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fda"
    thread_name = "experimental-multi-turn-model-run-thread"
    rollout_path = home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    _write_codex_multi_turn_model_run_rollout(rollout_path, session_id=session_id)
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "experimental", "export", thread_name, "--provider", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["normalization"]["counts"] == {
        "messages": 4,
        "model_runs": 2,
        "tool_invocations": 0,
        "events": 4,
        "usage": 0,
        "reasoning_traces": 2,
    }
    assert payload["normalization"]["coverage"]["model_runs"] == {
        "status": "normalized",
        "raw_turn_context_count": 2,
        "normalized_count": 2,
    }
    assert payload["normalization"]["coverage"]["reasoning"] == {
        "status": "normalized",
        "raw_count": 2,
        "normalized_count": 2,
    }

    first_run, second_run = payload["chat"]["model_runs"]
    assert first_run["turn_id"] == "turn-1"
    assert first_run["message_refs"] == ["message-1", "message-2"]
    assert first_run["event_refs"] == ["event-1", "event-2"]
    assert [entry["content"] for entry in first_run["reasoning_trace"]] == [
        "first turn reasoning"
    ]
    assert first_run["native"]["span_start_record_index"] == 2
    assert first_run["native"]["span_end_record_index"] == 7

    assert second_run["turn_id"] == "turn-2"
    assert second_run["message_refs"] == ["message-3", "message-4"]
    assert second_run["event_refs"] == ["event-3", "event-4"]
    assert [entry["content"] for entry in second_run["reasoning_trace"]] == [
        "second turn reasoning"
    ]
    assert second_run["native"]["span_start_record_index"] == 8
    assert second_run["native"]["span_end_record_index"] == 13

    assert not any(
        warning.startswith("codex reasoning records could not be attached to a model run:")
        for warning in payload["normalization"]["warnings"]
    )


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
