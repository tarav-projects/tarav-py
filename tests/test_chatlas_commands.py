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
from agentos.chatlas.session_model._hashes import (
    _session_content_hash,
    _session_identity_hash,
)
from agentos.chatlas.session_model._shared import _standard_model_traceability_errors
from _helpers import write_text_file as _write


_DEFAULT_CHATLAS_INSTANCE_IDS = object()


def _set_iso_mtime(path: Path, timestamp: str) -> None:
    normalized = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
    seconds = datetime.fromisoformat(normalized).astimezone(timezone.utc).timestamp()
    os.utime(path, (seconds, seconds))


def _read_session_index_rows(index_path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for shard_path in sorted(index_path.glob("*.index.jsonl")):
        rows.extend(
            json.loads(line)
            for line in shard_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return rows


def _session_index_shard_path(index_path: Path, identity_hash: str) -> Path:
    return index_path / f"{identity_hash.removeprefix('sha256:')[:2]}.index.jsonl"


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
    include_assistant_image: bool = False,
) -> None:
    assistant_content: list[dict[str, object]] = [{"type": "text", "text": assistant_text}]
    if include_assistant_image:
        assistant_content.append(
            {
                "type": "image",
                "image_url": "https://example.com/copilot.png",
            }
        )
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
                "content": assistant_content,
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
    configured_legacy_configs = [
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
            "instances": configured_legacy_configs,
        },
    }
    if chatlas_instance_ids is _DEFAULT_CHATLAS_INSTANCE_IDS:
        payload["chatlas"] = {
            "instance_ids": [
                instance_id
                for instance in configured_legacy_configs
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


_REFERENCE_CLAUDE_SESSION_ID = "5dbf4437-633e-4039-a627-0459d85e9ecc"
_REFERENCE_COPILOT_SESSION_ID = "d1d3f48b-4b29-4dfc-b551-5536b9677225"
_REFERENCE_CODEX_SESSION_ID = "019db5fd-7a73-7ae1-b5eb-901e62258dcb"


def _copy_chatlas_reference_session_samples(home: Path) -> None:
    sample_root = Path(__file__).resolve().parents[1] / "dev" / "session-samples"

    claude_target = (
        home
        / ".claude"
        / "projects"
        / "-reference-project"
        / f"{_REFERENCE_CLAUDE_SESSION_ID}.jsonl"
    )
    claude_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        sample_root / "claude-code" / f"{_REFERENCE_CLAUDE_SESSION_ID}.jsonl",
        claude_target,
    )

    copilot_target = (
        home
        / ".copilot"
        / "session-state"
        / _REFERENCE_COPILOT_SESSION_ID
        / "events.jsonl"
    )
    copilot_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        sample_root / "copilot-cli" / _REFERENCE_COPILOT_SESSION_ID / "events.jsonl",
        copilot_target,
    )

    codex_target = (
        home
        / ".codex"
        / "sessions"
        / "2026"
        / "04"
        / "22"
        / f"rollout-2026-04-22T12-19-41-{_REFERENCE_CODEX_SESSION_ID}.jsonl"
    )
    codex_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        sample_root
        / "codex"
        / _REFERENCE_CODEX_SESSION_ID
        / f"rollout-2026-04-22T12-19-41-{_REFERENCE_CODEX_SESSION_ID}.jsonl",
        codex_target,
    )


def _assert_current_semantic_event_tape(events: list[dict[str, object]]) -> None:
    required_keys = {
        "event_id",
        "sequence",
        "kind",
        "producer",
        "surfaces",
        "interaction_ref",
        "payload",
        "source_refs",
    }
    assert events
    for index, event in enumerate(events, start=1):
        assert required_keys <= set(event)
        assert event["event_id"] == f"event-{index}"
        assert event["sequence"] == index
        assert "type" not in event
        assert "data" not in event
        assert "native" not in event
        assert isinstance(event["kind"], str)
        assert isinstance(event["producer"], dict)
        assert isinstance(event["surfaces"], dict)
        assert isinstance(event["interaction_ref"], str)
        assert isinstance(event["payload"], dict)
        assert isinstance(event["source_refs"], list)
        assert event["producer"].get("type")
        assert {"transcript", "replay", "debug", "model_input"} <= set(event["surfaces"])
        for source_ref in event["source_refs"]:
            assert isinstance(source_ref, dict)
            assert isinstance(source_ref.get("source_ref_id"), str)


def _assert_current_projection_links(payload: dict[str, object]) -> None:
    chat = payload["chat"]
    assert isinstance(chat, dict)
    events = chat["events"]
    messages = chat["messages"]
    model_runs = chat["model_runs"]
    tool_invocations = chat["tool_invocations"]
    usage_records = chat["usage"]
    assert isinstance(events, list)
    assert isinstance(messages, list)
    assert isinstance(model_runs, list)
    assert isinstance(tool_invocations, list)
    assert isinstance(usage_records, list)

    event_by_id = {
        event["event_id"]: event
        for event in events
        if isinstance(event, dict) and isinstance(event.get("event_id"), str)
    }
    message_ids = {
        message["message_id"]
        for message in messages
        if isinstance(message, dict) and isinstance(message.get("message_id"), str)
    }
    model_run_ids = {
        model_run["model_run_id"]
        for model_run in model_runs
        if isinstance(model_run, dict) and isinstance(model_run.get("model_run_id"), str)
    }
    tool_invocation_ids = {
        tool_invocation["tool_invocation_id"]
        for tool_invocation in tool_invocations
        if isinstance(tool_invocation, dict)
        and isinstance(tool_invocation.get("tool_invocation_id"), str)
    }

    for event in events:
        assert isinstance(event, dict)
        model_run_ref = event.get("model_run_ref")
        if model_run_ref is not None:
            assert model_run_ref in model_run_ids
        tool_invocation_ref = event.get("tool_invocation_ref")
        if tool_invocation_ref is not None:
            assert tool_invocation_ref in tool_invocation_ids

    for message in messages:
        assert isinstance(message, dict)
        assert message.get("source_refs")

    for tool_invocation in tool_invocations:
        assert isinstance(tool_invocation, dict)
        invocation_id = tool_invocation["tool_invocation_id"]
        assert isinstance(invocation_id, str)
        event_refs = tool_invocation.get("event_refs")
        assert isinstance(event_refs, list)
        assert event_refs
        for event_ref in event_refs:
            assert event_ref in event_by_id
            assert event_by_id[event_ref].get("tool_invocation_ref") == invocation_id

    for model_run in model_runs:
        assert isinstance(model_run, dict)
        event_refs = model_run.get("event_refs")
        assert isinstance(event_refs, list)
        assert event_refs
        for event_ref in event_refs:
            assert event_ref in event_by_id
        for message_ref in model_run.get("message_refs", []):
            assert message_ref in message_ids
        for tool_ref in model_run.get("tool_invocation_refs", []):
            assert tool_ref in tool_invocation_ids
        reasoning_trace = model_run.get("reasoning_trace")
        if isinstance(reasoning_trace, list):
            for reasoning in reasoning_trace:
                assert isinstance(reasoning, dict)
                assert reasoning.get("source_refs")

    for usage in usage_records:
        assert isinstance(usage, dict)
        assert usage.get("source_refs")
        model_run_ref = usage.get("model_run_ref")
        if model_run_ref is not None:
            assert model_run_ref in model_run_ids


def _native_paths(value: object, *, path: str = "$") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}"
            if key == "native":
                paths.append(item_path)
            paths.extend(_native_paths(item, path=item_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(_native_paths(item, path=f"{path}[{index}]"))
    return paths


def _without_native(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_native(item)
            for key, item in value.items()
            if key != "native"
        }
    if isinstance(value, list):
        return [_without_native(item) for item in value]
    return value


def _raw_provider_event_field_paths(value: object, *, path: str = "$") -> list[str]:
    forbidden_keys = {
        "data",
        "event_type",
        "message_type",
        "provider_event_type",
        "raw_event_type",
        "record_type",
        "source_event_type",
    }
    paths: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}"
            if key in forbidden_keys:
                paths.append(item_path)
            paths.extend(_raw_provider_event_field_paths(item, path=item_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(_raw_provider_event_field_paths(item, path=f"{path}[{index}]"))
    return paths


def _assert_current_standard_model_contract(
    payload: dict[str, object],
    *,
    expected_unsupported_concepts: list[str],
    expected_deferred_concepts: list[str],
) -> None:
    assert set(payload) == {
        "class",
        "schema_version",
        "session",
        "agent_instance",
        "sources",
        "chat",
        "normalization",
    }
    assert _native_paths(payload["session"], path="session") == []
    assert _native_paths(payload["chat"]["events"], path="chat.events") == []
    assert _native_paths(payload["chat"]["messages"], path="chat.messages") == []
    assert _native_paths(payload["chat"]["model_runs"], path="chat.model_runs") == []
    assert _native_paths(payload["chat"]["tool_invocations"], path="chat.tool_invocations") == []
    assert _native_paths(payload["chat"]["usage"], path="chat.usage") == []
    assert _raw_provider_event_field_paths(payload["session"], path="session") == []
    assert _raw_provider_event_field_paths(payload["chat"], path="chat") == []
    assert _standard_model_traceability_errors(payload) == []
    assert payload["normalization"]["unsupported_concepts"] == expected_unsupported_concepts
    assert payload["normalization"]["deferred_concepts"] == expected_deferred_concepts
    _assert_current_semantic_event_tape(payload["chat"]["events"])
    _assert_current_projection_links(payload)


def _assert_current_reference_session_quality(
    payload: dict[str, object],
    *,
    provider: str,
    session_id: str,
    expected_counts: dict[str, int],
    expected_kinds: set[str],
    expected_unsupported_concepts: list[str],
    expected_deferred_concepts: list[str],
    expected_coverage_statuses: dict[str, str],
) -> None:
    assert payload["class"] == "agentos.chatlas.session_model"
    assert payload["schema_version"] == 1
    assert payload["session"]["provider"] == provider
    assert payload["session"]["session_id"] == session_id
    assert payload["session"]["identity_hash"] == _session_identity_hash(
        provider=provider,
        provider_session_id=session_id,
    )
    assert payload["normalization"]["counts"] == expected_counts
    _assert_current_standard_model_contract(
        payload,
        expected_unsupported_concepts=expected_unsupported_concepts,
        expected_deferred_concepts=expected_deferred_concepts,
    )

    chat = payload["chat"]
    events = chat["events"]
    assert isinstance(events, list)
    assert len(events) == expected_counts["events"]
    assert payload["session"]["content_hash"] == _session_content_hash(events=events)
    assert {event["kind"] for event in events if isinstance(event, dict)} == expected_kinds

    coverage = payload["normalization"]["coverage"]
    assert isinstance(coverage, dict)
    for concept, expected_status in expected_coverage_statuses.items():
        assert coverage[concept]["status"] == expected_status


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
    assert payload["session_index_count"] == 1
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
    session_index_root = Path(payload["session_index_root"])
    assert session_index_root.is_dir()
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
    normalized_rows = _read_session_index_rows(session_index_root)
    assert len(normalized_rows) == 1
    assert normalized_rows[0]["class"] == "agentos.chatlas.session"
    assert normalized_rows[0]["provider"] == "codex"
    assert normalized_rows[0]["session_id"] == session_id
    assert normalized_rows[0]["display_name"] == thread_name
    assert normalized_rows[0]["native"] == {"thread_name": thread_name}
    assert normalized_rows[0]["identity_hash"] == _session_identity_hash(
        provider="codex",
        provider_session_id=session_id,
    )
    assert _session_index_shard_path(
        session_index_root,
        normalized_rows[0]["identity_hash"],
    ).is_file()

    log_subject = _git_output(chatlas_root, "log", "-1", "--pretty=%s")
    assert log_subject.startswith("chatlas update: ")


def test_codex_chatlas_context_uses_provider_native_capability(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / ".codex"

    from agentos.chatlas.raw import ChatlasArchiveConfig, _build_chatlas_provider_context
    from agentos.codex.chatlas import CodexAgentChatlas

    archive_config = ChatlasArchiveConfig(
        family="codex",
        instance_id="codex-main",
        label=None,
        is_default=False,
        homes=(("home", codex_home),),
        includes=("custom/**",),
        excludes=("custom-secret.json",),
        identity=("codex", "codex-main", str(codex_home)),
        uri_key="abc123def456",
        fingerprint="abc123def456",
        summary_payload={"family": "codex", "instance_id": "codex-main", "fingerprint": "abc123def456"},
    )

    codex_chatlas = CodexAgentChatlas.from_archive_config(archive_config)
    context = _build_chatlas_provider_context(archive_config)

    assert context.effective_includes == codex_chatlas.includes
    assert context.effective_excludes == codex_chatlas.excludes
    assert "custom/**" in context.effective_includes
    assert "custom-secret.json" in context.effective_excludes
    assert "_auth*.json" in context.effective_excludes


def test_provider_session_ref_entry_uses_provider_agent_context(tmp_path: Path) -> None:
    from agentos.agent.primitives import AgentConfig
    from agentos.chat.core import ProviderAgentContext, ProviderSessionRefEntry
    from agentos.chat.providers import LegacyProviderConfig
    from agentos.codex.agent import CodexAgent
    from agentos.codex.session import CodexSessionRef

    rollout_path = tmp_path / "rollout.jsonl"
    legacy_config = LegacyProviderConfig(
        family="codex",
        instance_id="codex-main",
        homes=(("home", tmp_path),),
        direct_targets=(rollout_path,),
    )
    agent = CodexAgent.from_config(
        AgentConfig(
            provider="codex",
            instance_id="codex-main",
            homes=(("home", tmp_path),),
        )
    )
    context = ProviderAgentContext(
        agent=agent,
        legacy_config=legacy_config,
        provider="codex",
        instance_summary={"family": "codex", "fingerprint": "abc123", "instance_id": "codex-main"},
        instance_fingerprint="abc123",
        direct_targets=(rollout_path,),
        direct_existing_targets=(),
        direct_missing_targets=(rollout_path,),
        grep_targets=(),
        grep_existing_targets=(),
        grep_missing_targets=(),
        sqlite_db_paths=(),
        sqlite_existing_db_paths=(),
        sqlite_missing_db_paths=(),
    )
    session = ProviderSessionRefEntry(
        context=context,
        session_ref=CodexSessionRef(
            native_session_id="session-1",
            rollout_paths=(rollout_path,),
        ),
    )

    assert not hasattr(session, "legacy_provider_config")
    assert session.context.instance_fingerprint == "abc123"
    assert ("provider_instance_fingerprint", "abc123") in session.query_fields()


def test_chatlas_session_index_shards_delete_stale_files(tmp_path: Path) -> None:
    from agentos.chatlas import core as chatlas_core

    identity_hash = _session_identity_hash(
        provider="codex",
        provider_session_id="session-1",
    )
    stale_shard = tmp_path / "index" / "sessions" / "ff.index.jsonl"
    _write(stale_shard, '{"session_id":"stale"}\n')

    chatlas_core._write_session_index_shards(
        tmp_path,
        [
            {
                "class": "agentos.chatlas.session",
                "schema_version": 1,
                "provider": "codex",
                "instance": "codex-main",
                "session_id": "session-1",
                "identity_hash": identity_hash,
            }
        ],
    )

    index_path = tmp_path / "index" / "sessions"
    rows = _read_session_index_rows(index_path)
    assert rows == [
        {
            "class": "agentos.chatlas.session",
            "schema_version": 1,
            "provider": "codex",
            "instance": "codex-main",
            "session_id": "session-1",
            "identity_hash": identity_hash,
        }
    ]
    assert _session_index_shard_path(index_path, identity_hash).is_file()
    assert not stale_shard.exists()


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
    assert payload["session_index_count"] == 1
    assert payload["instances"][0]["instance"] == "pi-mm"
    assert payload["instances"][0]["destination_root"] == str(destination_root)
    assert sorted(payload["instances"][0]["includes"]) == ["sessions/**", "settings.json"]
    assert transcript_path.relative_to(pi_home).is_relative_to(Path("sessions"))
    assert (destination_root / transcript_path.relative_to(pi_home)).is_file()
    assert (destination_root / "settings.json").is_file()
    assert not (destination_root / "auth.json").exists()
    assert not (destination_root / "bin" / "pi-helper").exists()
    assert not (destination_root / "notes.md").exists()

    normalized_rows = _read_session_index_rows(Path(payload["session_index_root"]))
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
    assert payload["session_index_count"] == 2
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

    normalized_rows = _read_session_index_rows(Path(payload["session_index_root"]))
    normalized_by_session_id = {row["session_id"]: row for row in normalized_rows}
    assert sorted(normalized_by_session_id) == [session_id, legacy_session_id]
    assert normalized_by_session_id[session_id]["provider"] == "copilot-cli"
    assert normalized_by_session_id[session_id]["instance"] == "copilot-main"
    assert normalized_by_session_id[legacy_session_id]["provider"] == "copilot-cli"
    assert normalized_by_session_id[legacy_session_id]["instance"] == "copilot-main"

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
    assert payload["session_index_count"] == 1
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

    normalized_rows = _read_session_index_rows(Path(payload["session_index_root"]))
    normalized_by_session_id = {row["session_id"]: row for row in normalized_rows}
    assert sorted(normalized_by_session_id) == [cli_session_id]
    assert normalized_by_session_id[cli_session_id]["provider"] == "claude-code"
    assert normalized_by_session_id[cli_session_id]["instance"] == "claude-main"

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
    assert payload["session_index_count"] == 1
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

    normalized_rows = _read_session_index_rows(Path(payload["session_index_root"]))
    assert len(normalized_rows) == 1
    normalized_row = normalized_rows[0]
    assert normalized_row["provider"] == "opencode"
    assert normalized_row["instance"] == "opencode-main"
    assert normalized_row["session_id"] == session_id

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
    session_index_cache_path = chatlas_core._session_index_cache_path(chatlas_root)

    assert first_payload["scan_cache_enabled"] is True
    assert first_payload["session_index_cache_enabled"] is True
    assert raw_cache_path.is_file()
    assert session_index_cache_path.is_file()
    assert "/cache/" in (chatlas_root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert _git_output(chatlas_root, "ls-files", "cache/raw-scan-v1.json") == ""
    assert _git_output(chatlas_root, "ls-files", "cache/session-index-v1.json") == ""
    assert _git_output(chatlas_root, "status", "--porcelain") == ""

    def fail_match(*args, **kwargs):
        raise AssertionError("expected scan cache to bypass destination content comparison")

    def fail_normalized_record(*args, **kwargs):
        raise AssertionError("expected session index cache to bypass session index rebuild")

    monkeypatch.setattr(chatlas_raw, "_chatlas_archive_files_match", fail_match)
    monkeypatch.setattr(chatlas_core, "_session_ref_index_record", fail_normalized_record)

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["scan_cache_enabled"] is True
    assert payload["session_index_cache_enabled"] is True
    assert payload["changes_detected"] is False
    assert payload["committed"] is False
    assert _git_output(chatlas_root, "status", "--porcelain") == ""


@pytest.mark.parametrize(
    "cache_flag, expected_scan, expected_normalized, patched_targets",
    [
        pytest.param(
            "--scan-cache=false",
            False, True,
            ("raw._chatlas_archive_files_match",),
            id="scan",
        ),
        pytest.param(
            "--session-index-cache=false",
            True, False,
            ("core._session_ref_index_record",),
            id="normalized",
        ),
        pytest.param(
            "--disable-cache",
            False, False,
            ("raw._chatlas_archive_files_match", "core._session_ref_index_record"),
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
        extra_argv += ["--scan-cache=true", "--session-index-cache=true"]

    assert main(_chatlas_update_argv(*extra_argv)) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["scan_cache_enabled"] is expected_scan
    assert payload["session_index_cache_enabled"] is expected_normalized
    assert payload["changes_detected"] is False
    assert payload["committed"] is False
    for target in patched_targets:
        assert counters[target] > 0, f"expected {target} to be called"


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
    assert payload["session_index_count"] == 1
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
    assert payload["session_index_count"] == 1
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
    assert payload["session_index_count"] == 2


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
    assert payload["session_index_count"] == 1
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
    assert payload["session_index_count"] == 0
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
    assert first_payload["session_index_count"] == 1

    _write_global_config(agentos_home / "config.json", chatlas_instance_ids=None)

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["instance_count"] == 0
    assert payload["session_index_count"] == 1
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
    assert payload["session_index_count"] == 0
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

    assert main(["chatlas", "stats", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "chatlas stats"
    assert payload["stats"]["session_count"] == 1
    assert payload["stats"]["provider_count"] == 1
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
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "chatlas query"
    assert payload["session_count"] == 1
    session = payload["sessions"][0]
    identity_hash = _session_identity_hash(
        provider="codex",
        provider_session_id=session_id,
    )
    assert session["provider"] == "codex"
    assert session["instance"] == "codex-main"
    assert session["session_id"] == session_id
    assert session["identity_hash"] == identity_hash
    assert session["display_name"] == thread_name
    assert session["native"] == {"thread_name": thread_name}
    assert session["match"]["fields"] == [{"field": "thread_name", "value": thread_name}]
    assert "summary" not in session
    assert "summary_levels" not in session

    assert main(["chatlas", "query", identity_hash, "--include-match"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["session_count"] == 1
    assert payload["sessions"][0]["session_id"] == session_id
    assert payload["sessions"][0]["match"]["fields"] == [
        {"field": "identity_hash", "value": identity_hash}
    ]


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


def test_chatlas_raw_path_and_export_read_archived_artifacts(
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
    thread_name = "raw-export-thread"
    rollout_name = f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    _write_codex_dialog_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / rollout_name,
        session_id=session_id,
        user_text="raw export user",
        assistant_text="raw export assistant",
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(_chatlas_update_argv("--provider", "codex")) == 0
    _ = json.loads(capsys.readouterr().out)

    identity_hash = _session_identity_hash(
        provider="codex",
        provider_session_id=session_id,
    )

    assert main(["chatlas", "raw", "path", identity_hash, "--provider", "codex"]) == 0
    paths = [
        Path(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]

    assert any(path.name == rollout_name for path in paths)
    assert all(path.is_file() for path in paths)

    assert main(["chatlas", "raw", "export", identity_hash, "--provider", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["class"] == "agentos.chatlas.raw_export"
    assert payload["command"] == "chatlas raw export"
    assert payload["session"]["session_id"] == session_id
    rollout_source = next(
        source
        for source in payload["sources"]
        if Path(source["path"]).name == rollout_name
    )
    assert rollout_source["content_encoding"] == "utf-8"
    assert "raw export user" in rollout_source["content"]
    assert "raw export assistant" in rollout_source["content"]


def test_chatlas_raw_path_errors_when_query_does_not_match(
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

    assert main(["chatlas", "raw", "path", "missing-session"]) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert "no Chatlas session matched query missing-session" in captured.err


def test_chatlas_export_emits_session_model_json(
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

    assert main(["chatlas", "export", thread_name, "--provider", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["class"] == "agentos.chatlas.session_model"
    assert payload["schema_version"] == 1
    assert payload["session"]["provider"] == "codex"
    assert payload["session"]["session_id"] == session_id
    assert payload["session"]["display_name"] == thread_name
    assert payload["session"]["identity_hash"] == _session_identity_hash(
        provider="codex",
        provider_session_id=session_id,
    )
    assert payload["session"]["content_hash"] == _session_content_hash(
        events=payload["chat"]["events"],
    )
    assert payload["agent_instance"]["provider_family"] == "codex"
    assert (
        payload["agent_instance"]["provider_instance_fingerprint"]
        == payload["session"]["provider_instance_fingerprint"]
    )
    assert any(source["role"] == "transcript" for source in payload["sources"])
    assert payload["chat"]["model_runs"] == []
    assert payload["chat"]["tool_invocations"] == []
    assert payload["chat"]["usage"] == []
    assert [event["kind"] for event in payload["chat"]["events"]] == [
        "session.start",
        "message",
        "message",
    ]
    assert not any("data" in event for event in payload["chat"]["events"])
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
    assert _native_paths(payload["session"], path="session") == []
    assert _native_paths(payload["chat"], path="chat") == []
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
        "codex raw rollout messages projected from semantic events: 2 messages"
        in payload["normalization"]["warnings"]
    )
    assert (
        "codex raw rollout semantic events normalized: 3 events"
        in payload["normalization"]["warnings"]
    )
    assert "messages" not in payload["normalization"]["unsupported_concepts"]
    assert "model_runs" in payload["normalization"]["unsupported_concepts"]

    assert (
        main(
            [
                "chatlas", "export",
                payload["session"]["identity_hash"],
                "--provider",
                "codex",
            ]
        )
        == 0
    )
    repeated_payload = json.loads(capsys.readouterr().out)
    assert (
        repeated_payload["session"]["identity_hash"]
        == payload["session"]["identity_hash"]
    )
    assert (
        repeated_payload["session"]["content_hash"]
        == payload["session"]["content_hash"]
    )
    assert "view" not in payload

    assert (
        main(
            [
                "chatlas",
                "export",
                thread_name,
                "--provider",
                "codex",
                "--view",
                "full",
            ]
        )
        == 0
    )
    full_payload = json.loads(capsys.readouterr().out)
    assert full_payload == payload

    assert (
        main(
            [
                "chatlas",
                "export",
                thread_name,
                "--provider",
                "codex",
                "--view",
                "transcript",
            ]
        )
        == 0
    )
    transcript_payload = json.loads(capsys.readouterr().out)
    assert transcript_payload["class"] == "agentos.chatlas.session_model"
    assert transcript_payload["view"] == "transcript"
    assert [message["role"] for message in transcript_payload["chat"]["messages"]] == [
        "user",
        "assistant",
    ]
    assert transcript_payload["chat"]["model_runs"] == []
    assert transcript_payload["chat"]["tool_invocations"] == []
    assert [event["kind"] for event in transcript_payload["chat"]["events"]] == [
        "message",
        "message",
    ]
    assert transcript_payload["chat"]["usage"] == []

    assert (
        main(
            [
                "chatlas",
                "export",
                thread_name,
                "--provider",
                "codex",
                "--view",
                "user",
            ]
        )
        == 0
    )
    user_payload = json.loads(capsys.readouterr().out)
    assert user_payload["view"] == "user"
    assert [message["role"] for message in user_payload["chat"]["messages"]] == [
        "user",
    ]
    assert user_payload["chat"]["model_runs"] == []
    assert user_payload["chat"]["tool_invocations"] == []
    assert [event["kind"] for event in user_payload["chat"]["events"]] == [
        "message",
    ]
    assert user_payload["chat"]["usage"] == []

    assert (
        main(
            [
                "chatlas",
                "export",
                thread_name,
                "--provider",
                "codex",
                "--view",
                "events",
            ]
        )
        == 0
    )
    events_payload = json.loads(capsys.readouterr().out)
    assert events_payload["view"] == "events"
    assert events_payload["chat"]["messages"] == []
    assert events_payload["chat"]["model_runs"] == []
    assert events_payload["chat"]["tool_invocations"] == []
    assert [event["kind"] for event in events_payload["chat"]["events"]] == [
        "session.start",
        "message",
        "message",
    ]
    assert events_payload["chat"]["usage"] == []

    assert (
        main(
            [
                "chatlas",
                "export",
                thread_name,
                "--provider",
                "codex",
                "--view",
                "zip-transcript",
            ]
        )
        == 0
    )
    zip_payload = json.loads(capsys.readouterr().out)
    assert zip_payload["view"] == "zip-transcript"
    assert set(zip_payload) == {"class", "schema_version", "session", "chat", "view"}
    assert set(zip_payload["session"]) == {
        "uri",
        "provider",
        "session_id",
        "display_name",
        "created_at",
        "updated_at",
        "identity_hash",
        "content_hash",
    }
    assert set(zip_payload["chat"]) == {"messages"}
    assert [message["role"] for message in zip_payload["chat"]["messages"]] == [
        "user",
        "assistant",
    ]
    assert [
        message["event_refs"][0] for message in zip_payload["chat"]["messages"]
    ] == [
        "event-2",
        "event-3",
    ]


def test_codex_session_model_uses_provider_native_session_input(
    tmp_path: Path,
) -> None:
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = tmp_path / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    index_path = tmp_path / "session_index.jsonl"
    session_payload = {
        "provider": "codex",
        "session_id": session_id,
        "display_name": "codex-thread",
        "updated_at": "2026-03-25T01:05:38Z",
        "primary_backing_artifact": {
            "role": "transcript",
            "storage_kind": "file",
            "path": str(rollout_path),
        },
        "backing_artifacts": [
            {
                "role": "transcript",
                "storage_kind": "file",
                "path": str(rollout_path),
            },
            {
                "role": "session_index",
                "storage_kind": "file",
                "path": str(index_path),
            },
        ],
    }
    sources = [
        {
            "source_ref_id": "source-1",
            "role": "transcript",
            "storage_kind": "file",
            "path": str(rollout_path),
        }
    ]

    from agentos.codex.session import CodexSession

    codex_session = CodexSession.from_chatlas_session_payload(
        session_payload,
        sources=sources,
    )

    assert codex_session is not None
    assert codex_session.native_session_id == session_id
    assert codex_session.rollout_path == rollout_path
    assert codex_session.source_ref_id == "source-1"
    assert codex_session.thread_name == "codex-thread"
    assert codex_session.index_paths == (index_path,)


def test_codex_session_discovery_uses_provider_native_session_model(
    tmp_path: Path,
) -> None:
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    thread_name = "codex-discovery-thread"
    codex_home = tmp_path / ".codex"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    index_path = codex_home / "session_index.jsonl"
    _write_codex_dialog_rollout(
        rollout_path,
        session_id=session_id,
        user_text="discovery user",
        assistant_text="discovery assistant",
    )
    _write_codex_session_index(
        index_path,
        session_id=session_id,
        thread_name=thread_name,
    )

    from agentos.codex.session import CodexSession, discover_codex_sessions

    sessions = discover_codex_sessions(targets=(codex_home / "sessions", index_path))

    assert len(sessions) == 1
    assert isinstance(sessions[0], CodexSession)
    assert sessions[0].native_session_id == session_id
    assert sessions[0].rollout_paths == (rollout_path,)
    assert sessions[0].index_paths == (index_path,)
    assert sessions[0].thread_name == thread_name


def test_claude_session_model_uses_provider_native_session_input(
    tmp_path: Path,
) -> None:
    session_id = "claude-session-1"
    transcript_path = tmp_path / f"{session_id}.jsonl"
    session_payload = {
        "provider": "claude-code",
        "session_id": session_id,
        "display_name": "claude-thread",
        "updated_at": "2026-03-25T01:05:38Z",
        "primary_backing_artifact": {
            "role": "transcript",
            "storage_kind": "file",
            "path": str(transcript_path),
        },
        "backing_artifacts": [
            {
                "role": "transcript",
                "storage_kind": "file",
                "path": str(transcript_path),
            }
        ],
    }
    sources = [
        {
            "source_ref_id": "source-1",
            "role": "transcript",
            "storage_kind": "file",
            "path": str(transcript_path),
        }
    ]

    from agentos.claude.session import ClaudeSession

    claude_session = ClaudeSession.from_chatlas_session_payload(
        session_payload,
        sources=sources,
    )

    assert claude_session is not None
    assert claude_session.native_session_id == session_id
    assert claude_session.transcript_path == transcript_path
    assert claude_session.source_ref_id == "source-1"
    assert claude_session.title == "claude-thread"


def test_claude_session_discovery_uses_provider_native_session_model(
    tmp_path: Path,
) -> None:
    session_id = "claude-session-1"
    projects_root = tmp_path / ".claude" / "projects"
    transcript_path = projects_root / "project-a" / f"{session_id}.jsonl"
    _write_claude_session(
        transcript_path,
        session_id=session_id,
        user_text="discovery user",
        assistant_text="discovery assistant",
    )

    from agentos.claude.session import ClaudeSession, discover_claude_sessions

    sessions = discover_claude_sessions(targets=(projects_root,))

    assert len(sessions) == 1
    assert isinstance(sessions[0], ClaudeSession)
    assert sessions[0].native_session_id == session_id
    assert sessions[0].artifact_paths == (transcript_path,)
    assert sessions[0].source_kind == "project"


def test_copilot_session_model_uses_provider_native_session_input(
    tmp_path: Path,
) -> None:
    session_id = "d1d3f48b-4b29-4dfc-b551-5536b9677225"
    events_path = tmp_path / "session-state" / session_id / "events.jsonl"
    session_payload = {
        "provider": "copilot-cli",
        "session_id": session_id,
        "updated_at": "2026-03-25T01:05:38Z",
        "primary_backing_artifact": {
            "role": "transcript",
            "storage_kind": "file",
            "path": str(events_path),
        },
        "backing_artifacts": [
            {
                "role": "transcript",
                "storage_kind": "file",
                "path": str(events_path),
            }
        ],
    }
    sources = [
        {
            "source_ref_id": "source-1",
            "role": "transcript",
            "storage_kind": "file",
            "path": str(events_path),
        }
    ]

    from agentos.copilot.session import CopilotSession

    copilot_session = CopilotSession.from_chatlas_session_payload(
        session_payload,
        sources=sources,
    )

    assert copilot_session is not None
    assert copilot_session.native_session_id == session_id
    assert copilot_session.events_path == events_path
    assert copilot_session.source_ref_id == "source-1"
    assert copilot_session.updated_at is not None


def test_pi_session_discovery_uses_provider_native_session_model(
    tmp_path: Path,
) -> None:
    session_id = "019d9cde-0ff5-75a6-b36d-c11a19c2e1b4"
    pi_home = tmp_path / ".pi" / "profiles" / "codex-mm"
    transcript_path = (
        pi_home
        / "sessions"
        / "--Users-pereiro-projects-agentos-project-agentos-iterante-dev--"
        / f"2026-04-17T19-14-52-021Z_{session_id}.jsonl"
    )
    _write_pi_session(transcript_path, session_id=session_id, include_custom_message=True)

    from agentos.pi.session import PiSession, discover_pi_sessions

    sessions = discover_pi_sessions(targets=(pi_home / "sessions",))

    assert len(sessions) == 1
    assert isinstance(sessions[0], PiSession)
    assert sessions[0].native_session_id == session_id
    assert sessions[0].artifact_paths == (transcript_path,)
    assert sessions[0].cwd == "/Users/pereiro/projects/agentos-project/agentos-iterante-dev"
    assert sessions[0].model_provider == "openai-codex"
    assert sessions[0].model_id == "gpt-5.4-mini"
    assert sessions[0].thinking_level == "medium"


def test_opencode_session_discovery_uses_provider_native_session_model(
    tmp_path: Path,
) -> None:
    session_id = "ses_3db2f3c9f0e34924a7d7"
    opencode_home = tmp_path / ".local" / "share" / "opencode"
    db_path = opencode_home / "opencode.db"
    diff_path = opencode_home / "storage" / "session_diff" / f"{session_id}.json"
    connection = _write_opencode_db(db_path, session_id=session_id)
    connection.close()
    _write(diff_path, "[]\n")

    from agentos.opencode.session import OpencodeSession, discover_opencode_sessions

    sessions = discover_opencode_sessions(
        targets=(diff_path.parent,),
        sqlite_db_paths=(db_path,),
    )

    assert len(sessions) == 1
    assert isinstance(sessions[0], OpencodeSession)
    assert sessions[0].native_session_id == session_id
    assert sessions[0].diff_path == diff_path
    assert sessions[0].sqlite_db_path == db_path


def test_gemini_session_discovery_uses_provider_native_session_model(
    tmp_path: Path,
) -> None:
    session_id = "session-gemini-1"
    gemini_home = tmp_path / ".gemini"
    transcript_path = gemini_home / "tmp" / "chats" / "session-20260508.json"
    _write(
        transcript_path,
        json.dumps(
            {
                "sessionId": session_id,
                "lastUpdated": "2026-05-08T12:00:00Z",
            }
        )
        + "\n",
    )

    from agentos.gemini.session import GeminiSession, discover_gemini_sessions

    sessions = discover_gemini_sessions(targets=(gemini_home,))

    assert len(sessions) == 1
    assert isinstance(sessions[0], GeminiSession)
    assert sessions[0].native_session_id == session_id
    assert sessions[0].artifact_paths == (transcript_path,)
    assert sessions[0].updated_at is not None


def test_openclaw_session_discovery_uses_provider_native_session_model(
    tmp_path: Path,
) -> None:
    session_id = "9ce6dc88-dd77-4ea1-9c6b-2c4e9fd5d401"
    session_key = "agent:main:telegram:direct:734641842"
    transcript_path = _write_openclaw_session(
        tmp_path / ".openclaw" / "agents" / "main" / "sessions",
        session_id=session_id,
        session_key=session_key,
    )

    from agentos.openclaw.session import OpenclawSession, discover_openclaw_sessions, find_openclaw_sessions

    sessions = discover_openclaw_sessions(targets=(tmp_path / ".openclaw" / "agents",))
    matching_sessions = find_openclaw_sessions(
        targets=(tmp_path / ".openclaw" / "agents",),
        query=session_key,
    )

    assert len(sessions) == 1
    assert isinstance(sessions[0], OpenclawSession)
    assert sessions[0].native_session_id == session_id
    assert sessions[0].transcript_path == transcript_path.resolve()
    assert sessions[0].sessions_index_path == transcript_path.with_name("sessions.json").resolve()
    assert sessions[0].session_keys == (session_key,)
    assert sessions[0].agent_id == "main"
    assert matching_sessions == sessions


def test_chatlas_export_loads_claude_raw_session(
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
                "chatlas", "export",
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
    assert _without_native(payload["chat"]["messages"]) == _without_native([
        {
            "message_id": "message-1",
            "role": "user",
            "visibility": "conversation",
            "content": [{"type": "text", "text": "claude experimental user"}],
            "native": {
                "record_index": 1,
                "line": 1,
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
            },
            "timestamp": "2026-04-18T11:00:01.000Z",
            "source_refs": [{"source_ref_id": "source-1", "record_index": 2, "line": 2}],
        },
    ])
    assert payload["chat"]["model_runs"] == []
    assert payload["chat"]["tool_invocations"] == []
    events = payload["chat"]["events"]
    assert [event["event_id"] for event in events] == ["event-1", "event-2"]
    assert [event["sequence"] for event in events] == [1, 2]
    assert all("type" not in event for event in events)
    assert all("native" not in event for event in events)
    assert [event["kind"] for event in events] == ["message", "message"]
    assert [event["producer"] for event in events] == [
        {"type": "user"},
        {"type": "assistant"},
    ]
    assert [event["interaction_ref"] for event in events] == [
        "interaction-1",
        "interaction-1",
    ]
    assert [event["surfaces"]["transcript"] for event in events] == [
        "visible",
        "visible",
    ]
    assert "data" not in events[0]
    assert events[0]["payload"] == {
        "role": "user",
        "content": [{"type": "text", "text": "claude experimental user"}],
    }
    assert events[1]["parent_uuid"] == "msg-user-1"
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
        "claude raw session messages projected from canonical events: 2 messages"
        in payload["normalization"]["warnings"]
    )
    assert (
        "claude raw session semantic events normalized from raw records: 2 events"
        in payload["normalization"]["warnings"]
    )
    assert (
        "claude raw session normalization covers messages, events, tool invocations, model runs, reasoning, and usage"
        in payload["normalization"]["warnings"]
    )


def test_chatlas_export_normalizes_claude_tool_invocations(
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
                "chatlas", "export",
                session_id,
                "--provider",
                "claude-code",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert len(payload["chat"]["messages"]) == 2
    assert _without_native(payload["chat"]["model_runs"]) == _without_native([
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
    ])
    assert _without_native(payload["chat"]["tool_invocations"]) == _without_native([
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
    ])
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

    assert (
        main(
            [
                "chatlas",
                "export",
                session_id,
                "--provider",
                "claude-code",
                "--view",
                "replay",
            ]
        )
        == 0
    )
    replay_payload = json.loads(capsys.readouterr().out)
    assert replay_payload["view"] == "replay"
    assert len(replay_payload["chat"]["messages"]) == 2
    assert len(replay_payload["chat"]["tool_invocations"]) == 1
    assert [event["kind"] for event in replay_payload["chat"]["events"]] == [
        "message",
        "message",
        "tool.call",
        "tool.progress",
        "tool.result",
        "tool.progress",
    ]
    assert "output" not in replay_payload["chat"]["tool_invocations"][0]
    assert "result" not in replay_payload["chat"]["tool_invocations"][0]
    assert replay_payload["chat"]["usage"] == []


def test_chatlas_export_normalizes_claude_model_runs(
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
                "chatlas", "export",
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

    assert _without_native(payload["chat"]["model_runs"]) == _without_native([
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
    ])
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


def test_chatlas_export_normalizes_claude_reasoning_and_usage(
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
                "chatlas", "export",
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
        "events": 10,
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
            "raw_canonical_candidate_count": 10,
            "raw_progress_count": 2,
            "normalized_count": 10,
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
    assert _without_native(model_runs[0]["reasoning_trace"]) == _without_native([
        {
            "reasoning_id": "reasoning-1-1",
            "visibility": "visible",
            "content": "inspect repository layout before replying",
            "native": {
                "record_index": 2,
                "line": 2,
                "content_index": 1,
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
    ])
    assert _without_native(payload["chat"]["usage"]) == _without_native([
        {
            "usage_id": "usage-1",
            "scope": "model_run",
            "provider": "claude-code",
            "native": {"record_index": 3, "line": 3},
            "model": "claude-opus-4-6",
            "model_run_ref": "model-run-1",
            "input_tokens": 10,
            "output_tokens": 20,
            "cache_read_tokens": 7,
            "cache_write_tokens": 5,
            "request_count": 1,
            "timestamp": "2026-04-18T11:00:02.000Z",
            "source_refs": [
                {"source_ref_id": "source-1", "record_index": 3, "line": 3}
            ],
        },
        {
            "usage_id": "usage-2",
            "scope": "model_run",
            "provider": "claude-code",
            "native": {"record_index": 7, "line": 7},
            "model": "claude-opus-4-6",
            "model_run_ref": "model-run-2",
            "input_tokens": 14,
            "output_tokens": 7,
            "cache_read_tokens": 11,
            "cache_write_tokens": 2,
            "request_count": 1,
            "timestamp": "2026-04-18T11:00:02.800Z",
            "source_refs": [
                {"source_ref_id": "source-1", "record_index": 7, "line": 7}
            ],
        },
    ])
    assert (
        "claude raw session reasoning normalized from thinking blocks: 1 entries"
        in payload["normalization"]["warnings"]
    )
    assert (
        "claude raw session usage projected from canonical usage events: 2 records"
        in payload["normalization"]["warnings"]
    )
    assert (
        "claude raw session normalization covers messages, events, tool invocations, model runs, reasoning, and usage"
        in payload["normalization"]["warnings"]
    )


def test_chatlas_export_loads_copilot_raw_events(
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
                "chatlas", "export",
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
        "events": 15,
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
        "shutdown_usage_event_count": 1,
        "semantic_event_candidate_count": 15,
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
        "raw_semantic_candidate_count": 15,
        "normalized_count": 15,
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
    assert all("type" not in event for event in events)
    assert all("native" not in event for event in events)
    assert [event["sequence"] for event in events] == list(range(1, 16))
    assert [event["kind"] for event in events] == [
        "session.start",
        "session.update",
        "context",
        "message",
        "run.start",
        "message",
        "reasoning",
        "reasoning",
        "reasoning",
        "tool.call",
        "tool.progress",
        "tool.result",
        "run.end",
        "session.end",
        "usage",
    ]
    assert [event["interaction_ref"] for event in events] == [
        "session",
        "session",
        "session",
        "interaction-1",
        "interaction-1",
        "interaction-1",
        "interaction-1",
        "interaction-1",
        "interaction-1",
        "interaction-1",
        "interaction-1",
        "interaction-1",
        "interaction-1",
        "session",
        "session",
    ]
    assert events[0]["producer"] == {"type": "provider"}
    assert all("data" not in event for event in events)
    assert events[0]["timestamp"] == "2026-04-18T11:00:00.000Z"
    assert events[11]["outcome"] == "ok"
    assert events[12]["outcome"] == "ok"
    assert events[13]["outcome"] == "ok"
    assert events[4]["turn_id"] == "0"
    assert events[6]["payload"] == {
        "visibility": "visible",
        "content": "check repository state",
    }
    assert events[9]["payload"] == {
        "call_id": "tool-call-1",
        "tool_name": "shell",
        "input": {"arguments": {"cmd": "git status"}},
    }
    assert events[9]["call_id"] == "tool-call-1"
    assert events[9]["tool_invocation_ref"] == "tool-invocation-1"
    assert events[11]["payload"] == {
        "call_id": "tool-call-1",
        "success": True,
        "model": "gpt-4.1",
        "interaction_id": "copilot-interaction-1",
        "output": {
            "content": "On branch main",
            "detailed_content": "On branch main\nnothing to commit, working tree clean",
        },
    }
    assert events[11]["call_id"] == "tool-call-1"
    assert events[11]["tool_invocation_ref"] == "tool-invocation-1"
    messages = payload["chat"]["messages"]
    assert [message["role"] for message in messages] == ["system", "user", "assistant"]
    assert [message["visibility"] for message in messages] == [
        "context",
        "conversation",
        "conversation",
    ]
    assert messages[0]["content"] == [{"type": "text", "text": "copilot system prompt"}]
    assert _native_paths(messages, path="messages") == []
    assert messages[0]["source_refs"] == [
        {"source_ref_id": "source-1", "event_index": 3, "line": 3}
    ]
    assert messages[1]["content"] == [
        {"type": "text", "text": "copilot experimental user"}
    ]
    assert messages[1]["source_refs"] == [
        {"source_ref_id": "source-1", "event_index": 4, "line": 4}
    ]
    assert messages[2]["content"] == [
        {"type": "text", "text": "copilot experimental assistant"}
    ]
    assert messages[2]["source_refs"] == [
        {"source_ref_id": "source-1", "event_index": 6, "line": 6}
    ]
    tool_invocations = payload["chat"]["tool_invocations"]
    assert "interaction_id" not in tool_invocations[0]
    assert _without_native(tool_invocations) == _without_native([
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
                    "call_id": "tool-call-1",
                    "tool_name": "shell",
                    "input": {"arguments": {"cmd": "git status"}},
                },
                "execution_start": {
                    "phase": "start",
                    "tool_name": "shell",
                    "input": {"arguments": {"cmd": "git status"}},
                    "interaction_id": "copilot-interaction-1",
                    "call_id": "tool-call-1",
                },
                "execution_complete": {
                    "success": True,
                    "model": "gpt-4.1",
                    "interaction_id": "copilot-interaction-1",
                    "output": {
                        "content": "On branch main",
                        "detailed_content": "On branch main\nnothing to commit, working tree clean",
                    },
                    "call_id": "tool-call-1",
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
                {
                    "source_ref_id": "source-1",
                    "event_index": 6,
                    "line": 6,
                    "request_index": 1,
                },
                {"source_ref_id": "source-1", "event_index": 7, "line": 7},
                {"source_ref_id": "source-1", "event_index": 8, "line": 8},
            ],
            "event_refs": ["event-10", "event-11", "event-12"],
        }
    ])
    assert _without_native(payload["chat"]["usage"]) == _without_native([
        {
            "usage_id": "usage-1",
            "scope": "session",
            "provider": "copilot-cli",
            "model": "gpt-4.1",
            "native": {
                "event_index": 10,
                "line": 10,
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
    ])
    assert "interaction_id" not in payload["chat"]["model_runs"][0]
    assert _without_native(payload["chat"]["model_runs"]) == _without_native([
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
                "turn_end_event_index": 9,
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
                "event-10",
                "event-11",
                "event-12",
                "event-13",
            ],
            "reasoning_trace": [
                {
                    "reasoning_id": "reasoning-1-1",
                    "visibility": "visible",
                    "content": "check repository state",
                    "native": {
                        "event_index": 6,
                        "line": 6,
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
                        "event_index": 6,
                        "line": 6,
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
                        "event_index": 6,
                        "line": 6,
                    },
                    "timestamp": "2026-04-18T11:00:02.000Z",
                    "source_refs": [
                        {"source_ref_id": "source-1", "event_index": 6, "line": 6}
                    ],
                },
            ],
        }
    ])
    assert (
        "copilot raw events parsed for future normalization: 10 events"
        in payload["normalization"]["warnings"]
    )
    assert (
        "copilot raw events semantic events normalized from events.jsonl: 15 events"
        in payload["normalization"]["warnings"]
    )
    assert (
        "copilot raw events messages projected from canonical events: 3 messages"
        in payload["normalization"]["warnings"]
    )
    assert (
        "copilot raw events tool invocations projected from canonical events by toolCallId: 1 invocations"
        in payload["normalization"]["warnings"]
    )
    assert (
        "copilot raw events model runs projected from canonical events: 1 runs"
        in payload["normalization"]["warnings"]
    )
    assert (
        "copilot raw events usage projected from canonical usage events: 1 records"
        in payload["normalization"]["warnings"]
    )

    assert (
        main(
            [
                "chatlas",
                "export",
                session_id,
                "--provider",
                "copilot-cli",
                "--view",
                "transcript",
            ]
        )
        == 0
    )
    transcript_payload = json.loads(capsys.readouterr().out)
    assert transcript_payload["view"] == "transcript"
    assert [message["role"] for message in transcript_payload["chat"]["messages"]] == [
        "user",
        "assistant",
    ]
    assert transcript_payload["chat"]["model_runs"] == []
    assert transcript_payload["chat"]["tool_invocations"] == []
    assert [event["kind"] for event in transcript_payload["chat"]["events"]] == [
        "message",
        "message",
    ]
    assert transcript_payload["chat"]["usage"] == []

    assert (
        main(
            [
                "chatlas",
                "export",
                session_id,
                "--provider",
                "copilot-cli",
                "--view",
                "zip-transcript",
            ]
        )
        == 0
    )
    zip_payload = json.loads(capsys.readouterr().out)
    assert zip_payload["view"] == "zip-transcript"
    assert set(zip_payload) == {"class", "schema_version", "session", "chat", "view"}
    assert set(zip_payload["chat"]) == {"messages"}
    assert [message["role"] for message in zip_payload["chat"]["messages"]] == [
        "user",
        "assistant",
    ]
    assert all(
        block["type"] == "text"
        for message in zip_payload["chat"]["messages"]
        for block in message["content"]
    )


def test_chatlas_zip_transcript_filters_non_text_copilot_message_content(
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
        include_assistant_image=True,
    )

    assert main(_chatlas_update_argv("--provider", "copilot-cli")) == 0
    _ = json.loads(capsys.readouterr().out)

    assert (
        main(
            [
                "chatlas",
                "export",
                session_id,
                "--provider",
                "copilot-cli",
                "--view",
                "zip-transcript",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert all(
        block["type"] == "text"
        for message in payload["chat"]["messages"]
        for block in message["content"]
    )
    assert payload["chat"]["messages"][1]["content"] == [
        {"type": "text", "text": "copilot experimental assistant"}
    ]
    serialized = json.dumps(payload, sort_keys=True)
    assert "reasoningOpaque" not in serialized
    assert "encryptedContent" not in serialized
    assert '"type": "image"' not in serialized


def test_chatlas_export_errors_for_missing_provider_normalizer(
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

    assert main(["chatlas", "export", session_id, "--provider", "pi"]) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert (
        "chatlas export has no provider-specific raw normalizer "
        "for provider pi"
    ) in captured.err


def test_chatlas_export_reference_samples_match_current_semantic_contract(
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
    _copy_chatlas_reference_session_samples(home)

    assert (
        main(
            _chatlas_update_argv(
                "--provider",
                "codex",
                "--provider",
                "claude-code",
                "--provider",
                "copilot-cli",
                verbose_mode="quiet",
            )
        )
        == 0
    )
    _ = json.loads(capsys.readouterr().out)

    reference_expectations = [
        {
            "provider": "claude-code",
            "session_id": _REFERENCE_CLAUDE_SESSION_ID,
            "expected_counts": {
                "messages": 3,
                "model_runs": 4,
                "tool_invocations": 9,
                "events": 53,
                "usage": 12,
                "reasoning_traces": 1,
            },
            "expected_kinds": {
                "message",
                "metric",
                "reasoning",
                "tool.call",
                "tool.progress",
                "tool.result",
                "usage",
            },
            "expected_unsupported_concepts": [],
            "expected_deferred_concepts": [],
            "expected_coverage_statuses": {
                "messages": "normalized",
                "model_runs": "normalized",
                "tool_invocations": "normalized",
                "events": "normalized",
                "reasoning": "normalized",
                "usage": "normalized",
            },
        },
        {
            "provider": "copilot-cli",
            "session_id": _REFERENCE_COPILOT_SESSION_ID,
            "expected_counts": {
                "messages": 4,
                "model_runs": 3,
                "tool_invocations": 2,
                "events": 25,
                "usage": 1,
                "reasoning_traces": 5,
            },
            "expected_kinds": {
                "context",
                "message",
                "reasoning",
                "run.end",
                "run.start",
                "session.end",
                "session.start",
                "session.update",
                "tool.call",
                "tool.progress",
                "tool.result",
                "usage",
            },
            "expected_unsupported_concepts": [],
            "expected_deferred_concepts": [],
            "expected_coverage_statuses": {
                "messages": "normalized",
                "model_runs": "normalized",
                "tool_invocations": "normalized",
                "events": "normalized",
                "reasoning": "normalized",
                "usage": "normalized",
                "cost": "normalized",
            },
        },
        {
            "provider": "codex",
            "session_id": _REFERENCE_CODEX_SESSION_ID,
            "expected_counts": {
                "messages": 7,
                "model_runs": 1,
                "tool_invocations": 45,
                "events": 163,
                "usage": 0,
                "reasoning_traces": 7,
            },
            "expected_kinds": {
                "context",
                "message",
                "metric",
                "reasoning",
                "run.end",
                "run.start",
                "session.start",
                "tool.call",
                "tool.progress",
                "tool.result",
            },
            "expected_unsupported_concepts": ["usage"],
            "expected_deferred_concepts": ["usage"],
            "expected_coverage_statuses": {
                "messages": "normalized",
                "model_runs": "normalized",
                "tool_invocations": "normalized",
                "events": "normalized",
                "reasoning": "normalized",
                "usage": "event_only",
                "cost": "no_raw_evidence",
            },
        },
    ]

    for expectation in reference_expectations:
        provider = expectation["provider"]
        session_id = expectation["session_id"]
        assert isinstance(provider, str)
        assert isinstance(session_id, str)
        assert (
            main(
                [
                    "chatlas", "export",
                    session_id,
                    "--provider",
                    provider,
                    "--format",
                    "json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        _assert_current_reference_session_quality(payload, **expectation)


def test_chatlas_export_reports_invalid_codex_raw_lines(
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

    assert main(["chatlas", "export", thread_name, "--provider", "codex"]) == 0
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


def test_chatlas_export_preserves_codex_context_messages(
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

    assert main(["chatlas", "export", thread_name, "--provider", "codex"]) == 0
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
        }
    ]
    assert _native_paths(messages, path="messages") == []
    assert any(
        "content item 1 has unsupported type custom_payload" in warning
        for warning in payload["normalization"]["warnings"]
    )


def test_chatlas_export_joins_codex_tool_invocations(
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

    assert main(["chatlas", "export", thread_name, "--provider", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["normalization"]["source_mode"] == "codex_raw_rollout"
    assert payload["normalization"]["unsupported_concepts"] == ["usage"]
    assert payload["normalization"]["deferred_concepts"] == ["usage"]
    assert payload["normalization"]["counts"] == {
        "messages": 1,
        "model_runs": 1,
        "tool_invocations": 2,
        "events": 8,
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
        "raw_semantic_candidate_count": 8,
        "parse_warning_count": 0,
    }
    assert payload["normalization"]["coverage"]["events"] == {
        "status": "normalized",
        "raw_count": 8,
        "normalized_count": 8,
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
        "codex raw rollout semantic events normalized: 8 events"
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
    assert complete["event_refs"] == ["event-5", "event-6", "event-7"]
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
    assert "native" not in complete

    assert incomplete["tool_invocation_id"] == "tool-invocation-2"
    assert incomplete["call_id"] == "call-incomplete"
    assert incomplete["status"] == "requested"
    assert incomplete["event_refs"] == ["event-8"]
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
    assert not any("data" in event for event in events)
    assert not any("type" in event for event in events)
    assert not any("native" in event for event in events)
    assert [event["sequence"] for event in events] == list(range(1, 9))
    assert [event["kind"] for event in events] == [
        "session.start",
        "run.start",
        "metric",
        "message",
        "tool.call",
        "tool.result",
        "tool.progress",
        "tool.call",
    ]
    assert [event["interaction_ref"] for event in events] == [
        "session",
        "interaction-1",
        "interaction-1",
        "interaction-1",
        "interaction-1",
        "interaction-1",
        "interaction-1",
        "interaction-1",
    ]
    assert "outcome" not in events[1]
    assert events[1]["timestamp"] == "2026-03-08T01:08:59.090Z"
    assert events[1]["turn_id"] == "turn-1"
    assert events[1]["payload"] == {
        "turn_id": "turn-1",
        "started_at": 1772946539,
        "model_context_window": 258400,
        "collaboration_mode_kind": "default",
    }
    assert events[2]["event_id"] == "event-3"
    assert events[2]["payload"]["info"]["total_token_usage"]["total_tokens"] == 12
    assert events[4]["event_id"] == "event-5"
    assert events[4]["kind"] == "tool.call"
    assert events[4]["call_id"] == "call-complete"
    assert events[4]["tool_invocation_ref"] == "tool-invocation-1"
    assert events[4]["payload"]["input"] == {
        "arguments": {
            "cmd": "pwd",
            "workdir": "/tmp",
        }
    }
    assert events[5]["event_id"] == "event-6"
    assert events[5]["kind"] == "tool.result"
    assert events[5]["outcome"] == "ok"
    assert events[5]["payload"] == {
        "result_source": "model_input",
        "call_id": "call-complete",
        "content": "Chunk ID: abc\nOutput:\n/tmp\n",
    }
    assert events[6]["event_id"] == "event-7"
    assert events[6]["kind"] == "tool.progress"
    assert events[6]["outcome"] == "ok"
    assert events[6]["call_id"] == "call-complete"
    assert events[6]["turn_id"] == "turn-1"
    assert events[6]["tool_invocation_ref"] == "tool-invocation-1"
    assert events[6]["surfaces"]["model_input"] == "hidden"
    assert events[6]["payload"]["duration"] == 1.25
    assert events[6]["payload"]["aggregated_output"] == "/tmp\n"
    assert events[6]["source_refs"] == [
        {"source_ref_id": "source-1", "record_index": 7, "line": 7}
    ]


def test_chatlas_export_normalizes_codex_model_runs(
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

    assert main(["chatlas", "export", thread_name, "--provider", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["normalization"]["source_mode"] == "codex_raw_rollout"
    assert payload["normalization"]["unsupported_concepts"] == []
    assert payload["normalization"]["deferred_concepts"] == []
    assert payload["normalization"]["counts"] == {
        "messages": 1,
        "model_runs": 1,
        "tool_invocations": 1,
        "events": 9,
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
        "raw_semantic_candidate_count": 9,
        "parse_warning_count": 0,
    }
    assert payload["normalization"]["coverage"]["events"] == {
        "status": "normalized",
        "raw_count": 9,
        "normalized_count": 9,
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
    assert not any("data" in event for event in payload["chat"]["events"])
    assert [event["kind"] for event in payload["chat"]["events"]] == [
        "session.start",
        "context",
        "run.start",
        "message",
        "reasoning",
        "tool.call",
        "tool.result",
        "tool.progress",
        "run.end",
    ]
    assert payload["chat"]["events"][1]["payload"]["context_type"] == "turn_context"
    assert "user_instructions" not in json.dumps(payload["chat"]["events"][1]["payload"])
    assert "summary" not in json.dumps(payload["chat"]["events"][1]["payload"])

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
    assert model_run["event_refs"] == [
        "event-2",
        "event-3",
        "event-4",
        "event-5",
        "event-6",
        "event-7",
        "event-8",
        "event-9",
    ]
    assert "native" not in model_run
    assert model_run["source_refs"] == [
        {"source_ref_id": "source-1", "record_index": 2, "line": 2}
    ]

    reasoning_trace = model_run["reasoning_trace"]
    assert _without_native(reasoning_trace) == _without_native([
        {
                "reasoning_id": "reasoning-1",
                "visibility": "encrypted",
                "native": {
                    "record_index": 5,
                    "line": 5,
                    "summary": [{"type": "summary_text", "text": "check context"}],
                },
            "timestamp": "2026-03-08T01:09:02.000Z",
            "content": "encrypted-reasoning",
            "source_refs": [
                {"source_ref_id": "source-1", "record_index": 5, "line": 5}
            ],
        }
    ])


def test_chatlas_export_attaches_codex_multi_turn_model_runs(
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

    assert main(["chatlas", "export", thread_name, "--provider", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["normalization"]["counts"] == {
        "messages": 4,
        "model_runs": 2,
        "tool_invocations": 0,
        "events": 13,
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
    assert payload["normalization"]["coverage"]["events"] == {
        "status": "normalized",
        "raw_count": 13,
        "normalized_count": 13,
    }
    assert not any("data" in event for event in payload["chat"]["events"])

    first_run, second_run = payload["chat"]["model_runs"]
    assert first_run["turn_id"] == "turn-1"
    assert first_run["message_refs"] == ["message-1", "message-2"]
    assert first_run["event_refs"] == [
        "event-2",
        "event-3",
        "event-4",
        "event-5",
        "event-6",
        "event-7",
    ]
    assert [entry["content"] for entry in first_run["reasoning_trace"]] == [
        "first turn reasoning"
    ]
    assert "native" not in first_run
    assert first_run["source_refs"] == [
        {"source_ref_id": "source-1", "record_index": 2, "line": 2}
    ]

    assert second_run["turn_id"] == "turn-2"
    assert second_run["message_refs"] == ["message-3", "message-4"]
    assert second_run["event_refs"] == [
        "event-8",
        "event-9",
        "event-10",
        "event-11",
        "event-12",
        "event-13",
    ]
    assert [entry["content"] for entry in second_run["reasoning_trace"]] == [
        "second turn reasoning"
    ]
    assert "native" not in second_run
    assert second_run["source_refs"] == [
        {"source_ref_id": "source-1", "record_index": 8, "line": 8}
    ]

    assert not any(
        warning.startswith("codex reasoning records could not be attached to a model run:")
        for warning in payload["normalization"]["warnings"]
    )
