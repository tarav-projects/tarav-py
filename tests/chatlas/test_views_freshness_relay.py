# $kw: ^test-views-freshness-relay --from Workflow.Update --note [CT] downstream view freshness is checked and repaired by the owning workflow rather than the update pipeline ^c20260714-2u --supp static cleanup authorized ^c20260730-34u
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.testing import TaravTestEnvironment
from tarav.cli.cli import main
from tarav.chatlas.query import chatlas_query
from tarav.chatlas.session_cache import (
    load_chatlas_session_model,
    session_model_cache_path,
)

from .test_tape_provenance import (
    _closed_turn_records,
    _open_turn_records,
    _second_closed_turn_records,
)

SESSION_ID = "0195cafb-aaaa-7000-bbbb-000000000001"


def _claude_records(records: list[dict]) -> list[dict]:
    return [{**record, "sessionId": SESSION_ID} for record in records]


def _write_claude_session(claude_home: Path, records: list[dict]) -> Path:
    path = claude_home / "projects" / "-tmp-relay" / f"{SESSION_ID}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in _claude_records(records)),
        encoding="utf-8",
    )
    return path


def _isolate_claude(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    claude_home = tmp_path / "claude-home"
    environment.write_global_config(
        chatlas={"sources": [{"provider": "claude-code", "home": str(claude_home)}]}
    )
    return claude_home


def _session_row() -> dict:
    result = chatlas_query(
        providers=("claude-code",), session_id=SESSION_ID, row_shape="full"
    )
    return result["rows"][0]


def _cached_model() -> dict:
    return load_chatlas_session_model(_session_row())


def test_update_relays_staleness_to_views_without_touching_caches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workflow.Update [CT]: the update pipeline never touches view caches — a
    stale artifact is detected by the view's own read-time freshness check and
    re-derived on demand, resuming through Delta.Normalization::Chatlas."""
    claude_home = _isolate_claude(monkeypatch, tmp_path)
    base = _closed_turn_records() + _second_closed_turn_records()
    _write_claude_session(claude_home, base)

    assert main(["chatlas", "update", "--provider", "claude-code", "--quiet"]) == 0

    head = _cached_model()
    assert head["normalization"]["derivation"] == "full"
    artifact_dir = session_model_cache_path(_session_row())
    assert (artifact_dir / "events.jsonl").is_file()

    # the session grows; a scoped update refreshes archive + index row
    _write_claude_session(claude_home, base + _open_turn_records(parent="a6"))
    assert main([
        "chatlas", "update",
        "--provider", "claude-code",
        "--session-id", SESSION_ID,
        "--quiet",
    ]) == 0

    # the update left the view cache alone — the stale artifact survives as
    # the delta resume base
    assert (artifact_dir / "session.json").is_file()
    assert (artifact_dir / "events.jsonl").is_file()

    # the next read detects staleness by fingerprint and re-produces via delta
    head = _cached_model()
    assert head["normalization"]["derivation"] == "delta"
    assert head["normalization"]["counts"]["events"] > len(base)
