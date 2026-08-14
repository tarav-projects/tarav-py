from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

import pytest

from tarav.testing import TaravTestEnvironment
from tarav.cli.cli import main
from ._helpers import captured_json, read_json_file, write_chatlas_codex_source, write_text_file


def _isolate_chatlas(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[TaravTestEnvironment, Path]:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    codex_home = tmp_path / "codex-home"
    return environment, codex_home


def _configure_chatlas(
    environment: TaravTestEnvironment,
    codex_home: Path,
    *,
    chatlas_config: dict[str, object] | None = None,
) -> None:
    write_chatlas_codex_source(environment, codex_home, chatlas_config=chatlas_config)


def _write_codex_session(
    codex_home: Path,
    *,
    session_id: str,
    timestamp: float,
    text: str = "hello",
) -> Path:
    timestamp_text = _timestamp_text(timestamp)
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-{session_id}.jsonl"
    index_path = codex_home / "session_index.jsonl"
    events = [
        {
            "timestamp": timestamp_text,
            "type": "session_meta",
            "payload": {"id": session_id, "originator": "codex_cli_rs", "cwd": "/tmp"},
        },
        {
            "timestamp": timestamp_text,
            "type": "turn_context",
            "payload": {"cwd": "/tmp", "title": "cold cache source"},
        },
        {
            "timestamp": timestamp_text,
            "type": "response_item",
            "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]},
        },
    ]
    write_text_file(rollout_path, "\n".join(json.dumps(event) for event in events) + "\n")
    write_text_file(
        index_path,
        json.dumps({"id": session_id, "thread_name": "cold cache source", "updated_at": timestamp_text}) + "\n",
    )
    os.utime(rollout_path, (timestamp, timestamp))
    os.utime(index_path, (timestamp, timestamp))
    return rollout_path


def _timestamp_text(timestamp: float) -> str:
    return (
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _cache_entry(payload: dict[str, object], session_id: str) -> dict[str, object]:
    cache_root = Path(str(payload["cache_root"]))
    fingerprint = payload["selection"]["instances"][0]["provider_instance_fingerprint"]  # type: ignore[index]
    cache_path = cache_root / "codex" / str(fingerprint) / "sessions.json"
    return read_json_file(cache_path)["sessions"][session_id]


def test_cold_session_cache_skips_normal_update_and_full_scan_bypasses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    old_timestamp = time.time() - (40 * 24 * 60 * 60)
    rollout_path = _write_codex_session(codex_home, session_id=session_id, timestamp=old_timestamp)
    _configure_chatlas(environment, codex_home)

    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    first_payload = captured_json(capsys)
    first_entry = _cache_entry(first_payload, session_id)
    assert first_entry["scan_state"] == "cold"
    assert isinstance(first_entry["cold_since"], str)
    assert first_payload["cache"]["cold_marked_count"] == 1
    assert first_payload["cache"]["cold_skip_count"] == 0
    assert first_payload["full_scan_enabled"] is False

    _write_codex_session(codex_home, session_id=session_id, timestamp=old_timestamp, text="changed")

    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    skipped_payload = captured_json(capsys)
    skipped_entry = _cache_entry(skipped_payload, session_id)
    assert skipped_payload["cache"]["cold_skip_count"] == 1
    assert skipped_payload["cache"]["miss_count"] == 0
    assert skipped_payload["raw_copy"]["copied_file_count"] == 0
    assert skipped_entry == first_entry
    assert rollout_path.exists()

    assert main([
        "chatlas",
        "index",
        "update",
        "--provider",
        "codex",
        "--full-scan",
        "--json",
    ]) == 0
    full_scan_payload = captured_json(capsys)
    full_scan_entry = _cache_entry(full_scan_payload, session_id)
    assert full_scan_payload["full_scan_enabled"] is True
    assert full_scan_payload["cache"]["full_scan_count"] == 1
    assert full_scan_payload["cache"]["cold_skip_count"] == 0
    assert full_scan_payload["cache"]["miss_count"] == 1
    assert full_scan_payload["raw_copy"]["updated_file_count"] >= 1
    assert full_scan_entry["scan_state"] == "cold"
    assert full_scan_entry["cold_since"] == first_entry["cold_since"]

    recent_timestamp = time.time()
    _write_codex_session(codex_home, session_id=session_id, timestamp=recent_timestamp, text="active again")

    assert main([
        "chatlas",
        "index",
        "update",
        "--provider",
        "codex",
        "--full-scan",
        "--json",
    ]) == 0
    reactivated_payload = captured_json(capsys)
    reactivated_entry = _cache_entry(reactivated_payload, session_id)
    assert reactivated_payload["cache"]["full_scan_count"] == 1
    assert reactivated_payload["cache"]["cold_skip_count"] == 0
    assert reactivated_payload["cache"]["miss_count"] == 1
    assert "scan_state" not in reactivated_entry
    assert "cold_since" not in reactivated_entry


def test_missing_scan_state_is_hot_and_recent_activity_writes_hot_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    recent_timestamp = time.time()
    _write_codex_session(codex_home, session_id=session_id, timestamp=recent_timestamp)
    _configure_chatlas(environment, codex_home)

    assert main(["chatlas", "update", "--provider", "codex", "--json"]) == 0
    first_payload = captured_json(capsys)
    first_entry = _cache_entry(first_payload, session_id)
    assert "scan_state" not in first_entry
    assert first_payload["full_scan_enabled"] is False

    _write_codex_session(codex_home, session_id=session_id, timestamp=recent_timestamp, text="changed")

    assert main(["chatlas", "update", "--provider", "codex", "--json"]) == 0
    changed_payload = captured_json(capsys)
    changed_entry = _cache_entry(changed_payload, session_id)
    assert changed_payload["cache"]["cold_skip_count"] == 0
    assert changed_payload["cache"]["miss_count"] == 1
    assert changed_payload["raw_copy"]["updated_file_count"] >= 1
    assert "scan_state" not in changed_entry


def test_cold_session_cache_uses_configured_default_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    timestamp = time.time() - (40 * 24 * 60 * 60)
    _write_codex_session(codex_home, session_id=session_id, timestamp=timestamp)
    _configure_chatlas(
        environment,
        codex_home,
        chatlas_config={"cold_session_cache": {"cutoff": "45d"}},
    )

    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    payload = captured_json(capsys)
    entry = _cache_entry(payload, session_id)
    assert payload["instances"][0]["cold_session_cutoff_seconds"] == 45 * 24 * 60 * 60
    assert payload["cache"]["cold_marked_count"] == 0
    assert "scan_state" not in entry


def test_cold_session_cache_provider_override_can_shorten_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    timestamp = time.time() - (20 * 24 * 60 * 60)
    _write_codex_session(codex_home, session_id=session_id, timestamp=timestamp)
    _configure_chatlas(
        environment,
        codex_home,
        chatlas_config={
            "cold_session_cache": {
                "cutoff": "30d",
                "providers": {
                    "codex": {"cutoff": "10d"},
                },
            }
        },
    )

    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    payload = captured_json(capsys)
    entry = _cache_entry(payload, session_id)
    assert payload["instances"][0]["cold_session_cutoff_seconds"] == 10 * 24 * 60 * 60
    assert payload["cache"]["cold_marked_count"] == 1
    assert entry["scan_state"] == "cold"
