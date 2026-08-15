from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.cli.cli import main
from tarav.testing import TaravTestEnvironment


def _write_codex_rollout(
    path: Path,
    *,
    session_id: str,
    messages: list[tuple[str, str]],
) -> None:
    records: list[dict[str, object]] = [
        {
            "timestamp": "2026-08-15T00:00:00.000Z",
            "type": "session_meta",
            "payload": {"id": session_id, "originator": "codex_cli_rs", "cwd": "/tmp"},
        },
        {
            "timestamp": "2026-08-15T00:00:01.000Z",
            "type": "turn_context",
            "payload": {"turn_id": "turn-1", "model": "gpt"},
        },
    ]
    for index, (role, text) in enumerate(messages, start=2):
        records.append(
            {
                "timestamp": f"2026-08-15T00:00:{index:02d}.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "id": f"message-{index}",
                    "role": role,
                    "content": [
                        {
                            "type": "output_text"
                            if role == "assistant"
                            else "input_text",
                            "text": text,
                        }
                    ],
                },
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def test_chatlas2_cli_normalizes_every_archived_codex_transcript(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    first_home = tmp_path / "codex-first"
    second_home = tmp_path / "codex-second"
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675c22"
    relative = Path("sessions/2026/08/15") / f"rollout-{session_id}.jsonl"
    _write_codex_rollout(
        first_home / relative,
        session_id=session_id,
        messages=[("user", "first question"), ("assistant", "first answer")],
    )
    _write_codex_rollout(
        second_home / relative,
        session_id=session_id,
        messages=[
            ("user", "first question"),
            ("assistant", "first answer"),
            ("user", "second question"),
            ("assistant", "second answer"),
        ],
    )
    environment.write_global_config(
        chatlas={
            "sources": [
                {"provider": "codex", "home": str(first_home)},
                {"provider": "codex", "home": str(second_home)},
            ]
        }
    )
    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()

    assert main(["chatlas2", "normalize", "--session-id", session_id, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["class"] == "tarav.chatlas2.normal_model"
    assert payload["session"]["session_id"] == session_id
    assert len(payload["sources"]) == 2
    assert len(payload["events"]) == 6
    assert len(payload["annotations"]["chat_messages"]) == 4
    assert payload["metadata"]["commit"]
