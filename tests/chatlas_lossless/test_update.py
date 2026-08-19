from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from tarav._core.errors import CliError
from tarav.cli.cli import main
from tarav.testing import TaravTestEnvironment


def _args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "session_id": None,
        "identity_hash": None,
        "providers": None,
        "chatlas_root": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _write_fresh_codex_session(
    codex_home: Path,
    *,
    session_id: str,
    message: str,
) -> None:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
    rollout = (
        codex_home
        / "sessions"
        / "2026"
        / "08"
        / "16"
        / f"rollout-{session_id}.jsonl"
    )
    rollout.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "timestamp": timestamp,
            "type": "session_meta",
            "payload": {"id": session_id, "originator": "codex_cli_rs", "cwd": "/tmp"},
        },
        {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": message}],
            },
        },
    ]
    rollout.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    session_index = codex_home / "session_index.jsonl"
    session_index.write_text(
        json.dumps(
            {"id": session_id, "thread_name": message, "updated_at": timestamp}
        )
        + "\n",
        encoding="utf-8",
    )


def test_update_scope_uses_exact_native_session_and_selected_provider(
    tmp_path: Path,
) -> None:
    from tarav.chatlas.lossless.update import lossless_update_scope

    scope = lossless_update_scope(
        _args(
            session_id="session-one",
            providers=["codex"],
            chatlas_root=str(tmp_path),
        )
    )

    assert scope.providers == ("codex",)
    assert scope.session_ids == ("session-one",)
    assert scope.chatlas_root == tmp_path


def test_update_scope_resolves_known_identity_to_native_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tarav.chatlas.lossless import update

    monkeypatch.setattr(
        update,
        "select_one_chatlas_index_row",
        lambda **_kwargs: {
            "provider": "claude-code",
            "session_id": "session-two",
        },
    )

    scope = update.lossless_update_scope(_args(identity_hash="abc123"))

    assert scope.providers == ("claude-code",)
    assert scope.session_ids == ("session-two",)


def test_update_scope_unknown_identity_falls_back_to_supported_provider_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tarav.chatlas.lossless import update

    def missing(**_kwargs: object) -> dict[str, object]:
        raise CliError("not indexed")

    monkeypatch.setattr(update, "select_one_chatlas_index_row", missing)

    scope = update.lossless_update_scope(_args(identity_hash="unknown"))

    assert scope.providers == ("codex", "claude-code")
    assert scope.session_ids == ()


def test_update_runs_the_shared_delta_pipeline_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from tarav.chatlas.lossless import update

    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        update,
        "chatlas_update",
        lambda **kwargs: calls.append(kwargs) or {"status": "ok"},
    )
    def progress(_message: str) -> None:
        return None

    scope = update.LosslessUpdateScope(
        providers=("codex",),
        session_ids=("session-one",),
        chatlas_root=tmp_path,
    )

    result = update.update_lossless(scope, progress=progress)

    assert result == {"status": "ok"}
    assert calls == [
        {
            "providers": ("codex",),
            "session_ids": ("session-one",),
            "chatlas_root": tmp_path,
            "progress": progress,
        }
    ]


def test_cli_update_precedes_leaf_command_and_preserves_json_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tarav.chatlas.lossless import commands, update

    events: list[str] = []

    def run_update(_scope: update.LosslessUpdateScope, **_kwargs: object) -> dict[str, object]:
        events.append("update")
        return {"status": "ok"}

    def query(**_kwargs: object) -> dict[str, object]:
        events.append("query")
        return {"class": "tarav.chatlas2.session-query", "sessions": []}

    monkeypatch.setattr(commands, "update_lossless", run_update)
    monkeypatch.setattr(commands, "query_sessions", query)

    assert (
        main(
            [
                "chatlas",
                "--update",
                "sessions",
                "query",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert events == ["update", "query"]
    assert json.loads(captured.out) == {
        "class": "tarav.chatlas2.session-query",
        "sessions": [],
    }
    assert "session-query" not in captured.err


def test_cli_update_failure_prevents_leaf_command(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tarav.chatlas.lossless import commands

    queried = False

    def fail_update(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise CliError("provider unavailable")

    def query(**_kwargs: object) -> dict[str, object]:
        nonlocal queried
        queried = True
        return {"sessions": []}

    monkeypatch.setattr(commands, "update_lossless", fail_update)
    monkeypatch.setattr(commands, "query_sessions", query)

    assert main(["chatlas", "--update", "sessions", "query"]) == 1

    captured = capsys.readouterr()
    assert queried is False
    assert captured.out == ""
    assert "provider unavailable" in captured.err


def test_cli_update_ingests_fresh_session_before_chat_query(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    codex_home = tmp_path / "codex-home"
    session_id = "019ccafa-dddd-7000-aaaa-00000000000d"
    message = "chatlas2 fresh update message"
    _write_fresh_codex_session(
        codex_home,
        session_id=session_id,
        message=message,
    )
    environment.write_global_config(
        chatlas={"sources": [{"provider": "codex", "home": str(codex_home)}]}
    )
    query = [
        "chatlas",
        "chat",
        "query",
        "--provider",
        "codex",
        "--contains",
        message,
        "--json",
    ]

    assert main(query) == 0
    stale = json.loads(capsys.readouterr().out)
    assert stale["returned_message_count"] == 0

    assert main(["chatlas", "--update", *query[1:]]) == 0
    fresh = json.loads(capsys.readouterr().out)
    assert fresh["returned_message_count"] == 1
    assert fresh["messages"][0]["session"]["session_id"] == session_id
    assert fresh["messages"][0]["message"]["text"] == message
