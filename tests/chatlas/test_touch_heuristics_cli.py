# $kw: --from Chatlas.Session.Model.Tests --from Chatlas.Query.Surface --from Chat.Touched.Index
from __future__ import annotations

from pathlib import Path

import pytest

from tarav.cli.cli import main

from ._e2e_helpers import (
    _configure_chatlas,
    _index_rows,
    _isolate_chatlas,
    _write_codex_rollout,
)
from ._helpers import captured_json


def _quote_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[str, dict[str, object]]:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fb2"
    assistant_text = (
        "A quoted assistant passage carries enough distinctive material to establish "
        "touch evidence."
    )
    _write_codex_rollout(
        codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-{session_id}.jsonl",
        session_id=session_id,
        messages=[
            ("assistant", assistant_text),
            ("user", f"You wrote:\n> {assistant_text}\nThat matters."),
        ],
    )
    _configure_chatlas(environment, codex_home)
    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()
    row = _index_rows(environment.home / "Documents" / "chatlas")[0]
    return session_id, row


def test_quotes_cli_resolves_session_id_uri_and_identity_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id, row = _quote_fixture(tmp_path, monkeypatch, capsys)
    selectors = [session_id, str(row["uri"]), str(row["identity_hash"])[:16]]

    for selector in selectors:
        assert (
            main(
                [
                    "chatlas",
                    "touch-heuristics",
                    "quotes",
                    "--session",
                    selector,
                    "--json",
                ]
            )
            == 0
        )
        payload = captured_json(capsys)
        assert payload["command"] == "chatlas touch-heuristics quotes"
        assert payload["session"] == {
            "identity_hash": row["identity_hash"],
            "session_id": session_id,
            "uri": row["uri"],
        }
        assert payload["parameters"] == {
            "lookback": 5,
            "min_length": 40,
            "threshold": 0.75,
        }
        assert payload["finding_count"] == 1
        assert payload["findings"][0]["match_kind"] == "exact"


def test_quotes_cli_rejects_an_out_of_range_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id, _row = _quote_fixture(tmp_path, monkeypatch, capsys)

    assert (
        main(
            [
                "chatlas",
                "touch-heuristics",
                "quotes",
                "--session",
                session_id,
                "--threshold",
                "1.1",
                "--json",
            ]
        )
        == 1
    )
    assert "threshold must be between 0 and 1" in capsys.readouterr().err
