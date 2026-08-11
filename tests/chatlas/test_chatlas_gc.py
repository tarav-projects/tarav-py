from __future__ import annotations

import json
import os
from pathlib import Path
import time

import pytest

from agentos.agent.primitives import AgentConfig, SessionSource
from agentos.agent.providers import agent_from_config
from agentos.testing import AgentosTestEnvironment
from agentos.cli.cli import main
from agentos.chatlas.provider_home_adapter import ChatlasProviderInstance
from agentos.chatlas.gc import _candidates_for_session
from ._helpers import captured_json, write_chatlas_codex_source, write_text_file


def _isolate_chatlas(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[AgentosTestEnvironment, Path]:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    codex_home = tmp_path / "codex-home"
    return environment, codex_home


def _configure_chatlas(environment: AgentosTestEnvironment, codex_home: Path) -> None:
    write_chatlas_codex_source(environment, codex_home)


def _write_codex_rollout(path: Path, *, session_id: str, text: str = "hello") -> None:
    events = [
        {
            "timestamp": "2026-03-08T01:08:59.089Z",
            "type": "session_meta",
            "payload": {"id": session_id, "originator": "codex_cli_rs", "cwd": "/tmp"},
        },
        {
            "timestamp": "2026-03-08T01:09:01.000Z",
            "type": "turn_context",
            "payload": {"cwd": "/tmp", "title": "gc source"},
        },
        {
            "timestamp": "2026-03-08T01:09:02.000Z",
            "type": "response_item",
            "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]},
        },
    ]
    write_text_file(path, "\n".join(json.dumps(event) for event in events) + "\n")


def _make_old(path: Path) -> None:
    old_timestamp = time.time() - (40 * 24 * 60 * 60)
    os.utime(path, (old_timestamp, old_timestamp))


def test_chatlas_gc_dry_run_and_apply_moves_old_archived_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    index_path = codex_home / "session_index.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id)
    write_text_file(index_path, json.dumps({"id": session_id, "thread_name": "gc source"}) + "\n")
    _configure_chatlas(environment, codex_home)

    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    update_payload = captured_json(capsys)
    instance_name = update_payload["selection"]["instances"][0]["instance"]
    _make_old(rollout_path)
    _make_old(index_path)

    assert main([
        "chatlas",
        "gc",
            "--provider",
            "codex",
            "--instance",
            instance_name,
        "--session-id",
        session_id,
        "--json",
        "--verbose-mode",
        "quiet",
    ]) == 0
    dry_run = captured_json(capsys)
    assert dry_run["status"] == "ok"
    assert dry_run["apply"] is False
    assert dry_run["counts"]["candidate_count"] == 1
    assert dry_run["counts"]["moved_count"] == 0
    assert any(row["reason"] == "locator_source" for row in dry_run["skipped"])
    destination_path = Path(dry_run["candidates"][0]["destination_path"])
    write_text_file(destination_path, "stale destination\n")

    assert main([
        "chatlas",
        "gc",
            "--provider",
            "codex",
            "--instance",
            instance_name,
        "--session-id",
        session_id,
        "--apply",
        "--json",
        "--verbose-mode",
        "quiet",
    ]) == 0
    applied = captured_json(capsys)
    chatlas_root = environment.home / "Documents" / "chatlas"
    archived_path = Path(applied["moved"][0]["archived_path"])
    moved_path = Path(applied["moved"][0]["destination_path"])

    assert applied["counts"]["candidate_count"] == 1
    assert applied["counts"]["moved_count"] == 1
    assert not rollout_path.exists()
    assert index_path.exists()
    assert moved_path == destination_path
    assert moved_path.read_text(encoding="utf-8") == archived_path.read_text(encoding="utf-8")
    assert archived_path.exists()
    assert "/gc/" in (chatlas_root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert Path(applied["report_path"]).is_file()

    assert main(["chatlas", "raw", "path", "--session-id", session_id, "--json"]) == 0
    raw_payload = captured_json(capsys)
    assert raw_payload["session"]["session_id"] == session_id
    assert str(archived_path) in raw_payload["paths"]


def test_chatlas_gc_skips_hash_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    index_path = codex_home / "session_index.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id)
    write_text_file(index_path, json.dumps({"id": session_id, "thread_name": "gc source"}) + "\n")
    _configure_chatlas(environment, codex_home)

    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    captured_json(capsys)
    _write_codex_rollout(rollout_path, session_id=session_id, text="changed")
    _make_old(rollout_path)

    assert main([
        "chatlas",
        "gc",
        "--provider",
        "codex",
        "--session-id",
        session_id,
        "--json",
        "--verbose-mode",
        "quiet",
    ]) == 0
    payload = captured_json(capsys)
    assert payload["counts"]["candidate_count"] == 0
    assert any(row["reason"] == "hash_mismatch" for row in payload["skipped"])
    assert rollout_path.exists()


def test_chatlas_gc_keeps_recent_sources_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    index_path = codex_home / "session_index.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id)
    write_text_file(index_path, json.dumps({"id": session_id, "thread_name": "gc source"}) + "\n")
    _configure_chatlas(environment, codex_home)

    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    captured_json(capsys)

    assert main([
        "chatlas",
        "gc",
        "--provider",
        "codex",
        "--session-id",
        session_id,
        "--json",
        "--verbose-mode",
        "quiet",
    ]) == 0
    payload = captured_json(capsys)
    assert payload["older_than"] == "30d"
    assert payload["counts"]["candidate_count"] == 0
    assert any(row["reason"] == "recent" for row in payload["skipped"])
    assert rollout_path.exists()


def test_chatlas_gc_promotes_session_directory_read_target_when_file_is_archived(
    tmp_path: Path,
) -> None:
    provider_home = tmp_path / "provider-home"
    session_root = provider_home / "sessions" / "session-1"
    events_path = session_root / "events.jsonl"
    raw_root = tmp_path / "chatlas" / "raw"
    gc_root = tmp_path / "chatlas" / "gc"
    write_text_file(events_path, '{"type":"session.start"}\n')
    archived_path = raw_root / "copilot-cli" / "fingerprint" / "home" / "sessions" / "session-1" / "events.jsonl"
    write_text_file(archived_path, events_path.read_text(encoding="utf-8"))
    _make_old(events_path)
    _make_old(session_root)

    agent = agent_from_config(
        AgentConfig(
            provider="copilot-cli",
            profile_id="copilot-main",
            label=None,
            home=provider_home,
            direct_targets=(),
            sqlite_db_paths=(),
            is_default=False,
            fingerprint_override="fingerprint",
        )
    )
    instance = ChatlasProviderInstance(agent=agent, fingerprint="fingerprint")

    candidates, skipped = _candidates_for_session(
        instance=instance,
        session_id="session-1",
        sources=(
            SessionSource(role="transcript", path=events_path),
            SessionSource(role="session_root", path=session_root, storage_kind="directory"),
        ),
        raw_root=raw_root,
        gc_root=gc_root,
        cutoff_timestamp=time.time() - (30 * 24 * 60 * 60),
    )

    assert skipped == []
    assert len(candidates) == 1
    assert candidates[0].role == "session_root"
    assert candidates[0].storage_kind == "directory"
    assert candidates[0].source_path == session_root
