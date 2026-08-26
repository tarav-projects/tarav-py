"""Impl.Req 524: index-row metadata `Raw.Normalizer`s reproduce the session_ref-derived
fields from raw — including the `project_path: null` bug (reproduced in Slice 1, fixed in
Slice 2)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from tarav.agent.session_refs import BackingArtifact

from tarav.chatlas.index_metadata import index_metadata


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _claude_meta(transcript: Path) -> dict:
    return index_metadata(
        "claude-code", (BackingArtifact(role="transcript", path=transcript),)
    )


def _codex_meta(
    transcript: Path,
    *,
    index_path: Path | None = None,
    session_id: str | None = None,
) -> dict:
    artifacts = [BackingArtifact(role="transcript", path=transcript)]
    if index_path is not None:
        artifacts.append(
            BackingArtifact(
                role="session_index",
                path=index_path,
                locator={"match": {"id": session_id}},
            )
        )
    return index_metadata("codex", tuple(artifacts))


def test_claude_leading_mode_record_resolves_project_path(tmp_path: Path) -> None:
    transcript = tmp_path / "sess-abc.jsonl"
    _write_jsonl(
        transcript,
        [
            {"type": "mode", "sessionId": "sess-abc"},
            {"type": "user", "sessionId": "sess-abc", "cwd": "/Users/x/proj",
             "timestamp": "2024-01-01T00:00:00Z"},
        ],
    )
    meta = _claude_meta(transcript)
    # Slice 2 fix: project_path scans for the first record carrying a cwd (the leading
    # `mode` record has none), instead of taking record 0 -> the real cwd, not null.
    assert meta["project_path"] == "/Users/x/proj"
    # native still mirrors the raw first record (record 0 has no cwd) — only project_path moves.
    assert meta["native"] == {}
    assert meta["display_name"] is None
    assert meta["display_name_field"] is None
    assert isinstance(meta["last_activity_at"], str)


def test_claude_first_record_cwd_populates_project_path(tmp_path: Path) -> None:
    transcript = tmp_path / "sess-def.jsonl"
    _write_jsonl(
        transcript,
        [
            {"type": "user", "sessionId": "sess-def", "cwd": "/Users/x/proj",
             "timestamp": "2024-01-01T00:00:00Z"},
        ],
    )
    meta = _claude_meta(transcript)
    assert meta["project_path"] == "/Users/x/proj"
    assert meta["native"] == {"cwd": "/Users/x/proj"}


def test_unknown_provider_returns_none(tmp_path: Path) -> None:
    # Providers without index-row normalizers fall back to the session_ref path.
    assert index_metadata("gemini-cli", ()) is None


def test_codex_timestamps_use_oldest_created_and_newest_activity_candidates(tmp_path: Path) -> None:
    transcript = tmp_path / "rollout.jsonl"
    index_path = tmp_path / "session_index.jsonl"
    _write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-03-08T01:00:00.000Z",
                "type": "session_meta",
                "payload": {
                    "id": "sess-codex",
                    "timestamp": "2026-03-08T00:59:59.000Z",
                    "cwd": "/tmp/project",
                },
            },
            {
                "timestamp": "2026-03-08T01:02:00.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello"}],
                },
            },
            {
                "timestamp": "2026-03-08T01:03:00.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "hi"}],
                },
            },
        ],
    )
    index_path.write_text(
        json.dumps(
            {
                "id": "sess-codex",
                "thread_name": "fixture",
                "updated_at": "2026-03-08T01:05:00.000Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    meta = _codex_meta(transcript, index_path=index_path, session_id="sess-codex")

    assert meta["created_at"] == "2026-03-08T00:59:59.000Z"
    assert meta["last_activity_at"] == "2026-03-08T01:05:00.000Z"


def test_codex_bootstrap_rollout_uses_content_timestamps_without_dialog_turns(tmp_path: Path) -> None:
    transcript = tmp_path / "bootstrap.jsonl"
    _write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-02-10T04:14:37.544Z",
                "type": "session_meta",
                "payload": {
                    "id": "sess-bootstrap",
                    "timestamp": "2026-02-10T04:14:37.518Z",
                    "cwd": "/",
                },
            },
            {
                "timestamp": "2026-02-10T04:14:37.544Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "<permissions instructions>"}],
                },
            },
            {
                "timestamp": "2026-02-10T04:14:38.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "<environment_context>"}],
                },
            },
        ],
    )

    meta = _codex_meta(transcript)

    assert meta["created_at"] == "2026-02-10T04:14:37.518Z"
    assert meta["last_activity_at"] == "2026-02-10T04:14:38.000Z"


def test_claude_dialog_timestamp_contributes_created_at(tmp_path: Path) -> None:
    transcript = tmp_path / "claude-dialog.jsonl"
    _write_jsonl(
        transcript,
        [
            {
                "type": "user",
                "sessionId": "sess-claude",
                "cwd": "/tmp/project",
                "timestamp": "2026-03-08T01:01:00.000Z",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "hello"}],
                },
            }
        ],
    )

    meta = _claude_meta(transcript)

    assert meta["created_at"] == "2026-03-08T01:01:00.000Z"


def test_claude_snapshot_only_uses_nested_content_timestamps(tmp_path: Path) -> None:
    transcript = tmp_path / "claude-snapshot.jsonl"
    _write_jsonl(
        transcript,
        [
            {
                "type": "file-history-snapshot",
                "sessionId": "sess-snapshot",
                "messageId": "one",
                "snapshot": {"timestamp": "2026-03-16T02:58:59.547Z"},
            },
            {
                "type": "file-history-snapshot",
                "sessionId": "sess-snapshot",
                "messageId": "two",
                "snapshot": {"timestamp": "2026-03-16T03:14:01.755Z"},
            },
        ],
    )

    meta = _claude_meta(transcript)

    assert meta["created_at"] == "2026-03-16T02:58:59.547Z"
    assert meta["last_activity_at"] == "2026-03-16T03:14:01.755Z"


def test_claude_system_only_uses_top_level_content_timestamps(tmp_path: Path) -> None:
    transcript = tmp_path / "claude-system.jsonl"
    _write_jsonl(
        transcript,
        [
            {
                "type": "system",
                "sessionId": "sess-system",
                "cwd": "/tmp/project",
                "timestamp": "2026-04-23T20:11:57.119Z",
                "content": "<command-name>/status</command-name>",
            },
            {
                "type": "system",
                "sessionId": "sess-system",
                "cwd": "/tmp/project",
                "timestamp": "2026-04-23T20:12:01.000Z",
                "content": "<local-command-stdout>Status dialog dismissed</local-command-stdout>",
            },
        ],
    )

    meta = _claude_meta(transcript)

    assert meta["created_at"] == "2026-04-23T20:11:57.119Z"
    assert meta["last_activity_at"] == "2026-04-23T20:12:01.000Z"


def test_claude_ai_title_without_timestamp_keeps_created_at_null(tmp_path: Path) -> None:
    transcript = tmp_path / "claude-title.jsonl"
    _write_jsonl(
        transcript,
        [{"type": "ai-title", "aiTitle": "Test agent response format", "sessionId": "sess-title"}],
    )

    meta = _claude_meta(transcript)

    assert meta["created_at"] is None
    assert meta["last_activity_at"] is None


def test_last_activity_ignores_filesystem_mtime(tmp_path: Path) -> None:
    transcript = tmp_path / "mtime.jsonl"
    _write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-03-08T01:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "sess-mtime", "timestamp": "2026-03-08T01:00:00.000Z"},
            }
        ],
    )
    os.utime(transcript, (2_000_000_000, 2_000_000_000))

    meta = _codex_meta(transcript)

    assert meta["last_activity_at"] == "2026-03-08T01:00:00.000Z"
