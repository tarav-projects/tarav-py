from __future__ import annotations

import json
from pathlib import Path

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
                        "payload": {"id": session_id},
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-08T01:09:01.000Z",
                        "type": "turn_context",
                        "payload": {"cwd": "/tmp", "title": title},
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
