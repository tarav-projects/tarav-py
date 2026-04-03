from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentos.cli import main


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _set_iso_mtime(path: Path, timestamp: str) -> None:
    normalized = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
    seconds = datetime.fromisoformat(normalized).astimezone(timezone.utc).timestamp()
    os.utime(path, (seconds, seconds))


def _write_codex_rollout(path: Path, *, session_id: str) -> None:
    records = [
        {
            "timestamp": "2026-03-08T01:08:59.089Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "originator": "codex_cli_rs",
                "source": "cli",
            },
        }
    ]
    _write(path, "\n".join(json.dumps(record) for record in records) + "\n")
    _set_iso_mtime(path, records[0]["timestamp"])


def _write_codex_dialog_rollout(
    path: Path,
    *,
    session_id: str,
    user_text: str = "hello from codex",
    assistant_text: str = "codex reply",
) -> None:
    records = [
        {
            "timestamp": "2026-03-08T01:08:59.089Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "originator": "codex_cli_rs",
                "source": "cli",
            },
        },
        {
            "timestamp": "2026-03-08T01:08:59.093Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"{user_text}<system-reminder>\nmetadata tail",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-03-08T01:08:59.094Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": assistant_text,
                    }
                ],
            },
        },
    ]
    _write(path, "\n".join(json.dumps(record) for record in records) + "\n")
    _set_iso_mtime(path, records[-1]["timestamp"])


def _write_codex_session_index(
    path: Path,
    *,
    session_id: str,
    thread_name: str,
    updated_at: str = "2026-03-10T12:13:33.263726Z",
) -> None:
    _write(
        path,
        json.dumps(
            {
                "id": session_id,
                "thread_name": thread_name,
                "updated_at": updated_at,
            }
        )
        + "\n",
    )


def _write_global_config(
    path: Path,
    *,
    provider_instances: list[dict[str, object]] | None = None,
) -> None:
    _write(
        path,
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "chatlas": {
                    "provider_instances": provider_instances or [],
                },
            }
        ),
    )


def _git_output(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def _chatlas_home_root(agentos_home: Path, home: Path, source_home: Path) -> Path:
    return agentos_home / "chatlas" / "raw" / source_home.relative_to(home)


def test_chatlas_update_mirrors_default_codex_home_and_commits(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    thread_name = "chatlas-default-thread"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )
    _write(home / ".codex" / "notes.md", "# notes\n")
    _write(home / ".codex" / "log" / "skip.txt", "skip\n")
    _write(home / ".codex" / "auth.json", '{"token":"secret"}\n')

    assert main(["chatlas", "update", "--provider", "codex"]) == 0

    payload = json.loads(capsys.readouterr().out)
    chatlas_root = agentos_home / "chatlas"
    source_root = home / ".codex"
    destination_root = _chatlas_home_root(agentos_home, home, source_root)

    assert payload["command"] == "chatlas update"
    assert payload["committed"] is True
    assert payload["changes_detected"] is True
    assert payload["synced_instance_count"] == 1
    assert payload["skipped_instance_count"] == 0
    assert payload["normalized_session_count"] == 1
    assert payload["derived_transcript_session_count"] == 1
    assert payload["derived_summary_count"] == 1
    assert payload["instances"][0]["instance"] == "default"
    assert payload["instances"][0]["destination_root"] == str(destination_root)
    assert payload["manifest_path"] is not None
    assert Path(payload["normalized_sessions_path"]).is_file()
    assert Path(payload["derived_summaries_path"]).is_file()
    assert (
        destination_root
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    ).exists()
    assert (destination_root / "notes.md").exists()
    assert not (destination_root / "log" / "skip.txt").exists()
    assert not (destination_root / "auth.json").exists()
    manifest_path = Path(payload["manifest_path"])
    assert manifest_path.is_file()
    normalized_rows = [
        json.loads(line)
        for line in Path(payload["normalized_sessions_path"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(normalized_rows) == 1
    assert normalized_rows[0]["class"] == "agentos.chatlas.session"
    assert normalized_rows[0]["provider"] == "codex"
    assert normalized_rows[0]["session_id"] == session_id
    assert normalized_rows[0]["display_name"] == thread_name
    assert normalized_rows[0]["native"] == {"thread_name": thread_name}
    derived_md_path = (
        agentos_home
        / "chatlas"
        / "derived"
        / "transcripts"
        / "codex"
        / normalized_rows[0]["provider_instance_fingerprint"]
        / f"{session_id}.md"
    )
    assert derived_md_path.is_file()

    log_subject = _git_output(chatlas_root, "log", "-1", "--pretty=%s")
    assert log_subject.startswith("chatlas update: ")


def test_chatlas_update_second_run_skips_commit_when_unchanged(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )

    assert main(["chatlas", "update", "--provider", "codex"]) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "update", "--provider", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)

    chatlas_root = agentos_home / "chatlas"
    assert payload["changes_detected"] is False
    assert payload["committed"] is False
    assert payload["manifest_path"] is None
    assert payload["commit_message"] is None
    assert _git_output(chatlas_root, "rev-list", "--count", "HEAD") == "1"


def test_chatlas_update_uses_configured_extra_codex_instance(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    extra_codex_home = home / ".codex-jp"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    default_session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    extra_session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd6"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{default_session_id}.jsonl",
        session_id=default_session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=default_session_id,
        thread_name="default-thread",
    )
    _write_codex_rollout(
        extra_codex_home / "sessions" / "2026" / "03" / "26" / f"rollout-2026-03-26T01-05-38-{extra_session_id}.jsonl",
        session_id=extra_session_id,
    )
    _write_codex_session_index(
        extra_codex_home / "session_index.jsonl",
        session_id=extra_session_id,
        thread_name="jp-thread",
    )
    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "instance": "jp",
                "home": str(extra_codex_home),
            }
        ],
    )

    assert main(["chatlas", "update", "--provider", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)

    instance_names = [instance["instance"] for instance in payload["instances"]]

    assert payload["instance_count"] == 2
    assert payload["synced_instance_count"] == 2
    assert instance_names == ["default", "jp"]
    assert (
        _chatlas_home_root(agentos_home, home, home / ".codex")
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-2026-03-25T01-05-38-{default_session_id}.jsonl"
    ).exists()
    assert (
        _chatlas_home_root(agentos_home, home, extra_codex_home)
        / "sessions"
        / "2026"
        / "03"
        / "26"
        / f"rollout-2026-03-26T01-05-38-{extra_session_id}.jsonl"
    ).exists()
    assert payload["normalized_session_count"] == 2


def test_chatlas_stats_reports_normalized_counts(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name="stats-thread",
    )

    assert main(["chatlas", "update", "--provider", "codex"]) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "stats"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "chatlas stats"
    assert payload["stats"]["session_count"] == 1
    assert payload["stats"]["provider_count"] == 1
    assert payload["stats"]["derived_transcript_session_count"] == 1
    assert payload["stats"]["derived_summary_count"] == 1
    assert payload["stats"]["by_provider"][0]["provider"] == "codex"
    assert payload["stats"]["last_update_recorded_at"] is not None
    assert payload["stats"]["last_update_manifest_path"] is not None


def test_chatlas_query_matches_normalized_thread_name(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    thread_name = "query-thread"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(["chatlas", "update", "--provider", "codex"]) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "query", thread_name]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "chatlas query"
    assert payload["session_count"] == 1
    session = payload["sessions"][0]
    assert session["provider"] == "codex"
    assert session["session_id"] == session_id
    assert session["display_name"] == thread_name
    assert session["native"] == {"thread_name": thread_name}
    assert session["match"]["fields"] == [{"field": "thread_name", "value": thread_name}]
    assert session["summary"]["turn_count"] == 0


def test_chatlas_query_supports_user_contain_transcript_filter(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_dialog_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
        user_text="searchable user text",
        assistant_text="other assistant text",
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name="content-query-thread",
    )

    assert main(["chatlas", "update", "--provider", "codex"]) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "query", "--user-contain", "searchable user"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["session_count"] == 1
    assert payload["selection"]["query"] is None
    assert payload["selection"]["user_contain"] == "searchable user"
    assert payload["sessions"][0]["transcript_filter_match"] == {"user_contain": "searchable user"}
    assert payload["sessions"][0]["summary"]["first_user_text"] == "searchable user text"


def test_chatlas_query_supports_text_contain_filter(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_dialog_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl",
        session_id=session_id,
        user_text="neutral user text",
        assistant_text="assistant searchable phrase",
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name="text-filter-thread",
    )

    assert main(["chatlas", "update", "--provider", "codex"]) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "query", "--text-contain", "searchable phrase"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["session_count"] == 1
    assert payload["sessions"][0]["transcript_filter_match"] == {"text_contain": "searchable phrase"}
    assert payload["sessions"][0]["summary"]["last_assistant_text"] == "assistant searchable phrase"


def test_chatlas_export_returns_derived_markdown_transcript(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    thread_name = "export-thread"
    rollout_path = home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    _write_codex_dialog_rollout(
        rollout_path,
        session_id=session_id,
        user_text="markdown export user",
        assistant_text="markdown export assistant",
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name=thread_name,
    )

    assert main(["chatlas", "update", "--provider", "codex"]) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "export", thread_name]) == 0
    output = capsys.readouterr().out

    assert "### USER [2026-03-08T01:08:59.093Z]" in output
    assert "markdown export user" in output
    assert "markdown export assistant" in output
    assert "<system-reminder>" not in output


def test_chatlas_export_supports_jsonl_transcript_output(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    rollout_path = home / ".codex" / "sessions" / "2026" / "03" / "25" / f"rollout-2026-03-25T01-05-38-{session_id}.jsonl"
    _write_codex_dialog_rollout(
        rollout_path,
        session_id=session_id,
        user_text="jsonl export user",
        assistant_text="jsonl export assistant",
    )
    _write_codex_session_index(
        home / ".codex" / "session_index.jsonl",
        session_id=session_id,
        thread_name="jsonl-export-thread",
    )

    assert main(["chatlas", "update", "--provider", "codex"]) == 0
    _ = json.loads(capsys.readouterr().out)

    assert main(["chatlas", "export", session_id, "--format", "jsonl"]) == 0
    payload_lines = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]

    assert [line["role"] for line in payload_lines] == ["user", "assistant"]
    assert payload_lines[0]["text"] == "jsonl export user"
    assert payload_lines[1]["text"] == "jsonl export assistant"
