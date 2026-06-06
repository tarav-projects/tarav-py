from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.agent.account_registry import account_events_path, record_account_event

from _helpers import isolate_agentos, read_jsonl_file


def test_account_events_are_global_provider_tagged_daily_jsonl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, agentos_home = isolate_agentos(monkeypatch, tmp_path)

    record_account_event(
        event_type="account.auth.materialized",
        command="agent.run",
        argv=("agent", "run", "--profile", "codex-mm"),
        status="ok",
        payload={
            "provider": "codex",
            "profile": "codex-mm",
            "home": str(tmp_path / "codex-mm"),
            "account": "mm",
            "artifact_id": "abc123",
            "auth": {"tokens": {"refresh_token": "secret-refresh-token"}},
        },
    )

    event_files = sorted((agentos_home / "accounts" / "events").glob("*.jsonl"))
    assert len(event_files) == 1
    assert event_files[0].name.endswith(".jsonl")
    assert len(event_files[0].stem) == 8
    assert event_files[0].stem.isdigit()
    events = read_jsonl_file(event_files[0])
    assert events == [
        {
            "time": events[0]["time"],
            "event": "account.auth.materialized",
            "provider": "codex",
            "source": "agent.run",
            "argv": ["agent", "run", "--profile", "codex-mm"],
            "status": "ok",
            "profile": "codex-mm",
            "home": str(tmp_path / "codex-mm"),
            "account": "mm",
            "artifact_id": "abc123",
        }
    ]
    serialized = json.dumps(events)
    assert "tokens" not in serialized
    assert "secret-refresh-token" not in serialized


def test_account_events_path_uses_utc_date_from_timestamp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, agentos_home = isolate_agentos(monkeypatch, tmp_path)

    path = account_events_path("2026-06-04T16:22:31Z")

    assert path == agentos_home / "accounts" / "events" / "20260604.jsonl"
