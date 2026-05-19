from __future__ import annotations

import json
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from agentos.chatlas.core import chatlas_query
from agentos.chatlas.views.core import chatlas_run_produce
from agentos.cli import main


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_codex_rollout(
    path: Path,
    *,
    session_id: str,
    title: str = "Codex fixture",
    cwd: str = "/tmp",
    user_text: str = "hello",
    assistant_text: str = "hi",
) -> None:
    _write(
        path,
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-03-08T01:08:59.089Z",
                        "type": "session_meta",
                        "payload": {"id": session_id, "originator": "codex_cli_rs", "cwd": cwd},
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-08T01:09:01.000Z",
                        "type": "turn_context",
                        "payload": {"cwd": cwd, "title": title},
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-08T01:09:02.000Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": user_text}],
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
                            "content": [{"type": "output_text", "text": assistant_text}],
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


def _codex_raw_home(chatlas_root: Path, fingerprint: str) -> Path:
    return chatlas_root / "raw" / "codex" / fingerprint / "home"


def _codex_manifest_path(chatlas_root: Path, fingerprint: str) -> Path:
    return _codex_raw_home(chatlas_root, fingerprint).parent / "manifest.json"


def _doctor_row(
    chatlas_root: Path,
    *,
    uri: str = "agentos://chat-session/codex/fingerprint/session-1",
    provider: str = "codex",
    fingerprint: str = "fingerprint",
    session_id: str = "session-1",
    home: str = "/tmp/codex-home",
    artifact_name: str = "session-1.jsonl",
) -> dict[str, object]:
    artifact_path = chatlas_root / "raw" / provider / fingerprint / "home" / artifact_name
    return {
        "uri": uri,
        "provider": provider,
        "session_id": session_id,
        "updated_at": "2026-03-08T01:09:01.000Z",
        "home": home,
        "instance": "codex-work",
        "provider_instance_fingerprint": fingerprint,
        "primary_backing_artifact": {
            "path": str(artifact_path),
        },
        "backing_artifacts": [
            {
                "path": str(artifact_path),
            }
        ],
        "extractable": True,
    }


def _write_doctor_index(chatlas_root: Path, rows: list[dict[str, object]]) -> None:
    partition = chatlas_root / "index" / "sessions" / "codex" / "fingerprint" / "sessions.index.jsonl"
    _write(partition, "\n".join(json.dumps(row) for row in rows) + "\n")


def _write_doctor_manifest(chatlas_root: Path, *, provider: str = "codex", fingerprint: str = "fingerprint") -> None:
    _write(
        chatlas_root / "raw" / provider / fingerprint / "manifest.json",
        json.dumps(
            {
                "class": "agentos.chatlas.raw_partition_manifest",
                "schema_version": 1,
                "provider": provider,
                "provider_instance_fingerprint": fingerprint,
            }
        )
        + "\n",
    )


def _assert_chatlas_query_counts(
    payload: dict[str, object],
    *,
    index_matched: int,
    candidate: int,
    query_matched: int,
    returned: int,
) -> None:
    assert payload["index_matched_row_count"] == index_matched
    assert payload["candidate_row_count"] == candidate
    assert payload["query_matched_row_count"] == query_matched
    assert payload["returned_row_count"] == returned
    assert "matched_row_count" not in payload


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
    project_path = tmp_path / "workspace"
    _write_codex_rollout(rollout_path, session_id=session_id, cwd=str(project_path))
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
    fingerprint = instance_payload["provider_instance_fingerprint"]
    raw_home = _codex_raw_home(chatlas_root, fingerprint)
    manifest_path = _codex_manifest_path(chatlas_root, fingerprint)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest == {
        "class": "agentos.chatlas.raw_partition_manifest",
        "schema_version": 1,
        "provider": "codex",
        "provider_instance_fingerprint": fingerprint,
        "instance": "codex-work",
        "home": str(codex_home),
        "raw_home": str(raw_home),
        "home_source": "configured_agent_home",
        "source_roots": [
            {
                "role": "home",
                "source_root": str(codex_home),
                "raw_root": str(raw_home),
            }
        ],
    }
    assert "session_count" not in manifest
    assert "session_updated_at_range" not in manifest
    assert len(rows) == 1
    assert rows[0]["provider"] == "codex"
    assert rows[0]["session_id"] == session_id
    assert rows[0]["display_name"] == "delta scan"
    assert rows[0]["home"] == str(codex_home)
    assert rows[0]["project_path"] == str(project_path)
    assert rows[0]["native"]["cwd"] == str(project_path)
    assert str(codex_home) not in rows[0]["primary_backing_artifact"]["path"]
    assert str(chatlas_root / "raw") in rows[0]["primary_backing_artifact"]["path"]
    assert rows[0]["summary"] == {
        "visible_user_turn_count": 1,
        "visible_assistant_turn_count": 1,
        "visible_message_count": 2,
        "visible_user_text_char_count": 5,
        "visible_assistant_text_char_count": 2,
        "visible_text_char_count": 7,
        "first_user_text_excerpt": "hello",
        "last_user_text_excerpt": "hello",
        "last_assistant_text_excerpt": "hi",
    }

    assert main(["chatlas", "query", "--session-id", session_id]) == 0
    query_payload = json.loads(capsys.readouterr().out)
    assert query_payload["rows"] == [
        {
            "uri": rows[0]["uri"],
            "provider": "codex",
            "instance": "codex-work",
            "identity_hash": rows[0]["identity_hash"],
            "session_id": session_id,
            "updated_at": rows[0]["updated_at"],
            "home": str(codex_home),
            "project_path": str(project_path),
            "summary": rows[0]["summary"],
        }
    ]


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


def test_chatlas_index_update_summary_tracks_visible_turns_and_excerpts(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, agentos_home, codex_home = _isolate_agentos(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    _write_codex_rollout(
        rollout_path,
        session_id=session_id,
        user_text="first   user\nmessage",
        assistant_text="first assistant reply",
    )
    with rollout_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "timestamp": "2026-03-08T01:09:04.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "second user request"}],
                    },
                }
            )
            + "\n"
        )
        handle.write(
            json.dumps(
                {
                    "timestamp": "2026-03-08T01:09:05.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "second assistant reply"}],
                    },
                }
            )
            + "\n"
        )
    _write_global_config(agentos_home, codex_home=codex_home)

    assert main(["chatlas", "index", "update", "--provider", "codex", "--output-mode", "json"]) == 0
    capsys.readouterr()

    summary = _chatlas_index_rows(home / "Documents" / "chatlas")[0]["summary"]
    assert summary["visible_user_turn_count"] == 2
    assert summary["visible_assistant_turn_count"] == 2
    assert summary["visible_message_count"] == 4
    assert summary["first_user_text_excerpt"] == "first user message"
    assert summary["last_user_text_excerpt"] == "second user request"
    assert summary["last_assistant_text_excerpt"] == "second assistant reply"


def test_chatlas_index_reset_deletes_index_and_cache_only(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    chatlas_root = home / "Documents" / "chatlas"
    raw_artifact = chatlas_root / "raw" / "codex" / "fingerprint" / "home" / "sessions" / "rollout.jsonl"
    index_artifact = chatlas_root / "index" / "sessions" / "codex" / "fingerprint" / "sessions.index.jsonl"
    cache_artifact = chatlas_root / "cache" / "session-index-derivations-v2" / "codex" / "fingerprint" / "sessions.json"
    _write(raw_artifact, "{}\n")
    _write(index_artifact, "{}\n")
    _write(cache_artifact, "{}\n")

    assert main(["chatlas", "index", "reset", "--output-mode", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "chatlas index reset"
    assert raw_artifact.is_file()
    assert not (chatlas_root / "index" / "sessions").exists()
    assert not (chatlas_root / "cache" / "session-index-derivations-v2").exists()
    assert {Path(row["path"]).name for row in payload["deleted"]} == {"sessions", "session-index-derivations-v2"}


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
    assert payload["instances"][0]["instance"] == "codex-work"
    assert payload["instances"][0]["home"] == str(codex_home)
    assert payload["native_scan"]["session_count"] == 1
    assert payload["session_index"]["upserted_row_count"] == 1
    assert [row["session_id"] for row in rows] == [session_id]
    assert rows[0]["display_name"] == "redo source"
    assert rows[0]["instance"] == "codex-work"
    assert rows[0]["home"] == str(codex_home)
    assert str(home / "Documents" / "chatlas" / "raw") not in rows[0]["home"]
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
    _assert_chatlas_query_counts(payload, index_matched=0, candidate=0, query_matched=0, returned=0)
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


def test_chatlas_index_doctor_clean_fixture_returns_ok(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    chatlas_root = home / "Documents" / "chatlas"
    row = _doctor_row(chatlas_root)
    artifact_path = Path(row["primary_backing_artifact"]["path"])
    _write(artifact_path, "{}\n")
    _write_doctor_index(chatlas_root, [row])
    _write_doctor_manifest(chatlas_root)

    assert main(["chatlas", "index", "doctor", "--format", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "chatlas index doctor"
    assert payload["summary"]["row_count"] == 1
    assert payload["summary"]["error_count"] == 0
    assert {check["name"]: check["status"] for check in payload["checks"]} == {
        "required_fields": "ok",
        "duplicate_uri": "ok",
        "duplicate_provider_fingerprint_session": "ok",
        "backing_artifacts_exist": "ok",
        "home_not_managed_storage": "ok",
        "raw_partition_manifests": "ok",
    }


def test_chatlas_index_doctor_default_output_is_markdown_summary(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _isolate_agentos(monkeypatch, tmp_path)

    assert main(["chatlas", "index", "doctor"]) == 0

    output = capsys.readouterr().out
    assert "Chatlas index doctor" in output
    assert "Status: ok" in output
    assert "Rows: 0" in output
    assert "Errors: 0" in output


def test_chatlas_index_doctor_reports_required_field_errors(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    chatlas_root = home / "Documents" / "chatlas"
    row = _doctor_row(chatlas_root)
    row.pop("updated_at")
    row["home"] = None
    _write_doctor_index(chatlas_root, [row])

    assert main(["chatlas", "index", "doctor", "--format", "json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    check = next(check for check in payload["checks"] if check["name"] == "required_fields")
    assert check["status"] == "error"
    assert check["error_count"] == 2
    assert {sample["field"] for sample in check["samples"]} == {"updated_at", "home"}


def test_chatlas_index_doctor_reports_duplicate_identity_errors(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    chatlas_root = home / "Documents" / "chatlas"
    row = _doctor_row(chatlas_root)
    duplicate = {**row}
    _write_doctor_index(chatlas_root, [row, duplicate])

    assert main(["chatlas", "index", "doctor", "--format", "json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["duplicate_uri"]["error_count"] == 1
    assert checks["duplicate_provider_fingerprint_session"]["error_count"] == 1


def test_chatlas_index_doctor_reports_missing_backing_artifact(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    chatlas_root = home / "Documents" / "chatlas"
    row = _doctor_row(chatlas_root)
    _write_doctor_index(chatlas_root, [row])
    _write_doctor_manifest(chatlas_root)

    assert main(["chatlas", "index", "doctor", "--format", "json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    check = next(check for check in payload["checks"] if check["name"] == "backing_artifacts_exist")
    assert check["status"] == "error"
    assert check["error_count"] == 2
    assert check["samples"][0]["artifact"] == "primary_backing_artifact"


def test_chatlas_index_doctor_reports_home_under_managed_storage(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    chatlas_root = home / "Documents" / "chatlas"
    row = _doctor_row(chatlas_root, home=str(chatlas_root / "raw" / "codex" / "fingerprint" / "home"))
    artifact_path = Path(row["primary_backing_artifact"]["path"])
    _write(artifact_path, "{}\n")
    _write_doctor_index(chatlas_root, [row])
    _write_doctor_manifest(chatlas_root)

    assert main(["chatlas", "index", "doctor", "--format", "json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    check = next(check for check in payload["checks"] if check["name"] == "home_not_managed_storage")
    assert check["status"] == "error"
    assert check["error_count"] == 1
    assert check["samples"][0]["managed_root"] == str(chatlas_root / "raw")


def test_chatlas_index_doctor_reports_missing_raw_partition_manifest(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    chatlas_root = home / "Documents" / "chatlas"
    row = _doctor_row(chatlas_root)
    artifact_path = Path(row["primary_backing_artifact"]["path"])
    _write(artifact_path, "{}\n")
    _write_doctor_index(chatlas_root, [row])

    assert main(["chatlas", "index", "doctor", "--format", "json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    check = next(check for check in payload["checks"] if check["name"] == "raw_partition_manifests")
    assert check["status"] == "error"
    assert check["error_count"] == 1
    assert check["samples"][0]["path"] == str(chatlas_root / "raw" / "codex" / "fingerprint" / "manifest.json")


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
    _assert_chatlas_query_counts(payload, index_matched=1, candidate=1, query_matched=1, returned=1)
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
    _assert_chatlas_query_counts(payload, index_matched=1, candidate=1, query_matched=1, returned=1)
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


def test_chatlas_export_reports_codex_normalization_blocker(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    missing_artifact = home / "Documents" / "chatlas" / "raw" / "codex" / "fingerprint" / "home" / "missing.jsonl"
    partition = home / "Documents" / "chatlas" / "index" / "sessions" / "codex" / "fingerprint" / "sessions.index.jsonl"
    _write(
        partition,
        json.dumps(
            {
                "provider": "codex",
                "uri": "agentos://chat-session/codex/fingerprint/session-missing",
                "session_id": "session-missing",
                "identity_hash": "hash-missing",
                "primary_backing_artifact": {
                    "role": "transcript",
                    "path": str(missing_artifact),
                },
                "backing_artifacts": [
                    {
                        "role": "transcript",
                        "path": str(missing_artifact),
                    }
                ],
            }
        )
        + "\n",
    )

    assert main(["chatlas", "export", "--session-id", "session-missing"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "chatlas export could not normalize codex raw artifacts for session 'session-missing'" in captured.err
    assert f"primary transcript artifact is missing: {missing_artifact}" in captured.err


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
    home, agentos_home, codex_home = _isolate_agentos(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id)
    _write_global_config(agentos_home, codex_home=codex_home)

    assert main(["chatlas", "update", "--provider", "codex", "--output-mode", "json"]) == 0
    first_payload = json.loads(capsys.readouterr().out)
    chatlas_root = home / "Documents" / "chatlas"
    fingerprint = first_payload["instances"][0]["provider_instance_fingerprint"]
    manifest_path = _codex_manifest_path(chatlas_root, fingerprint)
    replacement_manifest = {
        "class": "agentos.chatlas.raw_partition_manifest",
        "schema_version": 1,
        "provider": "codex",
        "provider_instance_fingerprint": fingerprint,
        "instance": "preexisting",
        "home": "/already/stamped",
        "raw_home": "/already/raw",
        "home_source": "manual",
        "source_roots": [],
    }
    _write(manifest_path, json.dumps(replacement_manifest, sort_keys=True, indent=2) + "\n")
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
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == replacement_manifest


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


def test_chatlas_query_missing_index_returns_empty_normalized_rows(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _isolate_agentos(monkeypatch, tmp_path)

    assert main(["chatlas", "query", "--session-id", "missing"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "chatlas query"
    assert payload["scan_limit"] == 5000
    assert payload["limit"] == 50
    _assert_chatlas_query_counts(payload, index_matched=0, candidate=0, query_matched=0, returned=0)
    assert payload["rows"] == []


def test_chatlas_query_filters_index_rows_and_returns_minimal_shape(
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
                json.dumps(
                    {
                        "provider": "codex",
                        "uri": "agentos://chat-session/codex/fingerprint/session-1",
                        "session_id": "session-1",
                        "display_name": "Chatlas design",
                        "updated_at": "2026-03-08T01:09:01.000Z",
                        "extractable": True,
                        "identity_hash": "hash-1",
                    }
                ),
                json.dumps(
                    {
                        "provider": "codex",
                        "uri": "agentos://chat-session/codex/fingerprint/session-2",
                        "session_id": "session-2",
                        "display_name": "Other work",
                        "updated_at": "2026-03-09T01:09:01.000Z",
                        "extractable": True,
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
                "query",
                "--provider",
                "codex",
                "--display-name",
                "chatlas",
                "--updated-after",
                "2026-03-08T00:00:00Z",
                "--sort",
                "newest",
                "--limit",
                "1",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    _assert_chatlas_query_counts(payload, index_matched=1, candidate=1, query_matched=1, returned=1)
    assert payload["rows"] == [
        {
            "uri": "agentos://chat-session/codex/fingerprint/session-1",
            "provider": "codex",
            "instance": None,
            "identity_hash": "hash-1",
            "session_id": "session-1",
            "updated_at": "2026-03-08T01:09:01.000Z",
            "home": None,
            "project_path": None,
            "summary": None,
        }
    ]


def test_chatlas_query_min_user_turns_uses_indexed_summary_without_raw_artifacts(
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
                json.dumps(
                    {
                        "provider": "codex",
                        "uri": "agentos://chat-session/codex/fingerprint/session-high",
                        "session_id": "session-high",
                        "updated_at": "2026-03-09T01:09:01.000Z",
                        "summary": {"visible_user_turn_count": 6},
                    }
                ),
                json.dumps(
                    {
                        "provider": "codex",
                        "uri": "agentos://chat-session/codex/fingerprint/session-low",
                        "session_id": "session-low",
                        "updated_at": "2026-03-08T01:09:01.000Z",
                        "summary": {"visible_user_turn_count": 5},
                    }
                ),
                json.dumps(
                    {
                        "provider": "codex",
                        "uri": "agentos://chat-session/codex/fingerprint/session-missing-summary",
                        "session_id": "session-missing-summary",
                        "updated_at": "2026-03-10T01:09:01.000Z",
                    }
                ),
            ]
        )
        + "\n",
    )

    assert main(["chatlas", "query", "--min-user-turns", "6", "--sort", "newest"]) == 0

    payload = json.loads(capsys.readouterr().out)
    _assert_chatlas_query_counts(payload, index_matched=3, candidate=3, query_matched=1, returned=1)
    assert [row["session_id"] for row in payload["rows"]] == ["session-high"]
    assert payload["rows"][0]["summary"] == {"visible_user_turn_count": 6}
    assert not (home / "Documents" / "chatlas" / "raw").exists()


def test_chatlas_query_field_session_id_prints_matching_ids(
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
                json.dumps(
                    {
                        "provider": "codex",
                        "uri": "agentos://chat-session/codex/fingerprint/session-new",
                        "session_id": "session-new",
                        "updated_at": "2026-03-09T01:09:01.000Z",
                        "summary": {"visible_user_turn_count": 4},
                    }
                ),
                json.dumps(
                    {
                        "provider": "codex",
                        "uri": "agentos://chat-session/codex/fingerprint/session-old",
                        "session_id": "session-old",
                        "updated_at": "2026-03-08T01:09:01.000Z",
                        "summary": {"visible_user_turn_count": 4},
                    }
                ),
                json.dumps(
                    {
                        "provider": "codex",
                        "uri": "agentos://chat-session/codex/fingerprint/session-low",
                        "session_id": "session-low",
                        "updated_at": "2026-03-10T01:09:01.000Z",
                        "summary": {"visible_user_turn_count": 3},
                    }
                ),
                json.dumps(
                    {
                        "provider": "codex",
                        "uri": "agentos://chat-session/codex/fingerprint/missing-session-id",
                        "updated_at": "2026-03-11T01:09:01.000Z",
                        "summary": {"visible_user_turn_count": 4},
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
                "query",
                "--min-user-turns",
                "4",
                "--sort",
                "newest",
                "--limit",
                "2",
                "--field",
                "session_id",
            ]
        )
        == 0
    )

    assert capsys.readouterr().out.splitlines() == ["session-new"]


def test_chatlas_query_help_describes_field_and_jq_examples(
    capsys,
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["chatlas", "query", "--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "agentos chatlas query --min-user-turns 4 --field session_id" in output
    assert "agentos chatlas query --min-user-turns 4 | jq -r '.rows[].session_id'" in output


def test_chatlas_query_can_return_full_rows_for_internal_consumers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    artifact_path = home / "Documents" / "chatlas" / "raw" / "codex" / "fingerprint" / "home" / "session-1.jsonl"
    partition = home / "Documents" / "chatlas" / "index" / "sessions" / "codex" / "fingerprint" / "sessions.index.jsonl"
    _write(
        partition,
        json.dumps(
            {
                "provider": "codex",
                "uri": "agentos://chat-session/codex/fingerprint/session-1",
                "session_id": "session-1",
                "identity_hash": "hash-1",
                "primary_backing_artifact": {
                    "role": "transcript",
                    "path": str(artifact_path),
                },
                "backing_artifacts": [
                    {
                        "role": "transcript",
                        "path": str(artifact_path),
                    }
                ],
            }
        )
        + "\n",
    )

    compact_payload = chatlas_query(session_id="session-1")
    full_payload = chatlas_query(session_id="session-1", row_shape="full")

    assert "primary_backing_artifact" not in compact_payload["rows"][0]
    assert full_payload["rows"][0]["primary_backing_artifact"]["path"] == str(artifact_path)
    assert full_payload["rows"][0]["backing_artifacts"][0]["role"] == "transcript"


def test_chatlas_run_produce_uses_full_query_rows(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    artifact_path = home / "Documents" / "chatlas" / "raw" / "codex" / "fingerprint" / "home" / "session-1.jsonl"
    partition = home / "Documents" / "chatlas" / "index" / "sessions" / "codex" / "fingerprint" / "sessions.index.jsonl"
    _write(
        partition,
        json.dumps(
            {
                "provider": "codex",
                "uri": "agentos://chat-session/codex/fingerprint/session-1",
                "session_id": "session-1",
                "identity_hash": "hash-1",
                "primary_backing_artifact": {
                    "role": "transcript",
                    "path": str(artifact_path),
                },
                "backing_artifacts": [
                    {
                        "role": "transcript",
                        "path": str(artifact_path),
                    }
                ],
            }
        )
        + "\n",
    )
    captured_rows: list[dict[str, object]] = []

    def fake_run_produce(**kwargs):
        captured_rows.extend(kwargs["rows"])
        return {
            "status": "ok",
            "command": "chatlas run-produce",
            "failed_count": 0,
        }

    monkeypatch.setattr("agentos.chatlas.commands.chatlas_run_produce", fake_run_produce)

    assert (
        main(
            [
                "chatlas",
                "run-produce",
                "--agent-provider",
                "codex",
                "--session-id",
                "session-1",
                "--view",
                "zip-transcript-agent-summary",
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    assert captured_rows[0]["primary_backing_artifact"]["path"] == str(artifact_path)
    assert captured_rows[0]["backing_artifacts"][0]["role"] == "transcript"


def test_chatlas_run_produce_prepares_stage_and_commits_after_agent_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    chatlas_root = home / "Documents" / "chatlas"
    artifact_path = chatlas_root / "raw" / "codex" / "fingerprint" / "home" / "session-1.jsonl"
    _write_codex_rollout(
        artifact_path,
        session_id="session-1",
        user_text="full user text",
        assistant_text="long assistant text",
    )
    row = {
        "provider": "codex",
        "uri": "agentos://chat-session/codex/fingerprint/session-1",
        "session_id": "session-1",
        "identity_hash": "hash-1",
        "primary_backing_artifact": {
            "role": "transcript",
            "path": str(artifact_path),
        },
        "backing_artifacts": [
            {
                "role": "transcript",
                "path": str(artifact_path),
            }
        ],
    }
    prompts: list[str] = []

    class FakeAgent:
        def run(self, command_config, run_config):
            _ = run_config
            prompt = command_config.prompt
            prompts.append(prompt)
            source_path = Path(re.search(r"Read source transcript JSON from: (.+)", prompt).group(1))
            output_path = Path(re.search(r"Write exactly one artifact file to: (.+)", prompt).group(1))
            source_payload = json.loads(source_path.read_text(encoding="utf-8"))
            summary_payload = {
                "class": "agentos.chatlas.zip_transcript_agent_summary",
                "schema_version": 1,
                "view": "zip-transcript-agent-summary",
                "source_view": "zip-transcript",
                "session": source_payload["session"],
                "turns": [
                    {
                        "role": turn["role"],
                        "text": turn["text"] if turn["role"] == "user" else "compressed assistant turn",
                    }
                    for turn in source_payload["turns"]
                ],
            }
            output_path.write_text(json.dumps(summary_payload, separators=(",", ":")) + "\n", encoding="utf-8")
            return SimpleNamespace(exit_code=0)

        def run_dry(self, command_config):
            return SimpleNamespace(lines=[command_config.prompt])

    monkeypatch.setattr("agentos.agent.providers.resolve_agent", lambda **kwargs: FakeAgent())

    payload = chatlas_run_produce(
        view="zip-transcript-agent-summary",
        provider="codex",
        rows=[row],
        chatlas_root=chatlas_root,
    )

    assert payload["status"] == "ok"
    assert payload["failed_count"] == 0
    run = payload["runs"][0]
    assert run["exit_code"] == 0
    assert "commit" in run
    final_path = Path(run["artifact_path"])
    assert final_path.is_file()
    assert "agentos chatlas views stage" not in prompts[0]
    assert "agentos chatlas views commit" not in prompts[0]
    assert "/Users/pereiro/projects/agentos-project/agentos-md/skills/chatlas-usage/references" in prompts[0]
    assert str(final_path) in prompts[0]
    assert Path(run["prepared"]["output_artifact_path"]).name == "summary.json"
    final_payload = json.loads(final_path.read_text(encoding="utf-8"))
    assert [turn["role"] for turn in final_payload["turns"]] == ["user", "assistant"]
    assert final_payload["turns"][0]["text"] == "full user text"
    assert final_payload["turns"][1]["text"] == "compressed assistant turn"


def test_chatlas_run_produce_reports_commit_linter_failure_after_agent_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    chatlas_root = home / "Documents" / "chatlas"
    artifact_path = chatlas_root / "raw" / "codex" / "fingerprint" / "home" / "session-1.jsonl"
    _write_codex_rollout(artifact_path, session_id="session-1")
    row = {
        "provider": "codex",
        "uri": "agentos://chat-session/codex/fingerprint/session-1",
        "session_id": "session-1",
        "identity_hash": "hash-1",
        "primary_backing_artifact": {
            "role": "transcript",
            "path": str(artifact_path),
        },
        "backing_artifacts": [
            {
                "role": "transcript",
                "path": str(artifact_path),
            }
        ],
    }

    class FakeAgent:
        def run(self, command_config, run_config):
            _ = run_config
            output_path = Path(
                re.search(r"Write exactly one artifact file to: (.+)", command_config.prompt).group(1)
            )
            output_path.write_text(
                json.dumps(
                    {
                        "class": "agentos.chatlas.zip_transcript_agent_summary",
                        "schema_version": 1,
                        "view": "zip-transcript-agent-summary",
                        "source_view": "zip-transcript",
                        "session": {},
                        "turns": [],
                    },
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            return SimpleNamespace(exit_code=0)

        def run_dry(self, command_config):
            return SimpleNamespace(lines=[command_config.prompt])

    monkeypatch.setattr("agentos.agent.providers.resolve_agent", lambda **kwargs: FakeAgent())

    payload = chatlas_run_produce(
        view="zip-transcript-agent-summary",
        provider="codex",
        rows=[row],
        chatlas_root=chatlas_root,
    )

    assert payload["status"] == "error"
    assert payload["failed_count"] == 1
    assert payload["runs"][0]["exit_code"] == 0
    assert "commit_error" in payload["runs"][0]
    assert "Commit.Linter failed" in payload["runs"][0]["commit_error"]


def test_chatlas_run_produce_dry_run_does_not_create_stage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    chatlas_root = home / "Documents" / "chatlas"
    artifact_path = chatlas_root / "raw" / "codex" / "fingerprint" / "home" / "session-1.jsonl"
    _write_codex_rollout(artifact_path, session_id="session-1")
    row = {
        "provider": "codex",
        "uri": "agentos://chat-session/codex/fingerprint/session-1",
        "session_id": "session-1",
        "identity_hash": "hash-1",
        "primary_backing_artifact": {
            "role": "transcript",
            "path": str(artifact_path),
        },
        "backing_artifacts": [
            {
                "role": "transcript",
                "path": str(artifact_path),
            }
        ],
    }

    class FakeAgent:
        def run_dry(self, command_config):
            return SimpleNamespace(lines=[command_config.prompt])

    monkeypatch.setattr("agentos.agent.providers.resolve_agent", lambda **kwargs: FakeAgent())

    payload = chatlas_run_produce(
        view="zip-transcript-agent-summary",
        provider="codex",
        rows=[row],
        chatlas_root=chatlas_root,
        dry_run=True,
    )

    assert payload["status"] == "ok"
    assert payload["dry_run"] is True
    assert payload["runs"][0]["prepared"]["stage_id"] is None
    assert "<stage-id>" in payload["runs"][0]["prepared"]["output_artifact_path"]
    assert not (chatlas_root / "views" / "_staging").exists()


def test_chatlas_query_rejects_positional_and_legacy_options(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _isolate_agentos(monkeypatch, tmp_path)

    with pytest.raises(SystemExit) as positional_exc:
        main(["chatlas", "query", "session-1"])
    assert positional_exc.value.code == 2
    positional = capsys.readouterr()
    assert positional.out == ""
    assert "unrecognized arguments: session-1" in positional.err

    with pytest.raises(SystemExit) as legacy_exc:
        main(["chatlas", "query", "--updated-since", "3d"])
    assert legacy_exc.value.code == 2
    legacy = capsys.readouterr()
    assert legacy.out == ""
    assert "unrecognized arguments: --updated-since 3d" in legacy.err

    with pytest.raises(SystemExit) as include_exc:
        main(["chatlas", "query", "--include-match"])
    assert include_exc.value.code == 2
    include = capsys.readouterr()
    assert include.out == ""
    assert "unrecognized arguments: --include-match" in include.err


def test_chatlas_query_raw_contains_runs_after_scan_limit(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, _, _ = _isolate_agentos(monkeypatch, tmp_path)
    chatlas_root = home / "Documents" / "chatlas"
    partition = chatlas_root / "index" / "sessions" / "codex" / "fingerprint" / "sessions.index.jsonl"
    raw_old = chatlas_root / "raw" / "old.jsonl"
    raw_new = chatlas_root / "raw" / "new.jsonl"
    _write(raw_old, "needle text lives here\n")
    _write(raw_new, "plain text only\n")
    _write(
        partition,
        "\n".join(
            [
                json.dumps(
                    {
                        "provider": "codex",
                        "uri": "agentos://chat-session/codex/fingerprint/session-old",
                        "session_id": "session-old",
                        "updated_at": "2026-03-08T01:09:01Z",
                        "extractable": True,
                        "primary_backing_artifact": {"path": str(raw_old)},
                    }
                ),
                json.dumps(
                    {
                        "provider": "codex",
                        "uri": "agentos://chat-session/codex/fingerprint/session-new",
                        "session_id": "session-new",
                        "updated_at": "2026-03-09T01:09:01Z",
                        "extractable": True,
                        "primary_backing_artifact": {"path": str(raw_new)},
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
                "query",
                "--sort",
                "newest",
                "--scan-limit",
                "1",
                "--raw-contains",
                "needle",
            ]
        )
        == 0
    )
    limited_payload = json.loads(capsys.readouterr().out)
    _assert_chatlas_query_counts(limited_payload, index_matched=2, candidate=1, query_matched=0, returned=0)
    assert limited_payload["rows"] == []

    assert (
        main(
            [
                "chatlas",
                "query",
                "--sort",
                "newest",
                "--scan-limit",
                "2",
                "--raw-contains",
                "NEEDLE",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    _assert_chatlas_query_counts(payload, index_matched=2, candidate=2, query_matched=1, returned=1)
    assert [row["session_id"] for row in payload["rows"]] == ["session-old"]


def test_chatlas_query_standard_model_contains_filters_visible_roles(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, agentos_home, codex_home = _isolate_agentos(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    _write_codex_rollout(
        rollout_path,
        session_id=session_id,
        user_text="alpha user request",
        assistant_text="beta assistant reply",
    )
    _write_global_config(agentos_home, codex_home=codex_home)

    assert main(["chatlas", "index", "update", "--provider", "codex", "--output-mode", "json"]) == 0
    capsys.readouterr()
    rollout_path.unlink()

    assert main(["chatlas", "query", "--user-contains", "ALPHA", "--assistant-contains", "beta"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [row["session_id"] for row in payload["rows"]] == [session_id]
    assert payload["rows"][0]["home"] == str(codex_home)
    assert str(home / "Documents" / "chatlas" / "raw") not in json.dumps(payload)

    assert main(["chatlas", "query", "--user-contains", "beta"]) == 0
    role_payload = json.loads(capsys.readouterr().out)
    assert role_payload["rows"] == []


def test_chatlas_runtime_does_not_import_deprecated_code() -> None:
    src_root = Path(__file__).resolve().parents[1] / "src" / "agentos"
    matches = [
        path
        for path in src_root.rglob("*.py")
        if "_DEPRECATED" in path.read_text(encoding="utf-8")
    ]

    assert matches == []
