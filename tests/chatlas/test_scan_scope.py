from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from agentos.testing import AgentosTestEnvironment
from agentos.cli.cli import main
from ._helpers import captured_json, read_json_file, write_chatlas_codex_source
from .test_recent_window_update import _write_codex_session

ALPHA_ID = "019ccafb-1111-7000-aaaa-000000000001"
BETA_ID = "019ccafb-2222-7000-aaaa-000000000002"


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    codex_home = tmp_path / "codex-home"
    now = time.time()
    _write_codex_session(codex_home, session_id=ALPHA_ID, timestamp=now, text="alpha scoped turn")
    _write_codex_session(codex_home, session_id=BETA_ID, timestamp=now, text="beta scoped turn")
    write_chatlas_codex_source(environment, codex_home)
    return codex_home


def _derivation_cache_entries() -> dict[str, dict]:
    cache_root = (
        Path(os.environ["HOME"]) / "Documents" / "chatlas" / "cache" / "session-index-derivations-v2"
    )
    partitions = sorted(cache_root.glob("codex/*/sessions.json"))
    assert len(partitions) == 1, f"expected one codex cache partition, found {partitions}"
    return read_json_file(partitions[0])["sessions"]


def test_session_scoped_update_runs_standard_mechanics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Scan.Scope [CT]: a one-session scope runs the same discover →
    signature-compare → archive → derive stages, including derivation-cache
    maintenance — not a parallel path that skips them."""
    codex_home = _isolate(monkeypatch, tmp_path)

    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()
    entries_before = _derivation_cache_entries()
    assert set(entries_before) == {ALPHA_ID, BETA_ID}

    # advance alpha's raw content; beta stays untouched
    _write_codex_session(
        codex_home, session_id=ALPHA_ID, timestamp=time.time() + 5, text="alpha advanced turn"
    )

    assert main([
        "chatlas", "update",
        "--provider", "codex",
        "--session-id", ALPHA_ID,
        "--json",
    ]) == 0
    payload = captured_json(capsys)

    # standard pipeline counters, scoped to one session
    assert payload["native_scan"]["session_count"] == 1
    assert payload["native_scan"]["changed_session_count"] == 1
    assert payload["session_index"]["upserted_row_count"] >= 1

    # the derivation cache is maintained: alpha's signature advanced,
    # beta's entry survives the narrowed run untouched
    entries_after = _derivation_cache_entries()
    assert set(entries_after) == {ALPHA_ID, BETA_ID}
    assert entries_after[ALPHA_ID] != entries_before[ALPHA_ID]
    assert entries_after[BETA_ID] == entries_before[BETA_ID]


def test_session_scoped_update_agrees_with_following_bulk_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """After a scoped refresh, a bulk run sees the session unchanged —
    scope narrows the candidates, never the mechanics."""
    codex_home = _isolate(monkeypatch, tmp_path)
    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()

    # advance only alpha's rollout; the shared session_index.jsonl stays
    # untouched so beta's sources are genuinely unchanged
    _write_codex_session(
        codex_home,
        session_id=ALPHA_ID,
        timestamp=time.time() + 5,
        text="alpha advanced turn",
        in_index=False,
    )
    assert main([
        "chatlas", "update", "--provider", "codex", "--session-id", ALPHA_ID, "--json",
    ]) == 0
    capsys.readouterr()

    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    payload = captured_json(capsys)
    assert payload["native_scan"]["changed_session_count"] == 0
    assert payload["cache"]["hit_count"] == 2
