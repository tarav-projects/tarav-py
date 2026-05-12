from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli import main


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_codex_rollout(path: Path, *, session_id: str, title: str = "Codex fixture") -> None:
    _write(
        path,
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-03-08T01:08:59.089Z",
                        "type": "session_meta",
                        "payload": {"id": session_id, "originator": "codex_cli_rs"},
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-08T01:09:01.000Z",
                        "type": "turn_context",
                        "payload": {"cwd": "/tmp", "title": title},
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-08T01:09:02.000Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "hello"}],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-08T01:09:03.000Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "hi"}],
                        },
                    }
                ),
            ]
        )
        + "\n",
    )


def _write_global_config(agentos_home: Path, *, codex_home: Path) -> None:
    _write(
        agentos_home / "config.json",
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "agent": {
                    "instances": [
                        {
                            "provider": "codex",
                            "id": "codex-work",
                            "home": str(codex_home),
                        },
                    ],
                },
                "chatlas": {
                    "instance_ids": ["codex-work"],
                },
            }
        )
        + "\n",
    )


def _isolate_agentos(monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    codex_home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    return home, agentos_home, codex_home


def _chatlas_index_rows(chatlas_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted((chatlas_root / "index" / "sessions").rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            rows.append(json.loads(line))
    return rows


def test_chatlas_update_index_only_empty_selection_json_payload(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _isolate_agentos(monkeypatch, tmp_path)
    assert main(["chatlas", "update", "--output-mode", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "chatlas update"
    assert payload["phases"]["index"]["command"] == "chatlas index update"
    assert payload["phase"] == "index-only"
    assert payload["selection"]["providers"] is None
    assert payload["provider_count"] == 0
    assert payload["instance_count"] == 0
    assert payload["raw_copy"]["copied_file_count"] == 0
    assert payload["instances"] == []
    assert payload["timing"]["elapsed_seconds"] >= 0


def test_chatlas_update_index_only_preserves_provider_selection(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _isolate_agentos(monkeypatch, tmp_path)
    assert (
        main(
            [
                "chatlas",
                "update",
                "--provider",
                "codex",
                "--provider",
                "claude-code",
                "--output-mode",
                "json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["phase"] == "index-only"
    assert payload["selection"]["providers"] == ["codex", "claude-code"]


def test_chatlas_update_index_only_respects_quiet_default_output(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _isolate_agentos(monkeypatch, tmp_path)
    assert main(["chatlas", "update", "--verbose-mode", "quiet"]) == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_chatlas_update_delta_scan_copies_and_indexes_codex_raw(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, agentos_home, codex_home = _isolate_agentos(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    index_path = codex_home / "session_index.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id)
    _write(index_path, json.dumps({"id": session_id, "thread_name": "delta scan"}) + "\n")
    _write_global_config(agentos_home, codex_home=codex_home)

    assert main(["chatlas", "update", "--provider", "codex", "--output-mode", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    chatlas_root = home / "Documents" / "chatlas"
    rows = _chatlas_index_rows(chatlas_root)
    assert payload["status"] == "ok"
    assert payload["native_scan"]["session_count"] == 1
    assert payload["native_scan"]["source_artifact_count"] == 2
    assert payload["native_scan"]["changed_session_count"] == 1
    assert payload["native_scan"]["changed_source_artifact_count"] == 2
    assert payload["raw_copy"]["copied_file_count"] == 2
    assert payload["session_index"]["upserted_row_count"] == 1
    assert payload["timing"]["elapsed_seconds"] >= payload["timing"]["raw_copy_seconds"]
    assert len(payload["instances"]) == 1
    instance_payload = payload["instances"][0]
    assert instance_payload["provider"] == "codex"
    assert instance_payload["home"] == str(codex_home)
    assert instance_payload["stats"]["native_scan"]["source_artifact_count"] == 2
    assert instance_payload["stats"]["raw_copy"]["copied_file_count"] == 2
    assert instance_payload["stats"]["timing"]["elapsed_seconds"] >= 0
    assert len(rows) == 1
    assert rows[0]["provider"] == "codex"
    assert rows[0]["session_id"] == session_id
    assert rows[0]["display_name"] == "delta scan"
    assert str(codex_home) not in rows[0]["primary_backing_artifact"]["path"]
    assert str(chatlas_root / "raw") in rows[0]["primary_backing_artifact"]["path"]


def test_chatlas_update_default_progress_prints_final_stats(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _, agentos_home, codex_home = _isolate_agentos(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id)
    _write_global_config(agentos_home, codex_home=codex_home)

    assert main(["chatlas", "update", "--provider", "codex"]) == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[chatlas] update summary:" in captured.err
    assert "sessions=1 changed=1 cached=0 artifacts=1 cached_artifacts=0 copied=1 indexed=1" in captured.err
    assert "[chatlas] codex/codex-work home=" in captured.err


def test_chatlas_index_update_exposes_delta_scan_command(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _, agentos_home, codex_home = _isolate_agentos(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id)
    _write_global_config(agentos_home, codex_home=codex_home)

    assert main(["chatlas", "index", "update", "--provider", "codex", "--output-mode", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "chatlas index update"
    assert payload["phase"] == "index-only"
    assert payload["native_scan"]["session_count"] == 1
    assert payload["raw_copy"]["copied_file_count"] == 1
    assert payload["session_index"]["upserted_row_count"] == 1


def test_chatlas_index_reset_deletes_index_and_cache_only(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    chatlas_root = home / "Documents" / "chatlas"
    raw_artifact = chatlas_root / "raw" / "codex" / "fingerprint" / "home" / "sessions" / "rollout.jsonl"
    index_artifact = chatlas_root / "index" / "sessions" / "codex" / "fingerprint" / "sessions.index.jsonl"
    cache_artifact = chatlas_root / "cache" / "session-index-derivations-v1" / "codex" / "fingerprint" / "sessions.json"
    _write(raw_artifact, "{}\n")
    _write(index_artifact, "{}\n")
    _write(cache_artifact, "{}\n")

    assert main(["chatlas", "index", "reset", "--output-mode", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "chatlas index reset"
    assert raw_artifact.is_file()
    assert not (chatlas_root / "index" / "sessions").exists()
    assert not (chatlas_root / "cache" / "session-index-derivations-v1").exists()
    assert {Path(row["path"]).name for row in payload["deleted"]} == {"sessions", "session-index-derivations-v1"}


def test_chatlas_index_redo_rebuilds_index_from_copied_raw(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, agentos_home, codex_home = _isolate_agentos(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    index_path = codex_home / "session_index.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id, title="redo source")
    _write(index_path, json.dumps({"id": session_id, "thread_name": "redo source"}) + "\n")
    _write_global_config(agentos_home, codex_home=codex_home)

    assert main(["chatlas", "index", "update", "--provider", "codex", "--output-mode", "json"]) == 0
    capsys.readouterr()
    rollout_path.unlink()
    index_path.unlink()
    assert main(["chatlas", "index", "reset", "--verbose-mode", "quiet"]) == 0
    capsys.readouterr()
    stale_index = home / "Documents" / "chatlas" / "index" / "sessions" / "codex" / "stale" / "sessions.index.jsonl"
    _write(stale_index, json.dumps({"session_id": "stale"}) + "\n")
    assert main(["chatlas", "index", "redo", "--provider", "codex", "--output-mode", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    rows = _chatlas_index_rows(home / "Documents" / "chatlas")
    assert payload["status"] == "ok"
    assert payload["command"] == "chatlas index redo"
    assert payload["native_scan"]["session_count"] == 1
    assert payload["session_index"]["upserted_row_count"] == 1
    assert [row["session_id"] for row in rows] == [session_id]
    assert rows[0]["display_name"] == "redo source"
    assert not stale_index.exists()


def test_chatlas_index_query_missing_index_returns_zero_matches(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _isolate_agentos(monkeypatch, tmp_path)

    assert main(["chatlas", "index", "query", "--session-id", "missing", "--format", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "chatlas index query"
    assert payload["partition_count"] == 0
    assert payload["matched_row_count"] == 0
    assert payload["rows"] == []


def test_chatlas_stats_missing_index_returns_zero_counts(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _isolate_agentos(monkeypatch, tmp_path)

    assert main(["chatlas", "stats", "--format", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "chatlas stats"
    assert payload["stats"]["session_count"] == 0
    assert payload["stats"]["provider_count"] == 0
    assert payload["stats"]["instance_count"] == 0
    assert payload["stats"]["partition_count"] == 0
    assert payload["stats"]["scanned_row_count"] == 0
    assert payload["stats"]["skipped_row_count"] == 0
    assert payload["by_provider"] == {}
    assert payload["by_instance"] == {}


def test_chatlas_stats_summarizes_index_rows_without_raw_artifacts(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    chatlas_root = home / "Documents" / "chatlas"
    partition = chatlas_root / "index" / "sessions" / "codex" / "fingerprint" / "sessions.index.jsonl"
    _write(
        partition,
        "\n".join(
            [
                json.dumps(
                    {
                        "provider": "codex",
                        "instance": "codex-work",
                        "uri": "agentos://chat-session/codex/fingerprint/session-1",
                        "session_id": "session-1",
                        "updated_at": "2026-03-08T01:09:01.000Z",
                        "extractable": True,
                        "primary_backing_artifact": {
                            "path": str(chatlas_root / "raw" / "missing-session-1.jsonl"),
                        },
                    }
                ),
                json.dumps(
                    {
                        "provider": "codex",
                        "instance": "codex-work",
                        "uri": "agentos://chat-session/codex/fingerprint/session-2",
                        "session_id": "session-2",
                        "updated_at": "2026-03-09T01:09:01.000Z",
                        "extractable": False,
                        "primary_backing_artifact": {
                            "path": str(chatlas_root / "raw" / "missing-session-2.jsonl"),
                        },
                    }
                ),
            ]
        )
        + "\n",
    )

    assert main(["chatlas", "stats", "--format", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["stats"]["session_count"] == 2
    assert payload["stats"]["extractable_session_count"] == 1
    assert payload["stats"]["non_extractable_session_count"] == 1
    assert payload["stats"]["provider_count"] == 1
    assert payload["stats"]["instance_count"] == 1
    assert payload["stats"]["partition_count"] == 1
    assert payload["stats"]["oldest_updated_at"] == "2026-03-08T01:09:01Z"
    assert payload["stats"]["latest_updated_at"] == "2026-03-09T01:09:01Z"
    assert payload["by_provider"]["codex"]["session_count"] == 2
    assert payload["by_provider"]["codex"]["instance_count"] == 1
    assert payload["by_instance"]["codex/codex-work"]["session_count"] == 2


def test_chatlas_stats_filters_provider_and_keeps_explicit_zero_bucket(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    partition = home / "Documents" / "chatlas" / "index" / "sessions" / "claude-code" / "fp" / "sessions.index.jsonl"
    _write(
        partition,
        json.dumps(
            {
                "provider": "claude-code",
                "instance": "claude-work",
                "session_id": "session-1",
                "updated_at": "2026-03-08T01:09:01Z",
                "extractable": True,
            }
        )
        + "\n",
    )

    assert main(["chatlas", "stats", "--provider", "codex", "--full-output", "--format", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["filters"]["providers"] == ["codex"]
    assert payload["stats"]["session_count"] == 0
    assert payload["by_provider"]["codex"]["session_count"] == 0
    assert payload["by_provider"]["codex"]["instance_count"] == 0
    assert payload["by_instance"] == {}


def test_chatlas_stats_default_output_is_markdown_summary(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    partition = home / "Documents" / "chatlas" / "index" / "sessions" / "codex" / "fp" / "sessions.index.jsonl"
    _write(
        partition,
        json.dumps(
            {
                "provider": "codex",
                "instance": "codex-work",
                "session_id": "session-1",
                "updated_at": "2026-03-08T01:09:01Z",
                "extractable": True,
            }
        )
        + "\n",
    )

    assert main(["chatlas", "stats"]) == 0

    output = capsys.readouterr().out
    assert "Chatlas session index" in output
    assert "Sessions: 1" in output
    assert "Extractable: 1" in output
    assert "Index shards: 1" in output
    assert "- codex: 1 sessions, 1 instances" in output


def test_chatlas_stats_counts_malformed_index_rows(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    partition = home / "Documents" / "chatlas" / "index" / "sessions" / "codex" / "fp" / "sessions.index.jsonl"
    _write(
        partition,
        "\n".join(
            [
                json.dumps({"provider": "codex", "instance": "codex-work", "session_id": "session-1"}),
                "",
                "[1, 2, 3]",
                "{not-json}",
            ]
        )
        + "\n",
    )

    assert main(["chatlas", "stats", "--format", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["stats"]["session_count"] == 1
    assert payload["stats"]["scanned_row_count"] == 4
    assert payload["stats"]["skipped_row_count"] == 3


def test_chatlas_index_query_filters_index_rows_without_raw_artifacts(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    chatlas_root = home / "Documents" / "chatlas"
    partition = chatlas_root / "index" / "sessions" / "codex" / "fingerprint" / "sessions.index.jsonl"
    _write(
        partition,
        "\n".join(
            [
                json.dumps(
                    {
                        "provider": "codex",
                        "instance": "codex-work",
                        "provider_instance_fingerprint": "fingerprint",
                        "uri": "agentos://chat-session/codex/fingerprint/session-1",
                        "session_id": "session-1",
                        "display_name": "Delta Scan Notes",
                        "updated_at": "2026-03-08T01:09:01.000Z",
                        "extractable": True,
                        "identity_hash": "hash-1",
                    }
                ),
                json.dumps(
                    {
                        "provider": "codex",
                        "instance": "codex-other",
                        "provider_instance_fingerprint": "fingerprint",
                        "uri": "agentos://chat-session/codex/fingerprint/session-2",
                        "session_id": "session-2",
                        "display_name": "Other Work",
                        "updated_at": "2026-03-09T01:09:01.000Z",
                        "extractable": False,
                        "identity_hash": "hash-2",
                    }
                ),
            ]
        )
        + "\n",
    )

    assert (
        main(
            [
                "chatlas",
                "index",
                "query",
                "--provider",
                "codex",
                "--instance",
                "codex-work",
                "--display-name",
                "delta scan",
                "--extractable",
                "--format",
                "json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["matched_row_count"] == 1
    assert payload["returned_row_count"] == 1
    assert payload["rows"][0]["session_id"] == "session-1"
    assert not (chatlas_root / "raw").exists()


def test_chatlas_index_query_exact_filters_sort_limit_and_skips_bad_rows(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    partition = home / "Documents" / "chatlas" / "index" / "sessions" / "codex" / "fingerprint" / "sessions.index.jsonl"
    _write(
        partition,
        "\n".join(
            [
                "",
                "{bad json",
                json.dumps(
                    {
                        "provider": "codex",
                        "instance": "codex-work",
                        "provider_instance_fingerprint": "fingerprint",
                        "uri": "agentos://chat-session/codex/fingerprint/session-old",
                        "session_id": "session-old",
                        "display_name": "old",
                        "updated_at": "2026-03-07T01:09:01.000Z",
                        "extractable": True,
                        "identity_hash": "hash-old",
                    }
                ),
                json.dumps(
                    {
                        "provider": "codex",
                        "instance": "codex-work",
                        "provider_instance_fingerprint": "fingerprint",
                        "uri": "agentos://chat-session/codex/fingerprint/session-new",
                        "session_id": "session-new",
                        "display_name": "new",
                        "updated_at": "2026-03-09T01:09:01.000Z",
                        "extractable": True,
                        "identity_hash": "hash-new",
                    }
                ),
            ]
        )
        + "\n",
    )

    assert (
        main(
            [
                "chatlas",
                "index",
                "query",
                "--provider-instance-fingerprint",
                "fingerprint",
                "--updated-after",
                "2026-03-08T00:00:00.000Z",
                "--sort",
                "newest",
                "--limit",
                "1",
                "--format",
                "json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["scanned_row_count"] == 4
    assert payload["skipped_row_count"] == 2
    assert payload["matched_row_count"] == 1
    assert [row["session_id"] for row in payload["rows"]] == ["session-new"]


def test_chatlas_index_query_matches_identity_uri_and_session_id(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    uri = "agentos://chat-session/codex/fingerprint/session-1"
    partition = home / "Documents" / "chatlas" / "index" / "sessions" / "codex" / "fingerprint" / "sessions.index.jsonl"
    _write(
        partition,
        json.dumps(
            {
                "provider": "codex",
                "instance": "codex-work",
                "provider_instance_fingerprint": "fingerprint",
                "uri": uri,
                "session_id": "session-1",
                "display_name": "exact lookup",
                "updated_at": "2026-03-08T01:09:01.000Z",
                "extractable": True,
                "identity_hash": "hash-1",
            }
        )
        + "\n",
    )

    assert (
        main(
            [
                "chatlas",
                "index",
                "query",
                "--uri",
                uri,
                "--identity-hash",
                "hash-1",
                "--session-id",
                "session-1",
                "--format",
                "json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert [row["session_id"] for row in payload["rows"]] == ["session-1"]


def test_chatlas_export_uses_index_selection_and_copied_raw_artifact(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, agentos_home, codex_home = _isolate_agentos(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    index_path = codex_home / "session_index.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id, title="export source")
    _write(index_path, json.dumps({"id": session_id, "thread_name": "export source"}) + "\n")
    _write_global_config(agentos_home, codex_home=codex_home)

    assert main(["chatlas", "index", "update", "--provider", "codex", "--output-mode", "json"]) == 0
    capsys.readouterr()
    indexed_row = _chatlas_index_rows(home / "Documents" / "chatlas")[0]
    rollout_path.unlink()
    index_path.unlink()

    assert main(["chatlas", "export", "--session-id", session_id, "--view", "full", "--format", "json"]) == 0
    full_payload = json.loads(capsys.readouterr().out)
    chatlas_root = home / "Documents" / "chatlas"
    source_paths = [source["path"] for source in full_payload["sources"]]
    assert full_payload["class"] == "agentos.chatlas.session_model"
    assert full_payload["session"]["session_id"] == session_id
    assert full_payload["session"]["display_name"] == "export source"
    assert full_payload["normalization"]["provider"] == "codex"
    assert str(codex_home) not in json.dumps(full_payload)
    assert any(str(chatlas_root / "raw") in path for path in source_paths)

    assert (
        main(
            [
                "chatlas",
                "export",
                "--session-id",
                session_id,
                "--view",
                "zip-transcript",
                "--format",
                "json",
            ]
        )
        == 0
    )
    zip_payload = json.loads(capsys.readouterr().out)
    assert zip_payload["class"] == "agentos.chatlas.zip_transcript"
    assert zip_payload["session"]["session_id"] == session_id
    assert [turn["role"] for turn in zip_payload["turns"]] == ["user", "assistant"]

    assert main(["chatlas", "export", "--uri", indexed_row["uri"], "--format", "json"]) == 0
    uri_payload = json.loads(capsys.readouterr().out)
    assert uri_payload["session"]["session_id"] == session_id

    assert main(["chatlas", "export", "--identity-hash", indexed_row["identity_hash"], "--format", "json"]) == 0
    identity_payload = json.loads(capsys.readouterr().out)
    assert identity_payload["session"]["session_id"] == session_id


def test_chatlas_export_provider_restricts_index_selection(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, agentos_home, codex_home = _isolate_agentos(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id)
    _write_global_config(agentos_home, codex_home=codex_home)

    assert main(["chatlas", "index", "update", "--provider", "codex", "--output-mode", "json"]) == 0
    capsys.readouterr()
    assert main(["chatlas", "export", "--session-id", session_id, "--provider", "claude-code"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no indexed Chatlas session matched the chatlas export selector" in captured.err
    assert (home / "Documents" / "chatlas" / "raw").exists()


def test_chatlas_export_reports_zero_multiple_and_unsupported_matches(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    partition = home / "Documents" / "chatlas" / "index" / "sessions" / "mixed" / "fingerprint" / "sessions.index.jsonl"
    _write(
        partition,
        "\n".join(
            [
                json.dumps(
                    {
                        "provider": "codex",
                        "uri": "agentos://chat-session/codex/fingerprint/session-1",
                        "session_id": "session-1",
                        "display_name": "shared title",
                        "identity_hash": "hash-1",
                    }
                ),
                json.dumps(
                    {
                        "provider": "codex",
                        "uri": "agentos://chat-session/codex/fingerprint/session-2",
                        "session_id": "session-2",
                        "display_name": "shared title",
                        "identity_hash": "hash-2",
                    }
                ),
                json.dumps(
                    {
                        "provider": "gemini-cli",
                        "uri": "agentos://chat-session/gemini/fingerprint/session-3",
                        "session_id": "session-3",
                        "display_name": "gemini title",
                        "identity_hash": "hash-3",
                    }
                ),
            ]
        )
        + "\n",
    )

    assert main(["chatlas", "export", "--session-id", "missing"]) == 1
    assert "no indexed Chatlas session matched the chatlas export selector" in capsys.readouterr().err

    assert main(["chatlas", "export", "--display-name", "shared title"]) == 1
    multiple = capsys.readouterr()
    assert multiple.out == ""
    assert "multiple Chatlas sessions matched the chatlas export selector" in multiple.err
    assert "session-1" in multiple.err
    assert "session-2" in multiple.err

    assert main(["chatlas", "export", "--session-id", "session-3"]) == 1
    unsupported = capsys.readouterr()
    assert unsupported.out == ""
    assert "chatlas export has no provider-specific raw normalizer for provider 'gemini-cli'" in unsupported.err


def test_chatlas_export_rejects_positional_and_missing_selector(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _isolate_agentos(monkeypatch, tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(["chatlas", "export", "session-1"])
    assert exc_info.value.code == 2
    positional = capsys.readouterr()
    assert positional.out == ""
    assert "unrecognized arguments: session-1" in positional.err

    assert main(["chatlas", "export"]) == 1
    missing = capsys.readouterr()
    assert missing.out == ""
    assert "chatlas export requires at least one index query selector option" in missing.err


def test_chatlas_raw_path_and_export_use_index_selection_and_copied_raw(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, agentos_home, codex_home = _isolate_agentos(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    index_path = codex_home / "session_index.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id, title="raw source")
    _write(index_path, json.dumps({"id": session_id, "thread_name": "raw source"}) + "\n")
    _write_global_config(agentos_home, codex_home=codex_home)

    assert main(["chatlas", "index", "update", "--provider", "codex", "--output-mode", "json"]) == 0
    capsys.readouterr()
    rollout_path.unlink()
    index_path.unlink()

    assert main(["chatlas", "raw", "path", "--session-id", session_id]) == 0
    raw_path_output = capsys.readouterr().out
    chatlas_root = home / "Documents" / "chatlas"
    assert str(chatlas_root / "raw") in raw_path_output
    assert str(codex_home) not in raw_path_output

    assert main(["chatlas", "raw", "path", "--session-id", session_id, "--format", "json"]) == 0
    path_payload = json.loads(capsys.readouterr().out)
    assert path_payload["status"] == "ok"
    assert path_payload["command"] == "chatlas raw path"
    assert path_payload["session"]["session_id"] == session_id
    assert all(str(chatlas_root / "raw") in path for path in path_payload["paths"])

    assert main(["chatlas", "raw", "export", "--session-id", session_id, "--format", "json"]) == 0
    export_payload = json.loads(capsys.readouterr().out)
    assert export_payload["status"] == "ok"
    assert export_payload["class"] == "agentos.chatlas.raw_export"
    assert export_payload["session"]["session_id"] == session_id
    assert any("raw source" in source.get("content", "") for source in export_payload["sources"])
    assert all(str(codex_home) not in source.get("path", "") for source in export_payload["sources"])


def test_chatlas_raw_rejects_positional_and_missing_selector(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _isolate_agentos(monkeypatch, tmp_path)

    with pytest.raises(SystemExit) as path_exc_info:
        main(["chatlas", "raw", "path", "session-1"])
    assert path_exc_info.value.code == 2
    positional_path = capsys.readouterr()
    assert positional_path.out == ""
    assert "unrecognized arguments: session-1" in positional_path.err

    with pytest.raises(SystemExit) as export_exc_info:
        main(["chatlas", "raw", "export", "session-1"])
    assert export_exc_info.value.code == 2
    positional_export = capsys.readouterr()
    assert positional_export.out == ""
    assert "unrecognized arguments: session-1" in positional_export.err

    assert main(["chatlas", "raw", "path"]) == 1
    missing_path = capsys.readouterr()
    assert missing_path.out == ""
    assert "chatlas raw path requires at least one index query selector option" in missing_path.err

    assert main(["chatlas", "raw", "export"]) == 1
    missing_export = capsys.readouterr()
    assert missing_export.out == ""
    assert "chatlas raw export requires at least one index query selector option" in missing_export.err


def test_chatlas_update_delta_scan_unchanged_run_uses_derivation_cache(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _, agentos_home, codex_home = _isolate_agentos(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id)
    _write_global_config(agentos_home, codex_home=codex_home)

    assert main(["chatlas", "update", "--provider", "codex", "--output-mode", "json"]) == 0
    capsys.readouterr()
    assert main(["chatlas", "update", "--provider", "codex", "--output-mode", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["native_scan"]["session_count"] == 1
    assert payload["native_scan"]["changed_session_count"] == 0
    assert payload["native_scan"]["unchanged_session_count"] == 1
    assert payload["native_scan"]["cached_source_artifact_count"] == 1
    assert payload["cache"]["hit_count"] == 1
    assert payload["raw_copy"]["copied_file_count"] == 0
    assert payload["session_index"]["upserted_row_count"] == 0
    assert payload["instances"][0]["stats"]["cache"]["hit_count"] == 1


def test_chatlas_update_delta_scan_mutated_artifact_updates_delta_session(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _, agentos_home, codex_home = _isolate_agentos(monkeypatch, tmp_path)
    first_session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    second_session_id = "119ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    first_rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{first_session_id}.jsonl"
    second_rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{second_session_id}.jsonl"
    _write_codex_rollout(first_rollout_path, session_id=first_session_id)
    _write_codex_rollout(second_rollout_path, session_id=second_session_id)
    _write_global_config(agentos_home, codex_home=codex_home)

    assert main(["chatlas", "update", "--provider", "codex", "--output-mode", "json"]) == 0
    capsys.readouterr()
    with first_rollout_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": "2026-03-08T01:09:02.000Z", "type": "noop"}) + "\n")
    assert main(["chatlas", "update", "--provider", "codex", "--output-mode", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["native_scan"]["session_count"] == 2
    assert payload["native_scan"]["source_artifact_count"] == 2
    assert payload["native_scan"]["changed_session_count"] == 1
    assert payload["native_scan"]["changed_source_artifact_count"] == 1
    assert payload["native_scan"]["unchanged_session_count"] == 1
    assert payload["native_scan"]["cached_source_artifact_count"] == 1
    assert payload["raw_copy"]["copied_session_count"] == 1
    assert payload["raw_copy"]["copied_file_count"] == 1
    assert payload["session_index"]["upserted_row_count"] == 1


def test_chatlas_update_delta_scan_native_disappearance_drops_cache_not_index(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, agentos_home, codex_home = _isolate_agentos(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id)
    _write_global_config(agentos_home, codex_home=codex_home)

    assert main(["chatlas", "update", "--provider", "codex", "--output-mode", "json"]) == 0
    capsys.readouterr()
    rollout_path.unlink()
    assert main(["chatlas", "update", "--provider", "codex", "--output-mode", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    rows = _chatlas_index_rows(home / "Documents" / "chatlas")
    assert payload["native_scan"]["session_count"] == 0
    assert payload["cache"]["removed_entry_count"] == 1
    assert [row["session_id"] for row in rows] == [session_id]


def test_chatlas_query_fails_as_explicit_stub(capsys) -> None:
    assert main(["chatlas", "query", "session-1"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "chatlas query is under reimplementation" in captured.err


def test_chatlas_runtime_does_not_import_deprecated_code() -> None:
    src_root = Path(__file__).resolve().parents[1] / "src" / "agentos"
    matches = [
        path
        for path in src_root.rglob("*.py")
        if "_DEPRECATED" in path.read_text(encoding="utf-8")
    ]

    assert matches == []
