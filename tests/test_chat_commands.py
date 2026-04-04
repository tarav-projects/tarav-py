from __future__ import annotations

import json
import os
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
