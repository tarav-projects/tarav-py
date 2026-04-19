from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli import main


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_codex_rollout(
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
            "timestamp": "2026-03-08T01:08:59.091Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": "<permissions instructions>\ninternal developer message",
                    }
                ],
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


def _write_project_marker(project_root: Path) -> None:
    _write(
        project_root / ".agentos" / "project.json",
        json.dumps(
            {
                "class": "agentos.project",
                "schema_version": 1,
                "project_id": "00000000-0000-4000-8000-000000000001",
            }
        )
        + "\n",
    )


def _write_project_config(
    path: Path,
    *,
    provider_instances: list[dict[str, object]] | None = None,
) -> None:
    _write(
        path,
        json.dumps(
            {
                "class": "agentos.project.config",
                "schema_version": 1,
                "chat": {
                    "provider_instances": provider_instances or [],
                },
            }
        )
        + "\n",
    )


def test_chat_debug_extract_supports_live_provider_lookup(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "08" / f"rollout-2026-03-08T01-05-38-{session_id}.jsonl",
        session_id=session_id,
    )

    assert main(["chat", "debug", "extract", session_id]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload[0]["text"] == "hello from codex"
    assert payload[1]["text"] == "codex reply"


def test_chat_debug_extract_supports_file_mode_markdown(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rollout_path = tmp_path / "codex-rollout.jsonl"
    _write_codex_rollout(
        rollout_path,
        session_id="019ccafa-7835-7fc3-ac17-0e0a0f675fd5",
        user_text="markdown user",
        assistant_text="markdown assistant",
    )

    assert main(["chat", "debug", "extract", "--format", "markdown", "--file", str(rollout_path)]) == 0
    output = capsys.readouterr().out

    assert "### USER [2026-03-08T01:08:59.093Z]" in output
    assert "```markdown" in output
    assert "markdown assistant" in output


def test_chat_debug_extract_raw_includes_developer_content(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rollout_path = tmp_path / "codex-rollout.jsonl"
    _write_codex_rollout(
        rollout_path,
        session_id="019ccafa-7835-7fc3-ac17-0e0a0f675fd5",
    )

    assert main(["chat", "debug", "extract", "--raw", "--file", str(rollout_path)]) == 0
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert [turn["role"] for turn in payload[:3]] == ["developer", "user", "assistant"]


def test_chat_debug_extract_supports_explicit_project_target(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    project_root = tmp_path / "project"
    workspace = tmp_path / "workspace"
    home.mkdir()
    project_root.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(workspace)

    _write_project_marker(project_root)
    _write_project_config(
        project_root / ".agentos" / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "project-codex",
                "home": str(home / ".codex"),
            }
        ],
    )

    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        home / ".codex" / "sessions" / "2026" / "03" / "08" / f"rollout-2026-03-08T01-05-38-{session_id}.jsonl",
        session_id=session_id,
        user_text="project override user",
        assistant_text="project override assistant",
    )

    assert (
        main(
            [
                "chat",
                "debug",
                "extract",
                session_id,
                "--project",
                str(project_root),
            ]
        )
        == 0
    )
    payload = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert payload[0]["text"] == "project override user"
    assert payload[1]["text"] == "project override assistant"
