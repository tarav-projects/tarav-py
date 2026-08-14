from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.cli.cli import main
from ._e2e_helpers import (
    _configure_chatlas,
    _isolate_chatlas,
    _inline_selection_events,
    _write_codex_rollout,
)


def _file_touch_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, str]:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    sessions = {
        "writer": "019ccafa-7835-7fc3-ac17-0e0a0f675001",
        "reader": "019ccafa-7835-7fc3-ac17-0e0a0f675002",
        "mentioner": "019ccafa-7835-7fc3-ac17-0e0a0f675003",
    }
    _write_codex_rollout(
        codex_home
        / "sessions"
        / "2026"
        / "03"
        / "08"
        / f"rollout-{sessions['writer']}.jsonl",
        session_id=sessions["writer"],
        tool_calls=[("Write", {"file_path": "/repo/src/alpha.py", "content": "x"})],
    )
    _write_codex_rollout(
        codex_home
        / "sessions"
        / "2026"
        / "03"
        / "08"
        / f"rollout-{sessions['reader']}.jsonl",
        session_id=sessions["reader"],
        tool_calls=[("Read", {"file_path": "/repo/src/alpha.py"})],
    )
    _write_codex_rollout(
        codex_home
        / "sessions"
        / "2026"
        / "03"
        / "08"
        / f"rollout-{sessions['mentioner']}.jsonl",
        session_id=sessions["mentioner"],
        messages=[
            ("user", "please look at /repo/src/alpha.py later"),
            ("assistant", "noted"),
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
    return sessions


def _query_session_ids(
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> set[str]:
    assert main(argv) == 0
    return set(capsys.readouterr().out.strip().splitlines()) - {""}


def test_chatlas_query_file_write_matches_writer_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sessions = _file_touch_fixture(tmp_path, monkeypatch, capsys)
    matched = _query_session_ids(
        capsys,
        ["chatlas", "query", "--file-write", "alpha.py", "--field", "session_id"],
    )
    assert matched == {sessions["writer"]}


def test_chatlas_query_file_read_matches_reader_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sessions = _file_touch_fixture(tmp_path, monkeypatch, capsys)
    matched = _query_session_ids(
        capsys, ["chatlas", "query", "--file-read", "alpha.py", "--field", "session_id"]
    )
    assert matched == {sessions["reader"]}


def test_chatlas_query_file_touched_matches_both_never_mentioner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sessions = _file_touch_fixture(tmp_path, monkeypatch, capsys)
    matched = _query_session_ids(
        capsys,
        ["chatlas", "query", "--file-touched", "alpha.py", "--field", "session_id"],
    )
    assert matched == {sessions["writer"], sessions["reader"]}


def test_chatlas_query_file_touched_no_match_is_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _file_touch_fixture(tmp_path, monkeypatch, capsys)
    matched = _query_session_ids(
        capsys,
        [
            "chatlas",
            "query",
            "--file-touched",
            "does-not-exist.py",
            "--field",
            "session_id",
        ],
    )
    assert matched == set()


def test_chatlas_views_inline_file_write_selects_touching_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sessions = _file_touch_fixture(tmp_path, monkeypatch, capsys)
    events = _inline_selection_events(
        capsys,
        [
            "chatlas",
            "views",
            "get",
            "--session-id",
            sessions["writer"],
            "--file-write",
            "alpha.py",
            "--filter",
            "slim",
        ],
    )
    assert events
    assert all(
        "alpha" in json.dumps(event) or event["kind"] != "message" for event in events
    )
    sequences = {event["sequence"] for event in events}
    assert len(sequences) == len(events) <= 2


def test_chatlas_views_inline_file_touch_no_match_is_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sessions = _file_touch_fixture(tmp_path, monkeypatch, capsys)
    events = _inline_selection_events(
        capsys,
        [
            "chatlas",
            "views",
            "get",
            "--session-id",
            sessions["mentioner"],
            "--file-touched",
            "alpha.py",
        ],
    )
    assert events == []


def test_chatlas_query_tool_contains_catches_bash_touches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    bash_writer = "019ccafa-7835-7fc3-ac17-0e0a0f675011"
    bystander = "019ccafa-7835-7fc3-ac17-0e0a0f675012"
    _write_codex_rollout(
        codex_home / "sessions" / "2026" / "03" / "08" / f"rollout-{bash_writer}.jsonl",
        session_id=bash_writer,
        tool_calls=[
            (
                "Bash",
                {
                    "command": "python3 - <<'EOF'\nopen('/repo/src/beta.py','w').write('x')\nEOF"
                },
            )
        ],
    )
    _write_codex_rollout(
        codex_home / "sessions" / "2026" / "03" / "08" / f"rollout-{bystander}.jsonl",
        session_id=bystander,
        messages=[("user", "unrelated"), ("assistant", "ok")],
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

    matched = _query_session_ids(
        capsys,
        ["chatlas", "query", "--tool-contains", "beta.py", "--field", "session_id"],
    )
    assert matched == {bash_writer}

    # the semantic filter stays honest: Bash is not an explicit-path tool
    matched = _query_session_ids(
        capsys, ["chatlas", "query", "--file-write", "beta.py", "--field", "session_id"]
    )
    assert matched == set()

    # tool-name narrows the recall filter
    matched = _query_session_ids(
        capsys,
        [
            "chatlas",
            "query",
            "--tool-name",
            "Bash",
            "--tool-contains",
            "beta.py",
            "--field",
            "session_id",
        ],
    )
    assert matched == {bash_writer}
    matched = _query_session_ids(
        capsys,
        [
            "chatlas",
            "query",
            "--tool-name",
            "Write",
            "--tool-contains",
            "beta.py",
            "--field",
            "session_id",
        ],
    )
    assert matched == set()


def test_chatlas_views_inline_tool_contains_selects_invocation_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sessions = _file_touch_fixture(tmp_path, monkeypatch, capsys)
    events = _inline_selection_events(
        capsys,
        [
            "chatlas",
            "views",
            "get",
            "--session-id",
            sessions["writer"],
            "--tool-contains",
            "alpha.py",
        ],
    )
    assert events
    assert {event["sequence"] for event in events} <= {5, 6}
