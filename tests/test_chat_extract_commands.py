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
