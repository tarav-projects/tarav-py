from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.chatlas.views import compute_chatlas_view_cache_key, resolve_chatlas_view_slot_path
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


def test_chatlas_view_cache_key_is_stable_and_uses_only_view_identity(tmp_path: Path) -> None:
    parameters = [
        {
            "type": "chatlas.indexed-session",
            "session_id": "session-1",
            "uri": "agentos://chat-session/codex/fingerprint/session-1",
        }
    ]
    first = compute_chatlas_view_cache_key(view="zip-transcript", parameters=parameters)
    second = compute_chatlas_view_cache_key(
        view="zip-transcript",
        parameters=json.loads(json.dumps(parameters)),
    )

    assert first == second
    assert (
        resolve_chatlas_view_slot_path(
            view="zip-transcript",
            cache_key=first,
            chatlas_root=tmp_path / "chatlas",
        )
        == tmp_path / "chatlas" / "views" / "zip-transcript" / first
    )


def test_chatlas_views_list_reports_static_workflows(capsys) -> None:
    assert main(["chatlas", "views", "list"]) == 0

    payload = json.loads(capsys.readouterr().out)
    view_names = {view["name"] for view in payload["views"]}
    assert payload["status"] == "ok"
    assert "zip-transcript" in view_names
    assert "zip-transcript-agent-summary" in view_names


def test_chatlas_views_zip_transcript_materializes_from_index_selection(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home, agentos_home, codex_home = _isolate_agentos(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id, title="view source")
    _write_global_config(agentos_home, codex_home=codex_home)

    assert main(["chatlas", "index", "update", "--provider", "codex", "--output-mode", "json"]) == 0
    capsys.readouterr()
    rollout_path.unlink()

    assert main(["chatlas", "views", "get", "--view", "zip-transcript", "--session-id", session_id]) == 0
    payload = json.loads(capsys.readouterr().out)
    artifact_path = Path(payload["view"]["artifact"]["primary_path"])
    manifest_path = artifact_path.parent / "manifest.json"

    assert payload["status"] == "ok"
    assert payload["view"]["name"] == "zip-transcript"
    assert payload["view"]["state"] == "produced"
    assert artifact_path.is_file()
    assert manifest_path.is_file()
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["class"] == "agentos.chatlas.zip_transcript"
    assert artifact["session"]["session_id"] == session_id
    assert [turn["role"] for turn in artifact["turns"]] == ["user", "assistant"]
    assert str(home / "Documents" / "chatlas" / "views") in str(artifact_path)

    assert main(["chatlas", "views", "status", "--view", "zip-transcript", "--session-id", session_id]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["view"]["state"] == "fresh"

    assert main(["chatlas", "views", "path", "--view", "zip-transcript", "--session-id", session_id]) == 0
    assert capsys.readouterr().out.strip() == str(artifact_path)

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
    export_payload = json.loads(capsys.readouterr().out)
    assert export_payload["class"] == "agentos.chatlas.zip_transcript"


def test_chatlas_views_reuse_index_selector_errors(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _isolate_agentos(monkeypatch, tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(["chatlas", "views", "get", "--view", "zip-transcript", "session-1"])
    assert exc_info.value.code == 2
    assert "unrecognized arguments: session-1" in capsys.readouterr().err

    assert main(["chatlas", "views", "get", "--view", "zip-transcript"]) == 1
    assert "requires at least one index query selector option" in capsys.readouterr().err

    assert main(["chatlas", "views", "get", "--view", "unknown", "--session-id", "x"]) == 1
    assert "unknown Chatlas view: unknown" in capsys.readouterr().err


def test_chatlas_views_external_summary_stage_commit_and_stale_retention(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _, agentos_home, codex_home = _isolate_agentos(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-fixture-{session_id}.jsonl"
    _write_codex_rollout(rollout_path, session_id=session_id, title="summary source")
    _write_global_config(agentos_home, codex_home=codex_home)

    assert main(["chatlas", "index", "update", "--provider", "codex", "--output-mode", "json"]) == 0
    capsys.readouterr()

    summary_selector = [
        "chatlas",
        "views",
        "status",
        "--view",
        "zip-transcript-agent-summary",
        "--session-id",
        session_id,
    ]
    assert main(summary_selector) == 0
    missing_payload = json.loads(capsys.readouterr().out)
    assert missing_payload["view"]["state"] == "production_required"

    assert (
        main(
            [
                "chatlas",
                "views",
                "stage",
                "--view",
                "zip-transcript-agent-summary",
                "--session-id",
                session_id,
            ]
        )
        == 0
    )
    stage_payload = json.loads(capsys.readouterr().out)
    stage_id = stage_payload["stage"]["stage_id"]

    assert main(["chatlas", "views", "commit", "--stage-id", stage_id]) == 1
    assert "missing staged Chatlas view artifact" in capsys.readouterr().err

    stage_path = Path(stage_payload["stage"]["path"])
    _write(stage_path / "summary.md", "# Summary\n\nShort summary.\n")
    assert main(["chatlas", "views", "commit", "--stage-id", stage_id]) == 0
    commit_payload = json.loads(capsys.readouterr().out)
    summary_path = Path(commit_payload["view"]["artifact"]["primary_path"])
    assert commit_payload["view"]["state"] == "fresh"
    assert summary_path.read_text(encoding="utf-8").startswith("# Summary")

    index_row = _chatlas_index_rows(summary_path.parents[3])[0]
    index_row["display_name"] = "changed source"
    partition = summary_path.parents[3] / "index" / "sessions" / "codex" / "fingerprint" / "sessions.index.jsonl"
    if not partition.exists():
        partition = next((summary_path.parents[3] / "index" / "sessions").rglob("*.jsonl"))
    _write(partition, json.dumps(index_row) + "\n")

    assert main(summary_selector + ["--explain"]) == 0
    stale_payload = json.loads(capsys.readouterr().out)
    assert stale_payload["view"]["state"] == "production_required"
    assert summary_path.is_file()
