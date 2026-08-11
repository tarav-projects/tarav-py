from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.anchory import AnchoryDepot
import agentos.chatlas.anchory as chatlas_anchory
from agentos.cli.cli import build_parser, main


def _captured_json(capsys: object) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]


def test_anchory_register_resolve_query_and_amend_round_trip(
    tmp_path: Path,
    capsys: object,
) -> None:
    depot = tmp_path / "anchory"
    assert "anchory" in build_parser().format_help()

    assert (
        main(
            [
                "anchory",
                "register",
                "--depot",
                str(depot),
                "--anchor",
                "20260706-0",
                "--record-json",
                '{"session_id":"session-1"}',
            ]
        )
        == 0
    )
    assert _captured_json(capsys)["record"] == {"session_id": "session-1"}

    assert (
        main(["anchory", "resolve", "--depot", str(depot), "--anchor", "20260706-0"])
        == 0
    )
    assert _captured_json(capsys)["anchor"] == "20260706-0"

    assert main(["anchory", "query", "--depot", str(depot), "--prefix", "2026"]) == 0
    query = _captured_json(capsys)
    assert query["count"] == 1

    assert (
        main(
            [
                "anchory",
                "amend",
                "--depot",
                str(depot),
                "--anchor",
                "20260706-0",
                "--record-json",
                '{"session_id":"session-2"}',
            ]
        )
        == 0
    )
    assert _captured_json(capsys)["record"] == {"session_id": "session-2"}

    assert main(["anchory", "check", "--depot", str(depot)]) == 0
    payload = _captured_json(capsys)
    assert payload["domain"]["status"] == "ok"
    assert payload["pois"] == []


def test_anchory_cli_reports_identity_errors_and_accepts_record_file(
    tmp_path: Path,
    capsys: object,
) -> None:
    depot = tmp_path / "anchory"
    record_file = tmp_path / "record.json"
    record_file.write_text('{"session_id":"session-1"}\n', encoding="utf-8")
    register_args = [
        "anchory",
        "register",
        "--depot",
        str(depot),
        "--anchor",
        "stable",
        "--record-file",
        str(record_file),
    ]

    assert main(register_args) == 0
    _captured_json(capsys)
    assert main(register_args) == 1
    assert "anchor already exists" in capsys.readouterr().err  # type: ignore[attr-defined]

    assert (
        main(["anchory", "resolve", "--depot", str(depot), "--anchor", "missing"]) == 1
    )
    assert "anchor does not exist" in capsys.readouterr().err  # type: ignore[attr-defined]


def test_anchory_amend_rejects_invalid_chatlas_replacement_without_mutation(
    tmp_path: Path,
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agentos.chatlas.normalization.session_model.events import (
        compute_event_group_hash,
        compute_event_hash,
    )

    depot_root = tmp_path / "chatlas" / "anchory"
    depot = AnchoryDepot(depot_root)
    fixture_event = {
        "event_address": "a" * 64,
        "annotations": {"normal_turn": {"id": "turn-1", "kind": "user"}},
        "sequence": 1,
        "kind": "message",
        "timestamp": "2026-07-18T08:51:01.000Z",
        "producer": {"type": "human"},
        "surfaces": {"transcript": "visible"},
        "payload": {"role": "user", "content": []},
    }
    fixture_event["event_hash"] = compute_event_hash(fixture_event)
    current = {
        "app": "chatlas",
        "schema": "chatlas.support-set.v3",
        "hint": "original hint",
        "members": [
            {
                "session": "a" * 64,
                "turn_id": "turn-1",
                "turn_hash": compute_event_group_hash([fixture_event]),
                "at": "2026-07-18T08:51:01.000Z",
            }
        ],
    }
    depot.register(current, anchor="c20260718-0u", namespace="chatlas")
    proposed = {
        **current,
        "hint": "corrected hint",
        "members": [
            {
                "session": "a" * 64,
                "turn_id": "turn-1",
                    "turn_hash": compute_event_group_hash([fixture_event]),
            }
        ],
    }

    assert (
        main(
            [
                "anchory",
                "amend",
                "--depot",
                str(depot_root),
                "--namespace",
                "chatlas",
                "--anchor",
                "c20260718-0u",
                "--record-json",
                json.dumps(proposed),
            ]
        )
        == 1
    )
    assert "requires non-empty 'at'" in capsys.readouterr().err  # type: ignore[attr-defined]
    assert depot.resolve("c20260718-0u", namespace="chatlas").record == current

    monkeypatch.setattr(
        chatlas_anchory,
        "_load_session_model",
        lambda _identity, *, chatlas_root: {
            "chat": {
                    "events": [fixture_event]
            }
        },
    )
    valid = {**current, "hint": "corrected hint"}
    assert (
        main(
            [
                "anchory",
                "amend",
                "--depot",
                str(depot_root),
                "--namespace",
                "chatlas",
                "--anchor",
                "c20260718-0u",
                "--record-json",
                json.dumps(valid),
            ]
        )
        == 0
    )
    _captured_json(capsys)
    assert (
        AnchoryDepot(depot_root).resolve("c20260718-0u", namespace="chatlas").record
        == valid
    )


def test_anchory_register_prefix_allocates_next_anchor(
    tmp_path: Path,
    capsys: object,
) -> None:
    depot = tmp_path / "anchory"

    assert (
        main(
            [
                "anchory",
                "register",
                "--depot",
                str(depot),
                "--alloc-prefix",
                "20260708",
                "--record-json",
                '{"session_id":"session-1"}',
            ]
        )
        == 0
    )
    assert _captured_json(capsys)["anchor"] == "20260708-0"

    assert (
        main(
            [
                "anchory",
                "register",
                "--depot",
                str(depot),
                "--alloc-prefix",
                "20260708",
                "--record-json",
                '{"session_id":"session-2"}',
            ]
        )
        == 0
    )
    assert _captured_json(capsys)["anchor"] == "20260708-1"


def test_anchory_register_rejects_anchor_and_prefix_together(
    tmp_path: Path,
    capsys: object,
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "anchory",
                "register",
                "--depot",
                str(tmp_path / "anchory"),
                "--anchor",
                "stable",
                "--alloc-prefix",
                "20260708",
                "--record-json",
                '{"session_id":"session-1"}',
            ]
        )
    assert exc_info.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err  # type: ignore[attr-defined]


def test_anchory_check_returns_nonzero_with_structured_findings(
    tmp_path: Path,
    capsys: object,
) -> None:
    depot = tmp_path / "anchory"
    shard = depot / "global" / "00.json"
    shard.parent.mkdir(parents=True)
    shard.write_text("{", encoding="utf-8")

    assert main(["anchory", "check", "--depot", str(depot)]) == 1
    payload = _captured_json(capsys)
    assert payload["domain"]["status"] == "error"
    assert payload["pois"][0]["class"]["address"] == (  # type: ignore[index]
        "Anchory.Linter/Json.Invalid"
    )


def test_anchory_scan_outputs_human_records_by_default(
    tmp_path: Path,
    capsys: object,
) -> None:
    depot = tmp_path / "anchory"
    source = tmp_path / "source.md"
    source.write_text("refs: @alpha @missing @alpha\nnext: @beta\n", encoding="utf-8")
    assert (
        main(
            [
                "anchory",
                "register",
                "--depot",
                str(depot),
                "--anchor",
                "alpha",
                "--record-json",
                '{"value":1}',
            ]
        )
        == 0
    )
    _captured_json(capsys)
    assert (
        main(
            [
                "anchory",
                "register",
                "--depot",
                str(depot),
                "--anchor",
                "beta",
                "--record-json",
                '{"value":2}',
            ]
        )
        == 0
    )
    _captured_json(capsys)

    assert (
        main(
            [
                "anchory",
                "scan",
                "--depot",
                str(depot),
                "--src-file",
                str(source),
                "--regex",
                r"@(?P<anchor>[A-Za-z0-9-]+)",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Anchory scan" in output
    assert "3 match(es)" in output
    assert "alpha @ line 1, column 8" in output
    assert '"value": 1' in output
    assert "missing @ line 1, column 15" in output
    assert "record: missing" in output
    assert "beta @ line 2, column 8" in output


def test_anchory_scan_json_is_deterministic_and_read_only(
    tmp_path: Path,
    capsys: object,
) -> None:
    depot = tmp_path / "anchory"
    source = tmp_path / "source.md"
    source.write_text("refs: [alpha] [missing] [alpha]\n", encoding="utf-8")
    assert (
        main(
            [
                "anchory",
                "register",
                "--depot",
                str(depot),
                "--anchor",
                "alpha",
                "--record-json",
                '{"value":1}',
            ]
        )
        == 0
    )
    _captured_json(capsys)
    before = {
        path: path.read_bytes() for path in sorted(depot.rglob("*")) if path.is_file()
    }

    assert (
        main(
            [
                "anchory",
                "scan",
                "--depot",
                str(depot),
                "--src-file",
                str(source),
                "--regex",
                r"\[([A-Za-z0-9-]+)\]",
                "--json",
            ]
        )
        == 0
    )

    payload = _captured_json(capsys)
    assert payload == {
        "count": 2,
        "depot": str(depot.resolve()),
        "matches": [
            {
                "anchor": "alpha",
                "column": 8,
                "line": 1,
                "record": {"value": 1},
                "start": 7,
                "end": 12,
            },
            {
                "anchor": "missing",
                "column": 16,
                "line": 1,
                "record": None,
                "start": 15,
                "end": 22,
            },
        ],
        "regex": r"\[([A-Za-z0-9-]+)\]",
        "src_file": str(source.resolve()),
    }
    after = {
        path: path.read_bytes() for path in sorted(depot.rglob("*")) if path.is_file()
    }
    assert after == before
