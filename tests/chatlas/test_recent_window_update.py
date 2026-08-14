from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import time
from pathlib import Path

import pytest

from tarav.testing import TaravTestEnvironment
from tarav.cli.cli import main
from ._helpers import captured_json, write_chatlas_codex_source, write_text_file

FRESH_ID = "019ccafa-1111-7000-aaaa-000000000001"
OLD_ID = "019ccafa-2222-7000-aaaa-000000000002"


def _timestamp_text(timestamp: float) -> str:
    return (
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _write_codex_session(
    codex_home: Path,
    *,
    session_id: str,
    timestamp: float,
    text: str,
    in_index: bool = True,
) -> Path:
    timestamp_text = _timestamp_text(timestamp)
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-{session_id}.jsonl"
    events = [
        {
            "timestamp": timestamp_text,
            "type": "session_meta",
            "payload": {"id": session_id, "originator": "codex_cli_rs", "cwd": "/tmp"},
        },
        {
            "timestamp": timestamp_text,
            "type": "turn_context",
            "payload": {"cwd": "/tmp", "title": text},
        },
        {
            "timestamp": timestamp_text,
            "type": "response_item",
            "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]},
        },
    ]
    write_text_file(rollout_path, "\n".join(json.dumps(event) for event in events) + "\n")
    os.utime(rollout_path, (timestamp, timestamp))
    if in_index:
        index_path = codex_home / "session_index.jsonl"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        with index_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"id": session_id, "thread_name": text, "updated_at": timestamp_text}) + "\n")
    return rollout_path


def _isolate_codex(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    codex_home = tmp_path / "codex-home"
    now = time.time()
    _write_codex_session(codex_home, session_id=FRESH_ID, timestamp=now, text="fresh session turn")
    _write_codex_session(
        codex_home,
        session_id=OLD_ID,
        timestamp=now - 30 * 24 * 60 * 60,
        text="old session turn",
        in_index=False,
    )
    write_chatlas_codex_source(environment, codex_home)
    return codex_home


def _query_session_ids(capsys: pytest.CaptureFixture[str]) -> set[str]:
    assert main(["chatlas", "query", "--provider", "codex", "--json"]) == 0
    payload = captured_json(capsys)
    return {row["session_id"] for row in payload.get("rows", []) if isinstance(row, dict)}


def test_recent_window_update_indexes_only_in_window_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate_codex(monkeypatch, tmp_path)

    assert main([
        "chatlas",
        "index",
        "update",
        "--provider",
        "codex",
        "--recent-window",
        "1h",
        "--json",
    ]) == 0
    capsys.readouterr()

    ids = _query_session_ids(capsys)
    assert FRESH_ID in ids
    assert OLD_ID not in ids


def test_full_update_indexes_both_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate_codex(monkeypatch, tmp_path)

    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()

    ids = _query_session_ids(capsys)
    assert FRESH_ID in ids
    assert OLD_ID in ids
