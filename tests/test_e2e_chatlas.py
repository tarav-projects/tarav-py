from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli import main
from _helpers import captured_json, write_text_file


def _isolate_chatlas(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    codex_home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    return home, agentos_home, codex_home


def _write_global_config(agentos_home: Path, codex_home: Path) -> None:
    write_text_file(
        agentos_home / "config.json",
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "agent": {"instances": [{"provider": "codex", "id": "codex-work", "home": str(codex_home)}]},
                "chatlas": {"instance_ids": ["codex-work"]},
            }
        )
        + "\n",
    )


def _write_codex_rollout(path: Path, *, session_id: str, title: str = "Codex fixture", cwd: str = "/tmp") -> None:
    events = [
        {"timestamp": "2026-03-08T01:08:59.089Z", "type": "session_meta", "payload": {"id": session_id, "originator": "codex_cli_rs", "cwd": cwd}},
        {"timestamp": "2026-03-08T01:09:01.000Z", "type": "turn_context", "payload": {"cwd": cwd, "title": title}},
        {
            "timestamp": "2026-03-08T01:09:02.000Z",
            "type": "response_item",
            "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hello"}]},
        },
        {
            "timestamp": "2026-03-08T01:09:03.000Z",
            "type": "response_item",
            "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "hi"}]},
        },
    ]
    write_text_file(path, "\n".join(json.dumps(event) for event in events) + "\n")


def _index_rows(chatlas_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted((chatlas_root / "index" / "sessions").rglob("*.jsonl")):
        rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    return rows


def _doctor_row(chatlas_root: Path) -> dict[str, object]:
    artifact_path = chatlas_root / "raw" / "codex" / "fingerprint" / "home" / "session-1.jsonl"
    return {
        "uri": "agentos://chat-session/codex/fingerprint/session-1",
        "provider": "codex",
        "session_id": "session-1",
        "updated_at": "2026-03-08T01:09:01.000Z",
        "home": "/tmp/codex-home",
        "instance": "codex-work",
        "provider_instance_fingerprint": "fingerprint",
        "primary_backing_artifact": {"path": str(artifact_path)},
        "backing_artifacts": [{"path": str(artifact_path)}],
        "extractable": True,
    }


def test_chatlas_index_update_query_export_and_raw_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home, agentos_home, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    index_path = codex_home / "session_index.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id, title="chatlas source", cwd=str(tmp_path / "workspace"))
    write_text_file(index_path, json.dumps({"id": session_id, "thread_name": "chatlas source"}) + "\n")
    _write_global_config(agentos_home, codex_home)

    assert main(["chatlas", "index", "update", "--provider", "codex", "--output-mode", "json"]) == 0
    update_payload = captured_json(capsys)
    assert update_payload["status"] == "ok"
    assert update_payload["session_index"]["upserted_row_count"] == 1
    chatlas_root = home / "Documents" / "chatlas"
    row = _index_rows(chatlas_root)[0]
    assert row["session_id"] == session_id
    assert row["display_name"] == "chatlas source"
    assert row["summary"]["visible_user_turn_count"] == 1
    assert str(chatlas_root / "raw") in row["primary_backing_artifact"]["path"]

    rollout_path.unlink()
    index_path.unlink()

    assert main(["chatlas", "query", "--session-id", session_id]) == 0
    query_payload = captured_json(capsys)
    assert query_payload["returned_row_count"] == 1
    assert query_payload["rows"][0]["summary"]["last_assistant_text_excerpt"] == "hi"

    assert main(["chatlas", "export", "--session-id", session_id, "--view", "zip-transcript", "--format", "json"]) == 0
    export_payload = captured_json(capsys)
    assert export_payload["class"] == "agentos.chatlas.zip_transcript"
    assert [turn["role"] for turn in export_payload["turns"]] == ["user", "assistant"]

    assert main(["chatlas", "raw", "path", "--session-id", session_id, "--format", "json"]) == 0
    raw_payload = captured_json(capsys)
    assert raw_payload["session"]["session_id"] == session_id
    assert all(str(chatlas_root / "raw") in path for path in raw_payload["paths"])
    assert all(str(codex_home) not in path for path in raw_payload["paths"])


def test_chatlas_stats_and_doctor_cover_index_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home, _, _ = _isolate_chatlas(monkeypatch, tmp_path)
    chatlas_root = home / "Documents" / "chatlas"
    row = _doctor_row(chatlas_root)
    artifact_path = Path(row["primary_backing_artifact"]["path"])
    write_text_file(artifact_path, "{}\n")
    write_text_file(
        chatlas_root / "index" / "sessions" / "codex" / "fingerprint" / "sessions.index.jsonl",
        json.dumps(row) + "\n",
    )
    write_text_file(
        chatlas_root / "raw" / "codex" / "fingerprint" / "manifest.json",
        json.dumps({"class": "agentos.chatlas.raw_partition_manifest", "schema_version": 1, "provider": "codex", "provider_instance_fingerprint": "fingerprint"}) + "\n",
    )

    assert main(["chatlas", "stats", "--format", "json"]) == 0
    stats_payload = captured_json(capsys)
    assert stats_payload["stats"]["session_count"] == 1
    assert stats_payload["stats"]["provider_count"] == 1
    assert stats_payload["by_provider"]["codex"]["session_count"] == 1

    assert main(["chatlas", "index", "doctor", "--format", "json"]) == 0
    doctor_payload = captured_json(capsys)
    assert doctor_payload["summary"]["row_count"] == 1
    assert doctor_payload["summary"]["error_count"] == 0
    assert {check["status"] for check in doctor_payload["checks"]} == {"ok"}


def test_chatlas_query_uses_indexed_summary_without_raw_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home, _, _ = _isolate_chatlas(monkeypatch, tmp_path)
    partition = home / "Documents" / "chatlas" / "index" / "sessions" / "codex" / "fingerprint" / "sessions.index.jsonl"
    rows = [
        {"provider": "codex", "uri": "agentos://chat-session/codex/fingerprint/high", "session_id": "high", "updated_at": "2026-03-09T01:09:01.000Z", "summary": {"visible_user_turn_count": 6}},
        {"provider": "codex", "uri": "agentos://chat-session/codex/fingerprint/low", "session_id": "low", "updated_at": "2026-03-08T01:09:01.000Z", "summary": {"visible_user_turn_count": 5}},
        {"provider": "codex", "uri": "agentos://chat-session/codex/fingerprint/missing", "session_id": "missing", "updated_at": "2026-03-10T01:09:01.000Z"},
    ]
    write_text_file(partition, "\n".join(json.dumps(row) for row in rows) + "\n")

    assert main(["chatlas", "query", "--min-user-turns", "6", "--sort", "newest"]) == 0
    payload = captured_json(capsys)
    assert payload["index_matched_row_count"] == 3
    assert payload["query_matched_row_count"] == 1
    assert [row["session_id"] for row in payload["rows"]] == ["high"]
    assert not (home / "Documents" / "chatlas" / "raw").exists()


def test_chatlas_views_materialize_and_reuse_index_selectors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home, agentos_home, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-{session_id}.jsonl", session_id=session_id)
    _write_global_config(agentos_home, codex_home)
    assert main(["chatlas", "index", "update", "--provider", "codex", "--output-mode", "json"]) == 0
    capsys.readouterr()

    assert main(["chatlas", "views", "list"]) == 0
    assert {"zip-transcript", "zip-transcript-agent-summary"} <= {view["name"] for view in captured_json(capsys)["views"]}

    assert main(["chatlas", "views", "get", "--view", "zip-transcript", "--session-id", session_id]) == 0
    payload = captured_json(capsys)
    artifact_path = Path(payload["view"]["artifact"]["primary_path"])
    assert payload["view"]["state"] == "produced"
    assert artifact_path.is_file()
    assert str(home / "Documents" / "chatlas" / "views") in str(artifact_path)

    assert main(["chatlas", "views", "status", "--view", "zip-transcript", "--session-id", session_id]) == 0
    assert captured_json(capsys)["view"]["state"] == "fresh"


def test_chatlas_selector_errors_are_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate_chatlas(monkeypatch, tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(["chatlas", "export", "session-1"])
    assert exc_info.value.code == 2
    assert "unrecognized arguments: session-1" in capsys.readouterr().err

    assert main(["chatlas", "export"]) == 1
    assert "chatlas export requires at least one index query selector option" in capsys.readouterr().err

    assert main(["chatlas", "views", "get", "--view", "zip-transcript"]) == 1
    assert "requires at least one index query selector option" in capsys.readouterr().err
