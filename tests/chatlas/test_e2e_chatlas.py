from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli.cli import main
from agentos.chatlas.local import chatlas_local_sync
from ._e2e_helpers import (
    _configure_chatlas,
    _index_rows,
    _isolate_chatlas,
    _write_codex_custom_tool_rollout,
    _write_codex_rollout,
)
from ._helpers import captured_json, write_text_file


def _doctor_row(chatlas_root: Path) -> dict[str, object]:
    artifact_path = (
        chatlas_root / "raw" / "codex" / "fingerprint" / "home" / "session-1.jsonl"
    )
    return {
        "uri": "agentos://chat-session/codex/fingerprint/session-1",
        "provider": "codex",
        "session_id": "session-1",
        "last_activity_at": "2026-03-08T01:09:01.000Z",
        "display_name": None,
        "display_name_field": None,
        "home": "/tmp/codex-home",
        "project_path": None,
        "instance": "codex-work",
        "provider_instance_fingerprint": "fingerprint",
        "identity_hash": "ab-session-1",
        "primary_backing_artifact": {"path": str(artifact_path)},
        "backing_artifacts": [{"path": str(artifact_path)}],
        "extractable": True,
    }


def test_event_pattern_cli_uses_sqlite_candidates_and_normal_model_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fa1"
    _write_codex_rollout(
        codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-{session_id}.jsonl",
        session_id=session_id,
        messages=[
            ("assistant", "candidate: POI.Class"),
            ("user", "::approve POI.Class"),
        ],
    )
    _configure_chatlas(environment, codex_home)
    assert (
        main(
            [
                "chatlas",
                "index",
                "update",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["chatlas", "events", "index", "--json"]) == 0
    index_payload = captured_json(capsys)
    assert index_payload["session_count"] == 1

    pattern = json.dumps(
        {
            "steps": [
                {"role": "assistant", "text_contains": "candidate:"},
                {"role": "user", "text_exact": "::approve POI.Class"},
            ]
        }
    )
    assert (
        main(
            [
                "chatlas",
                "events",
                "query",
                "--session-id",
                session_id,
                "--pattern-json",
                pattern,
                "--backend",
                "sqlite",
                "--json",
            ]
        )
        == 0
    )
    payload = captured_json(capsys)

    assert payload["backend_used"] == "sqlite"
    assert payload["match_count"] == 1
    assert [event["payload"]["role"] for event in payload["matches"][0]["events"]] == [
        "assistant",
        "user",
    ]
    assert payload["matches"][0]["events"][1]["payload"]["content"][0]["text"] == (
        "::approve POI.Class"
    )

    assert (
        main(
            [
                "chatlas",
                "turns",
                "query",
                "--session-id",
                session_id,
                "--verbatim",
                "- [DF] APPROVE, poi class! ^c20260731-99u",
                "--producer-type",
                "human",
                "--role",
                "user",
                "--after",
                "2026-03-08T01:09:02Z",
                "--before",
                "2026-03-08T01:09:04Z",
                "--backend",
                "sqlite",
                "--detail",
                "turn",
                "--json",
            ]
        )
        == 0
    )
    turns_payload = captured_json(capsys)

    assert turns_payload["command"] == "chatlas turns query"
    assert turns_payload["backend_used"] == "sqlite"
    assert turns_payload["match_count"] == 1
    turn = turns_payload["turns"][0]
    assert turn["turn_ref"]["session"] == turn["session_identity"]
    assert turn["turn_ref"]["turn_id"] == turn["normal_turn"]["turn_id"]
    assert len(turn["turn_ref"]["turn_hash"]) == 64
    assert turns_payload["turns"][0]["normal_turn"]["events"][0]["payload"][
        "content"
    ][0]["text"] == "::approve POI.Class"


def test_chatlas_local_sync_exports_project_chats_turns_only_and_skips_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    home = environment.home
    project_parent = tmp_path / "workspace" / "project-a"
    project_root = project_parent / "nested"
    other_project = tmp_path / "workspace" / "project-b"
    for project in (project_parent, project_root, other_project):
        project.mkdir(parents=True)
        environment.write_project_marker(project)

    sessions = {
        "current": "019ccafa-7835-7fc3-ac17-0e0a0f675fd5",
        "ancestor": "019ccafa-7835-7fc3-ac17-0e0a0f675fd6",
        "other": "019ccafa-7835-7fc3-ac17-0e0a0f675fd7",
    }
    _write_codex_rollout(
        codex_home
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-{sessions['current']}.jsonl",
        session_id=sessions["current"],
        cwd=str(project_root),
        tool_calls=[("Read", {"path": "secret.txt"})],
    )
    _write_codex_rollout(
        codex_home
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-{sessions['ancestor']}.jsonl",
        session_id=sessions["ancestor"],
        cwd=str(project_parent),
    )
    _write_codex_rollout(
        codex_home
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-{sessions['other']}.jsonl",
        session_id=sessions["other"],
        cwd=str(other_project),
    )
    _configure_chatlas(environment, codex_home)
    assert (
        main(
            [
                "chatlas",
                "index",
                "update",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )

    chatlas_root = home / "Documents" / "chatlas"
    bad_row = dict(_index_rows(chatlas_root)[0])
    bad_row.update(
        {
            "session_id": "broken-session",
            "identity_hash": "ab-broken-session",
            "uri": "agentos://chat-session/codex/fingerprint/broken-session",
            "project_path": str(project_root),
            "primary_backing_artifact": {"path": str(tmp_path / "missing.jsonl")},
            "backing_artifacts": [{"path": str(tmp_path / "missing.jsonl")}],
        }
    )
    partition = (
        chatlas_root / "index" / "sessions" / "codex" / "ab" / "sessions.index.jsonl"
    )
    partition.parent.mkdir(parents=True, exist_ok=True)
    with partition.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(bad_row) + "\n")

    payload = chatlas_local_sync(project=project_root)

    assert payload["written_count"] == 2
    assert payload["skipped_count"] == 1
    assert payload["total_local_session_count"] == 2
    exported_files = sorted((project_root / "chatlas").glob("*.json"))
    assert [path.name for path in exported_files if path.name != "manifest.json"] == [
        f"{row['identity_hash']}.json"
        for row in sorted(
            (
                row
                for row in _index_rows(chatlas_root)
                if row["session_id"] in {sessions["current"], sessions["ancestor"]}
            ),
            key=lambda row: str(row["identity_hash"]),
        )
    ]
    for path in exported_files:
        if path.name == "manifest.json":
            continue
        model = json.loads(path.read_text(encoding="utf-8"))
        assert "normalization" not in model
        assert "sources" not in model
        assert {event["kind"] for event in model["chat"]["events"]} == {"message"}
        assert model["chat"]["tool_invocations"] == []


def test_chatlas_local_cli_sync_is_idempotent_and_status_reports_buckets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    project_root = tmp_path / "workspace" / "project-a"
    project_root.mkdir(parents=True)
    environment.write_project_marker(project_root)
    other_project = tmp_path / "workspace" / "project-b"
    other_project.mkdir(parents=True)
    environment.write_project_marker(other_project)

    project_session = "019ccafa-7835-7fc3-ac17-0e0a0f675fe1"
    other_session = "019ccafa-7835-7fc3-ac17-0e0a0f675fe2"
    _write_codex_rollout(
        codex_home
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-{project_session}.jsonl",
        session_id=project_session,
        cwd=str(project_root),
    )
    _write_codex_rollout(
        codex_home
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-{other_session}.jsonl",
        session_id=other_session,
        cwd=str(other_project),
    )
    _configure_chatlas(environment, codex_home)
    assert (
        main(
            [
                "chatlas",
                "index",
                "update",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    monkeypatch.chdir(project_root)
    assert main(["chatlas", "local", "sync", "--project", "--json"]) == 0
    sync_payload = captured_json(capsys)
    assert sync_payload["project_root"] == str(project_root.resolve())
    assert sync_payload["written_count"] == 1
    assert sync_payload["skipped_count"] == 0
    local_root = project_root / "chatlas"
    first_sync_files = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(local_root.glob("*.json"))
    }

    manual_file = local_root / "manual-port.json"
    manual_file.write_text(json.dumps({"manual": True}) + "\n", encoding="utf-8")
    assert main(["chatlas", "local", "sync", "--project", "--json"]) == 0
    second_sync_payload = captured_json(capsys)
    assert second_sync_payload["written_count"] == 1
    assert manual_file.is_file()
    assert {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(local_root.glob("*.json"))
        if path.name in first_sync_files
    } == first_sync_files

    assert main(["chatlas", "local", "status", "--project", "--json"]) == 0
    status_payload = captured_json(capsys)
    assert status_payload["project_root"] == str(project_root.resolve())
    assert status_payload["attributed_and_present_count"] == 1
    assert status_payload["attributed_and_missing_count"] == 0
    assert status_payload["present_but_not_attributed_count"] == 1
    assert (
        status_payload["present_but_not_attributed"][0]["identity_hash"]
        == "manual-port"
    )

    assert main(["chatlas", "local", "--project", "--json"]) == 0
    status_payload = captured_json(capsys)
    assert status_payload["attributed_and_present_count"] == 1
    assert status_payload["attributed_and_missing_count"] == 0
    assert status_payload["present_but_not_attributed_count"] == 1
    assert (
        status_payload["present_but_not_attributed"][0]["identity_hash"]
        == "manual-port"
    )


def test_chatlas_index_update_query_export_and_raw_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    home = environment.home
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = (
        codex_home
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-fixture-{session_id}.jsonl"
    )
    index_path = codex_home / "session_index.jsonl"
    _write_codex_rollout(
        rollout_path,
        session_id=session_id,
        title="chatlas source",
        cwd=str(tmp_path / "workspace"),
    )
    write_text_file(
        index_path,
        json.dumps({"id": session_id, "thread_name": "chatlas source"}) + "\n",
    )
    _configure_chatlas(environment, codex_home)

    assert (
        main(
            [
                "chatlas",
                "index",
                "update",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )
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

    assert main(["chatlas", "query", "--session-id", session_id, "--json"]) == 0
    query_payload = captured_json(capsys)
    assert query_payload["returned_row_count"] == 1
    assert query_payload["rows"][0]["summary"]["last_assistant_text_excerpt"] == "hi"

    assert (
        main(
            [
                "chatlas",
                "views",
                "get",
                "--session-id",
                session_id,
                "--view",
                "zip-transcript",
                "--json",
            ]
        )
        == 0
    )
    export_payload = captured_json(capsys)
    assert export_payload["class"] == "agentos_chatlas.zip_transcript"
    assert [turn["role"] for turn in export_payload["turns"]] == ["user", "assistant"]

    assert (
        main(["chatlas", "raw", "path", "--session-id", session_id, "--json"])
        == 0
    )
    raw_payload = captured_json(capsys)
    assert raw_payload["session"]["session_id"] == session_id
    assert all(str(chatlas_root / "raw") in path for path in raw_payload["paths"])
    assert all(str(codex_home) not in path for path in raw_payload["paths"])


def test_chatlas_index_redo_rebuilds_from_raw_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = (
        codex_home
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-fixture-{session_id}.jsonl"
    )
    index_path = codex_home / "session_index.jsonl"
    _write_codex_rollout(
        rollout_path,
        session_id=session_id,
        title="redo from raw",
        cwd=str(tmp_path / "workspace"),
    )
    write_text_file(
        index_path,
        json.dumps({"id": session_id, "thread_name": "redo from raw"}) + "\n",
    )
    _configure_chatlas(environment, codex_home)

    assert (
        main(
            [
                "chatlas",
                "index",
                "update",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )
    captured_json(capsys)
    chatlas_root = environment.home / "Documents" / "chatlas"
    assert [row["session_id"] for row in _index_rows(chatlas_root)] == [session_id]

    rollout_path.unlink()
    index_path.unlink()

    assert (
        main(
            [
                "chatlas",
                "index",
                "redo",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )
    redo_payload = captured_json(capsys)

    assert redo_payload["phase"] == "index-redo"
    assert redo_payload["session_index"]["upserted_row_count"] == 1
    assert [row["session_id"] for row in _index_rows(chatlas_root)] == [session_id]


def test_chatlas_index_update_skips_sessions_with_symlinked_source_ancestors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    real_sessions = tmp_path / "real-sessions"
    rollout_path = (
        real_sessions / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    )
    index_path = codex_home / "session_index.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id, title="symlink source")
    write_text_file(
        index_path,
        json.dumps({"id": session_id, "thread_name": "symlink source"}) + "\n",
    )
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / "sessions").symlink_to(real_sessions, target_is_directory=True)
    _configure_chatlas(environment, codex_home)

    assert (
        main(
            [
                "chatlas",
                "index",
                "update",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )
    update_payload = captured_json(capsys)

    assert update_payload["native_scan"]["session_count"] == 0
    assert update_payload["session_index"]["upserted_row_count"] == 0


def test_chatlas_provider_query_ignores_sessions_with_symlinked_source_ancestors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    real_sessions = tmp_path / "real-sessions"
    rollout_path = (
        real_sessions / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    )
    index_path = codex_home / "session_index.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id, title="symlink source")
    write_text_file(
        index_path,
        json.dumps({"id": session_id, "thread_name": "symlink source"}) + "\n",
    )
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / "sessions").symlink_to(real_sessions, target_is_directory=True)
    _configure_chatlas(environment, codex_home)

    assert (
        main(
            [
                "chatlas",
                "provider",
                "query",
                "--provider",
                "codex",
                "--session-id",
                session_id,
                "--json",
            ]
        )
        == 0
    )
    payload = captured_json(capsys)

    assert payload["rows"] == [
        {
            "session_id": session_id,
            "provider": "codex",
            "found": False,
        }
    ]


def test_chatlas_stats_and_doctor_cover_index_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, _ = _isolate_chatlas(monkeypatch, tmp_path)
    home = environment.home
    chatlas_root = home / "Documents" / "chatlas"
    row = _doctor_row(chatlas_root)
    artifact_path = Path(row["primary_backing_artifact"]["path"])
    write_text_file(artifact_path, "{}\n")
    write_text_file(
        chatlas_root / "index" / "sessions" / "codex" / "ab" / "sessions.index.jsonl",
        json.dumps(row) + "\n",
    )
    write_text_file(
        chatlas_root / "raw" / "codex" / "fingerprint" / "manifest.json",
        json.dumps(
            {
                "class": "agentos_chatlas.raw_partition_manifest",
                "schema_version": 1,
                "provider": "codex",
                "provider_instance_fingerprint": "fingerprint",
            }
        )
        + "\n",
    )

    assert main(["chatlas", "stats", "--json"]) == 0
    stats_payload = captured_json(capsys)
    assert stats_payload["stats"]["session_count"] == 1
    assert stats_payload["stats"]["provider_count"] == 1
    assert stats_payload["by_provider"]["codex"]["session_count"] == 1

    assert main(["chatlas", "index", "doctor", "--json"]) == 0
    doctor_payload = captured_json(capsys)
    assert doctor_payload["summary"]["row_count"] == 1
    assert doctor_payload["summary"]["error_count"] == 0
    assert doctor_payload["summary"]["warning_count"] == 1
    policy_check = next(
        check
        for check in doctor_payload["checks"]
        if check["name"] == "unexpected_null_fields"
    )
    assert policy_check["status"] == "warning"
    assert policy_check["mode"] == "policy"
    assert policy_check["field_counts"] == {"project_path": 1}
    assert policy_check["total_null_count"] == 1
    assert policy_check["nullable_fields"] == ["display_name", "display_name_field"]

    assert main(["chatlas", "index", "doctor"]) == 0
    markdown_output = capsys.readouterr().out
    assert "Non-ok checks:" in markdown_output
    assert (
        "- unexpected_null_fields: 0 errors, 1 warnings, 1 samples" in markdown_output
    )
    assert "  Field breakdown:" in markdown_output
    assert "  - project_path: 1" in markdown_output

    assert (
        main(
            ["chatlas", "index", "doctor", "--null-fields", "warn", "--json"]
        )
        == 0
    )
    warn_payload = captured_json(capsys)
    null_check = next(
        check for check in warn_payload["checks"] if check["name"] == "null_fields"
    )
    assert warn_payload["summary"]["warning_count"] == 3
    assert null_check["status"] == "warning"
    assert null_check["mode"] == "warn"
    assert null_check["warning_count"] == 3
    assert null_check["field_counts"] == {
        "display_name": 1,
        "display_name_field": 1,
        "project_path": 1,
    }
    assert null_check["total_null_count"] == 3

    assert (
        main(
            ["chatlas", "index", "doctor", "--null-fields", "error", "--json"]
        )
        == 1
    )
    error_payload = captured_json(capsys)
    null_check = next(
        check for check in error_payload["checks"] if check["name"] == "null_fields"
    )
    assert error_payload["summary"]["error_count"] == 3
    assert null_check["status"] == "error"
    assert null_check["mode"] == "error"
    assert null_check["error_count"] == 3

    assert (
        main(
            [
                "chatlas",
                "index",
                "doctor",
                "--null-fields",
                "ignore",
                "--json",
            ]
        )
        == 0
    )
    ignore_payload = captured_json(capsys)
    assert {check["name"] for check in ignore_payload["checks"]}.isdisjoint(
        {"unexpected_null_fields", "null_fields"}
    )


def test_chatlas_query_uses_indexed_summary_without_raw_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, _ = _isolate_chatlas(monkeypatch, tmp_path)
    home = environment.home
    partition = (
        home
        / "Documents"
        / "chatlas"
        / "index"
        / "sessions"
        / "codex"
        / "ab"
        / "sessions.index.jsonl"
    )
    rows = [
        {
            "provider": "codex",
            "uri": "agentos://chat-session/codex/fingerprint/high",
            "identity_hash": "ab-high",
            "session_id": "high",
            "last_activity_at": "2026-03-09T01:09:01.000Z",
            "summary": {"visible_user_turn_count": 6},
        },
        {
            "provider": "codex",
            "uri": "agentos://chat-session/codex/fingerprint/low",
            "identity_hash": "ab-low",
            "session_id": "low",
            "last_activity_at": "2026-03-08T01:09:01.000Z",
            "summary": {"visible_user_turn_count": 5},
        },
        {
            "provider": "codex",
            "uri": "agentos://chat-session/codex/fingerprint/missing",
            "identity_hash": "ab-missing",
            "session_id": "missing",
            "last_activity_at": "2026-03-10T01:09:01.000Z",
        },
    ]
    write_text_file(partition, "\n".join(json.dumps(row) for row in rows) + "\n")

    assert main(["chatlas", "query", "--min-user-turns", "6", "--sort", "newest", "--json"]) == 0
    payload = captured_json(capsys)
    assert payload["index_matched_row_count"] == 3
    assert payload["query_matched_row_count"] == 1
    assert [row["session_id"] for row in payload["rows"]] == ["high"]
    assert not (home / "Documents" / "chatlas" / "raw").exists()


def test_chatlas_project_selectors_use_exact_indexed_project_path_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, _ = _isolate_chatlas(monkeypatch, tmp_path)
    home = environment.home
    workspace = tmp_path / "workspace"
    agentos_md = workspace / "agentos-md"
    agentos_md_extra = workspace / "agentos-md-extra"
    other_agentos_md = tmp_path / "other" / "agentos-md"
    for project_path in (agentos_md, agentos_md_extra, other_agentos_md):
        project_path.mkdir(parents=True)
    partition = (
        home
        / "Documents"
        / "chatlas"
        / "index"
        / "sessions"
        / "codex"
        / "ab"
        / "sessions.index.jsonl"
    )
    rows = [
        {
            "provider": "codex",
            "uri": "agentos://chat-session/codex/fingerprint/main",
            "identity_hash": "ab-main",
            "session_id": "main",
            "last_activity_at": "2026-03-09T01:09:01.000Z",
            "project_path": str(agentos_md),
            "summary": {"visible_user_turn_count": 3},
        },
        {
            "provider": "codex",
            "uri": "agentos://chat-session/codex/fingerprint/suffix",
            "identity_hash": "ab-suffix",
            "session_id": "suffix",
            "last_activity_at": "2026-03-10T01:09:01.000Z",
            "project_path": str(agentos_md_extra),
            "summary": {"visible_user_turn_count": 3},
        },
        {
            "provider": "codex",
            "uri": "agentos://chat-session/codex/fingerprint/other",
            "identity_hash": "ab-other",
            "session_id": "other",
            "last_activity_at": "2026-03-11T01:09:01.000Z",
            "project_path": str(other_agentos_md),
            "summary": {"visible_user_turn_count": 3},
        },
        {
            "provider": "codex",
            "uri": "agentos://chat-session/codex/fingerprint/missing",
            "identity_hash": "ab-missing",
            "session_id": "missing",
            "last_activity_at": "2026-03-12T01:09:01.000Z",
            "summary": {"visible_user_turn_count": 3},
        },
    ]
    write_text_file(partition, "\n".join(json.dumps(row) for row in rows) + "\n")

    assert (
        main(
            [
                "chatlas",
                "index",
                "query",
                "--project-base",
                "agentos-md",
                "--sort",
                "lexical",
                "--json",
            ]
        )
        == 0
    )
    index_payload = captured_json(capsys)
    assert index_payload["filters"]["project_base"] == "agentos-md"
    assert index_payload["index_matched_row_count"] == 2
    assert {row["session_id"] for row in index_payload["rows"]} == {"main", "other"}

    selector_path = agentos_md / "."
    assert (
        main(
            [
                "chatlas",
                "query",
                "--project",
                str(selector_path),
                "--min-user-turns",
                "3",
                "--json",
            ]
        )
        == 0
    )
    query_payload = captured_json(capsys)
    assert query_payload["filters"]["project"] == str(agentos_md.resolve())
    assert query_payload["index_matched_row_count"] == 1
    assert query_payload["query_matched_row_count"] == 1
    assert [row["session_id"] for row in query_payload["rows"]] == ["main"]

    assert (
        main(
            [
                "chatlas",
                "raw",
                "path",
                "--project",
                str(selector_path),
                "--json",
            ]
        )
        == 0
    )
    raw_payload = captured_json(capsys)
    assert raw_payload["session"]["session_id"] == "main"


def test_codex_custom_tool_raw_input_survives_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675099"
    patch = "*** Begin Patch\n*** Update File: src/alpha.py\n*** End Patch\n"
    _write_codex_custom_tool_rollout(
        codex_home / "sessions" / "2026" / "03" / "08" / f"rollout-{session_id}.jsonl",
        session_id=session_id,
        tool_input=patch,
    )
    _configure_chatlas(environment, codex_home)
    assert (
        main(
            [
                "chatlas",
                "index",
                "update",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "chatlas",
                "views",
                "get",
                "--session-id",
                session_id,
                "--json",
            ]
        )
        == 0
    )
    model = captured_json(capsys)

    call_event = next(
        event for event in model["chat"]["events"] if event["kind"] == "tool.call"
    )
    invocation = model["chat"]["tool_invocations"][0]
    expected_input = {"arguments": patch, "arguments_format": "raw_string"}
    assert call_event["payload"]["input"] == expected_input
    assert invocation["input"] == expected_input
    assert "invalid json arguments" not in json.dumps(model["normalization"])


def test_chatlas_file_edition_pois_cli_supports_session_and_file_queries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675098"
    patch = (
        "*** Begin Patch\n"
        "*** Update File: src/alpha.py\n"
        "*** Add File: src/beta.py\n"
        "+new\n"
        "*** End Patch\n"
    )
    _write_codex_custom_tool_rollout(
        codex_home / "sessions" / "2026" / "03" / "08" / f"rollout-{session_id}.jsonl",
        session_id=session_id,
        tool_input=patch,
    )
    _configure_chatlas(environment, codex_home)
    assert (
        main(
            [
                "chatlas",
                "index",
                "update",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "chatlas",
                "file-edition-pois",
                "--session",
                session_id,
                "--limit",
                "1",
                "--json",
            ]
        )
        == 0
    )
    unfiltered = captured_json(capsys)
    assert unfiltered["session"] == session_id
    assert [poi["file"] for poi in unfiltered["pois"]] == ["src/alpha.py"]

    assert (
        main(
            [
                "chatlas",
                "file-edition-pois",
                "--session",
                session_id,
                "--file",
                "/repo/src/beta.py",
                "--json",
            ]
        )
        == 0
    )
    filtered = captured_json(capsys)
    assert filtered["file"] == "/repo/src/beta.py"
    assert [poi["file"] for poi in filtered["pois"]] == ["src/beta.py"]


def test_chatlas_selector_errors_are_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate_chatlas(monkeypatch, tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(["chatlas", "export", "--json"])
    assert exc_info.value.code == 2
    assert "invalid choice: 'export'" in capsys.readouterr().err

    assert main(["chatlas", "views", "get", "--json"]) == 1
    assert (
        "chatlas views get requires at least one index query selector option"
        in capsys.readouterr().err
    )

    assert main(["chatlas", "views", "get", "--view", "zip-transcript", "--json"]) == 1
    assert (
        "requires at least one index query selector option" in capsys.readouterr().err
    )
