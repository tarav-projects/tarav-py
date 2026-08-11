from __future__ import annotations

from pathlib import Path

import pytest

from agentos.cli.cli import main
from agentos.chatlas.chat_index import chat_index_source_model
from agentos.chatlas.recents import chatlas_recents, format_chatlas_recents_text

from ._e2e_helpers import (
    _configure_chatlas,
    _index_rows,
    _isolate_chatlas,
    _write_codex_rollout,
)
from ._helpers import captured_json


SESSION_ID = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"


def _setup_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[Path, Path, dict[str, object]]:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    rollout = (
        codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-{SESSION_ID}.jsonl"
    )
    _write_codex_rollout(
        rollout,
        session_id=SESSION_ID,
        messages=[("user", "first"), ("assistant", "answer")],
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
    chatlas_root = environment.home / "Documents" / "chatlas"
    row = _index_rows(chatlas_root)[0]
    return chatlas_root, rollout, row


def _materialize_chat_index(
    chatlas_root: Path,
    row: dict[str, object],
    *,
    through: int = -1,
) -> Path:
    """Write a real derived surface: one Delta per user turn, plus HEAD."""
    _canonical, source = chat_index_source_model(row, chatlas_root=chatlas_root)
    turns = source["turn_refs"][: None if through < 0 else through]
    surface = chatlas_root / "session-index" / str(row["identity_hash"])
    (surface / "deltas").mkdir(parents=True, exist_ok=True)
    for entry in turns:
        turn_id = entry["turn_ref"]["turn_id"]
        (surface / "deltas" / f"{turn_id}.md").write_text(
            f"# Chat.Index.Delta/{turn_id}\n", encoding="utf-8"
        )
    horizon = turns[-1]["turn_ref"]["turn_id"]
    (surface / "HEAD.md").write_text(
        f"# Chat.Index.HEAD\n\nEvidence.Horizon: `{horizon}`\n", encoding="utf-8"
    )
    return surface


def _surface_snapshot(surface: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(surface)): path.read_bytes()
        for path in sorted(surface.rglob("*"))
        if path.is_file()
    }


def test_chat_index_cli_discovers_current_then_retains_stale_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, rollout, row = _setup_session(tmp_path, monkeypatch, capsys)
    selector = ["--session-id", SESSION_ID]
    expected_surface = chatlas_root / "session-index" / str(row["identity_hash"])

    assert main(["chatlas", "chat-index", "status", *selector, "--json"]) == 0
    missing = captured_json(capsys)["chat_index"]
    assert missing["state"] == "missing"
    assert missing["path"] == str(expected_surface)
    assert not expected_surface.exists()

    surface = _materialize_chat_index(chatlas_root, row)
    before = _surface_snapshot(surface)

    assert main(["chatlas", "chat-index", "status", *selector, "--json"]) == 0
    current = captured_json(capsys)["chat_index"]
    assert current["state"] == "materialized"
    assert current["freshness"]["state"] == "current"

    assert main(["chatlas", "chat-index", "show", *selector, "--json"]) == 0
    shown = captured_json(capsys)
    assert shown["capture"]["head"]["path"] == "HEAD.md"
    assert shown["chat_index"]["layout"] == "delta-head-v2"

    assert main(["chatlas", "chat-index", "tail", *selector, "--json"]) == 0
    assert captured_json(capsys)["tail"]["state"] == "current"

    assert main(["chatlas", "chat-index", "path", *selector]) == 0
    assert capsys.readouterr().out.strip() == str(surface)

    assert main(["chatlas", "chat-index", "files", *selector, "--json"]) == 0
    files = captured_json(capsys)["files"]
    assert [item["relative_path"] for item in files] == [
        "HEAD.md",
        *sorted(
            f"deltas/{path.name}" for path in (surface / "deltas").glob("*.md")
        ),
    ]
    assert all(item["exists"] is True for item in files)

    assert main(["chatlas", "query", *selector, "--json"]) == 0
    query_row = captured_json(capsys)["rows"][0]
    assert query_row["chat_index"] == {
        "materialized": True,
        "state": "materialized",
        "path": str(surface),
    }

    recents = chatlas_recents(
        since_date="2026-03-01",
        session_id=SESSION_ID,
        chatlas_root=chatlas_root,
    )
    assert recents["entries"][0]["chat_index"]["path"] == str(surface)
    assert f"index at: {surface}" in format_chatlas_recents_text(recents)

    _write_codex_rollout(
        rollout,
        session_id=SESSION_ID,
        messages=[
            ("user", "first"),
            ("assistant", "answer"),
            ("user", "second"),
        ],
    )
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

    assert main(["chatlas", "chat-index", "status", *selector, "--json"]) == 0
    stale = captured_json(capsys)["chat_index"]
    assert stale["state"] == "materialized"
    assert stale["freshness"]["state"] == "stale"
    assert "past the declared horizon" in stale["warning"]
    assert _surface_snapshot(surface) == before

    assert (
        main(
            [
                "chatlas",
                "gc",
                "--provider",
                "codex",
                "--session-id",
                SESSION_ID,
                "--apply",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert _surface_snapshot(surface) == before

    assert (
        main(["chatlas", "index", "reset", "--json"])
        == 0
    )
    capsys.readouterr()
    assert _surface_snapshot(surface) == before


def test_chat_index_unreadable_surface_is_reported_not_repaired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, _rollout, row = _setup_session(tmp_path, monkeypatch, capsys)
    selector = ["--session-id", SESSION_ID]
    surface = chatlas_root / "session-index" / str(row["identity_hash"])
    surface.mkdir(parents=True)
    stray = surface / "notes.md"
    stray.write_text("not a Chat.Index\n", encoding="utf-8")

    stray_bytes = stray.read_bytes()
    assert main(["chatlas", "chat-index", "status", *selector, "--json"]) == 0
    unmaterialized = captured_json(capsys)["chat_index"]
    assert unmaterialized["state"] == "invalid"
    assert "is not materialized" in unmaterialized["warning"]
    assert stray.read_bytes() == stray_bytes

    _materialize_chat_index(chatlas_root, row)
    delta = next((surface / "deltas").glob("*.md"))
    delta.write_text("# Chat.Index.Delta/turn-elsewhere\n", encoding="utf-8")
    disagreeing_bytes = delta.read_bytes()

    assert main(["chatlas", "chat-index", "files", *selector, "--json"]) == 0
    disagreeing = captured_json(capsys)
    assert disagreeing["chat_index"]["state"] == "invalid"
    assert "disagrees with its filename" in disagreeing["chat_index"]["warning"]
    assert disagreeing["files"] == []
    assert delta.read_bytes() == disagreeing_bytes
