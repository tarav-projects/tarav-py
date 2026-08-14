# $kw: ^test-e2e-bloberia --from Agentos.Bloberia --note [DF] end-to-end coverage for the thin tarav bloberia command consumer ^c20260724-31u
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.cli.cli import build_parser, main


def _captured_json(capsys: object) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]


def test_bloberia_create_get_edit_query_and_check_round_trip(
    tmp_path: Path, capsys: object
) -> None:
    depot = tmp_path / "bloberia"
    value_file = tmp_path / "value.json"
    value_file.write_text('{"kind":"edition","version":2}\n', encoding="utf-8")
    assert "bloberia" in build_parser().format_help()

    assert (
        main(
            [
                "bloberia",
                "create",
                "--depot",
                str(depot),
                "--value-json",
                '{"kind":"edition","version":1}',
            ]
        )
        == 0
    )
    created_payload = _captured_json(capsys)
    created = created_payload["record"]
    assert isinstance(created, dict)
    record_id = created["_bloberia"]["id"]  # type: ignore[index]

    assert main(["bloberia", "get", "--depot", str(depot), "--id", record_id]) == 0
    assert _captured_json(capsys)["record"] == created

    assert (
        main(
            [
                "bloberia",
                "edit",
                "--depot",
                str(depot),
                "--id",
                record_id,
                "--value-file",
                str(value_file),
            ]
        )
        == 0
    )
    edited = _captured_json(capsys)["record"]
    assert edited["value"] == {"kind": "edition", "version": 2}  # type: ignore[index]
    assert edited["_bloberia"]["revision"] == 2  # type: ignore[index]

    assert (
        main(
            [
                "bloberia",
                "query",
                "--depot",
                str(depot),
                "--query-json",
                '{"value":{"kind":"edition"}}',
            ]
        )
        == 0
    )
    query = _captured_json(capsys)
    assert query["count"] == 1
    assert query["records"] == [edited]

    assert main(["bloberia", "query", "--depot", str(depot)]) == 0
    assert _captured_json(capsys)["count"] == 1

    assert main(["bloberia", "check", "--depot", str(depot)]) == 0
    payload = _captured_json(capsys)
    assert payload["domain"]["status"] == "ok"
    assert payload["pois"] == []


def test_bloberia_cli_requires_explicit_depot_and_reports_missing_record(
    tmp_path: Path, capsys: object
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["bloberia", "query"])
    assert exc_info.value.code == 2
    assert "--depot" in capsys.readouterr().err  # type: ignore[attr-defined]

    assert (
        main(
            [
                "bloberia",
                "get",
                "--depot",
                str(tmp_path / "bloberia"),
                "--id",
                "a8dcf050-086a-4fb6-8bd4-a24167c94584",
            ]
        )
        == 1
    )
    assert "record does not exist" in capsys.readouterr().err  # type: ignore[attr-defined]


def test_bloberia_cli_accepts_scalar_json_values(
    tmp_path: Path, capsys: object
) -> None:
    depot = tmp_path / "bloberia"

    assert (
        main(
            [
                "bloberia",
                "create",
                "--depot",
                str(depot),
                "--value-json",
                "null",
            ]
        )
        == 0
    )
    assert _captured_json(capsys)["record"]["value"] is None  # type: ignore[index]


def test_bloberia_check_returns_nonzero_for_corrupt_depot(
    tmp_path: Path, capsys: object
) -> None:
    depot = tmp_path / "bloberia"
    records = depot / "records"
    records.mkdir(parents=True)
    (records / "not-a-uuid.json").write_text("{}\n", encoding="utf-8")

    assert main(["bloberia", "check", "--depot", str(depot)]) == 1
    payload = _captured_json(capsys)
    assert payload["domain"]["status"] == "error"
    assert payload["pois"][0]["class"]["address"] == (  # type: ignore[index]
        "Bloberia.Linter/Record.Filename.Invalid"
    )
