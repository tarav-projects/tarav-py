# $kw: ^test-e2e-bloberia --from Agentos.Bloberia --note [DF] end-to-end coverage for the thin tarav bloberia command consumer ^c20260724-31u
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.cli.cli import build_parser, main


def _captured_json(capsys: object) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]


def test_bloberia_insert_first_replace_all_and_check_round_trip(
    tmp_path: Path, capsys: object
) -> None:
    depot = tmp_path / "bloberia"
    cargo_file = tmp_path / "cargo.json"
    cargo_file.write_text('{"id":"e-1","kind":"edition","version":2}\n', encoding="utf-8")
    assert "bloberia" in build_parser().format_help()

    assert (
        main(
            [
                "bloberia",
                "insert",
                "--depot",
                str(depot),
                "--cargo-json",
                '{"id":"e-1","kind":"edition","version":1}',
            ]
        )
        == 0
    )
    assert _captured_json(capsys)["inserted"] == 1

    by_id = '{"id":{"equals":"e-1"}}'
    assert main(["bloberia", "first", "--depot", str(depot), "--query-json", by_id]) == 0
    found = _captured_json(capsys)
    assert found["found"] is True
    assert found["record"] == {"id": "e-1", "kind": "edition", "version": 1}

    assert (
        main(
            [
                "bloberia",
                "replace",
                "--depot",
                str(depot),
                "--query-json",
                by_id,
                "--cargo-file",
                str(cargo_file),
            ]
        )
        == 0
    )
    assert _captured_json(capsys)["replaced"] == 1

    assert (
        main(
            [
                "bloberia",
                "all",
                "--depot",
                str(depot),
                "--query-json",
                '{"kind":{"equals":"edition"}}',
            ]
        )
        == 0
    )
    query = _captured_json(capsys)
    assert query["count"] == 1
    assert query["records"] == [{"id": "e-1", "kind": "edition", "version": 2}]

    assert main(["bloberia", "all", "--depot", str(depot)]) == 0
    assert _captured_json(capsys)["count"] == 1

    assert main(["bloberia", "delete", "--depot", str(depot), "--query-json", by_id]) == 0
    assert _captured_json(capsys)["deleted"] == 1

    assert main(["bloberia", "check", "--depot", str(depot)]) == 0
    payload = _captured_json(capsys)
    assert payload["domain"]["status"] == "ok"
    assert payload["pois"] == []


def test_bloberia_cli_requires_an_explicit_depot(
    tmp_path: Path, capsys: object
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["bloberia", "all"])
    assert exc_info.value.code == 2
    assert "--depot" in capsys.readouterr().err  # type: ignore[attr-defined]


def test_a_query_matching_nothing_is_an_answer_rather_than_an_error(
    tmp_path: Path, capsys: object
) -> None:
    """There is no id to be missing. Absence is reported, not raised.

    The retired `get --id` had a distinct not-found failure because the store owned the
    identity it was given. A query that matches no record is an ordinary result.
    """
    assert (
        main(
            [
                "bloberia",
                "first",
                "--depot",
                str(tmp_path / "bloberia"),
                "--query-json",
                '{"id":{"equals":"absent"}}',
            ]
        )
        == 0
    )
    payload = _captured_json(capsys)
    assert payload["found"] is False
    assert payload["record"] is None


def test_bloberia_cli_accepts_scalar_json_cargo(
    tmp_path: Path, capsys: object
) -> None:
    depot = tmp_path / "bloberia"
    assert (
        main(["bloberia", "insert", "--depot", str(depot), "--cargo-json", "null"]) == 0
    )
    _captured_json(capsys)
    assert main(["bloberia", "all", "--depot", str(depot)]) == 0
    assert _captured_json(capsys)["records"] == [None]


def test_bloberia_check_returns_nonzero_for_an_unparseable_record(
    tmp_path: Path, capsys: object
) -> None:
    depot = tmp_path / "bloberia"
    records = depot / "records"
    records.mkdir(parents=True)
    (records / "unparseable.json").write_text("{not json", encoding="utf-8")

    assert main(["bloberia", "check", "--depot", str(depot)]) == 1
    payload = _captured_json(capsys)
    assert payload["domain"]["status"] == "error"
    assert payload["pois"][0]["class"]["address"] == (  # type: ignore[index]
        "Bloberia.Linter/Json.Invalid"
    )
