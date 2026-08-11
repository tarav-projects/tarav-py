from __future__ import annotations

import time
from pathlib import Path

import pytest

from agentos.testing import AgentosTestEnvironment
from agentos.cli.cli import main
from ._helpers import captured_json, write_chatlas_codex_source
from .test_recent_window_update import _write_codex_session

ALPHA_ID = "019ccafa-aaaa-7000-aaaa-00000000000a"
BETA_ID = "019ccafa-bbbb-7000-aaaa-00000000000b"


def _isolate_codex_two_fresh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    codex_home = tmp_path / "codex-home"
    now = time.time()
    _write_codex_session(codex_home, session_id=ALPHA_ID, timestamp=now, text="alpha unique turn")
    _write_codex_session(codex_home, session_id=BETA_ID, timestamp=now, text="beta unique turn")
    write_chatlas_codex_source(environment, codex_home)


def _query(capsys: pytest.CaptureFixture[str], argv: list[str]) -> dict:
    assert main([*argv, "--json"]) == 0
    return captured_json(capsys)


def test_query_update_ingests_fresh_match_a_bare_read_misses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate_codex_two_fresh(monkeypatch, tmp_path)

    stale = _query(capsys, ["chatlas", "query", "--provider", "codex", "--user-contains", "alpha unique turn"])
    assert stale["returned_row_count"] == 0

    fresh = _query(
        capsys,
        ["chatlas", "query", "--provider", "codex", "--user-contains", "alpha unique turn", "--update"],
    )
    assert fresh["returned_row_count"] == 1
    assert fresh["rows"][0]["session_id"] == ALPHA_ID


def test_query_update_scope_is_structural_not_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate_codex_two_fresh(monkeypatch, tmp_path)

    # --update filtered by content for one session must still ingest the whole provider scope.
    _query(
        capsys,
        ["chatlas", "query", "--provider", "codex", "--user-contains", "alpha unique turn", "--update"],
    )

    after = _query(capsys, ["chatlas", "query", "--provider", "codex"])
    ids = {row["session_id"] for row in after["rows"]}
    assert ALPHA_ID in ids
    assert BETA_ID in ids


def test_query_update_direct_tier_refreshes_named_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate_codex_two_fresh(monkeypatch, tmp_path)

    result = _query(
        capsys,
        ["chatlas", "query", "--provider", "codex", "--session-id", ALPHA_ID, "--update"],
    )
    assert result["returned_row_count"] == 1
    assert result["rows"][0]["session_id"] == ALPHA_ID
