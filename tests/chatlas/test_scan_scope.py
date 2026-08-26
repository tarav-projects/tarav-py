from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import time
from pathlib import Path

import pytest

from tarav.testing import TaravTestEnvironment
from tarav.cli.cli import main
from ._helpers import (
    captured_json,
    read_json_file,
    write_chatlas_codex_source,
    write_text_file,
)

ALPHA_ID = "019ccafb-1111-7000-aaaa-000000000001"
BETA_ID = "019ccafb-2222-7000-aaaa-000000000002"


def _write_codex_session(
    codex_home: Path,
    *,
    session_id: str,
    timestamp: float,
    text: str,
    in_index: bool = True,
) -> Path:
    timestamp_text = (
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    rollout = (
        codex_home
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-{session_id}.jsonl"
    )
    events = [
        {
            "timestamp": timestamp_text,
            "type": "session_meta",
            "payload": {"id": session_id, "originator": "codex_cli_rs", "cwd": "/tmp"},
        },
        {
            "timestamp": timestamp_text,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        },
    ]
    write_text_file(
        rollout,
        "\n".join(json.dumps(event) for event in events) + "\n",
    )
    os.utime(rollout, (timestamp, timestamp))
    if in_index:
        index_path = codex_home / "session_index.jsonl"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        with index_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "id": session_id,
                        "thread_name": text,
                        "updated_at": timestamp_text,
                    }
                )
                + "\n"
            )
    return rollout


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    environment = TaravTestEnvironment.create(tmp_path)
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

    assert main(["chatlas", "update", "--provider", "codex"]) == 0
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
    assert main(["chatlas", "update", "--provider", "codex"]) == 0
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
        "chatlas", "update", "--provider", "codex", "--session-id", ALPHA_ID,
    ]) == 0
    capsys.readouterr()

    assert main(["chatlas", "update", "--provider", "codex"]) == 0
    payload = captured_json(capsys)
    assert payload["native_scan"]["changed_session_count"] == 0
    assert payload["cache"]["hit_count"] == 2
