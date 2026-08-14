from __future__ import annotations

import time
from pathlib import Path

import pytest

from tarav.testing import TaravTestEnvironment
from tarav.cli.cli import main
from ._helpers import captured_json, write_chatlas_codex_source
from .test_recent_window_update import _write_codex_session

SESSION_ID = "019ccafa-cccc-7000-aaaa-00000000000c"


def _isolate_one_fresh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    codex_home = tmp_path / "codex-home"
    _write_codex_session(codex_home, session_id=SESSION_ID, timestamp=time.time(), text="recents update turn")
    write_chatlas_codex_source(environment, codex_home)


def test_recents_without_update_misses_uningested_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate_one_fresh(monkeypatch, tmp_path)

    assert main(["chatlas", "recents", "--provider", "codex", "--json"]) == 0
    payload = captured_json(capsys)
    assert payload["entry_count"] == 0


def test_recents_with_update_freshens_and_returns_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate_one_fresh(monkeypatch, tmp_path)

    assert main(["chatlas", "recents", "--provider", "codex", "--json", "--update"]) == 0
    payload = captured_json(capsys)
    assert payload["entry_count"] == 1
    assert payload["entries"][0]["session_id"] == SESSION_ID
