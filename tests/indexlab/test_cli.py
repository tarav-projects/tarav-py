from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.cli.cli import main
from tarav.indexlab.commands import CAPTURE_MANIFEST_SCHEMA, TOUCH_MOCK_FILENAME


def _manifest(path) -> None:
    common = {
        "context": {
            "session": "chat-a",
            "horizon": {"address": "turn-a", "hash": "turn-hash-a"},
        },
        "support": {
            "neighborhoods": [
                {
                    "session": "chat-a",
                    "grounding": [
                        {"address": "message-a", "hash": "message-hash-a"}
                    ],
                }
            ]
        },
    }
    path.write_text(
        json.dumps(
            {
                "schema": "tarav.indexlab-capture-manifest.v1",
                "records": [
                    {
                        **common,
                        "id": "record-block",
                        "operation": {
                            "type": "block.create",
                            "parameters": {
                                "block_id": "block-a",
                                "isoblock_id": "isoblock-a",
                                "name": "Recording.Kernel",
                            },
                        },
                    },
                    {
                        **common,
                        "id": "record-line",
                        "operation": {
                            "type": "line.capture",
                            "parameters": {
                                "line_id": "line-a",
                                "isoline_id": "isoline-a",
                                "block_id": "block-a",
                                "label": "^index-sequence",
                                "text": "The index is a sequence of records.",
                            },
                        },
                    },
                ],
            }
        ),
        "utf-8",
    )


def _initialize_library(path, capsys) -> None:
    assert main(["indexlab", "library", "init", "--library", str(path)]) == 0
    capsys.readouterr()


def _create_workspace(
    library, name: str, capsys, *, touch_adapter: str = "chatlas"
) -> dict[str, object]:
    assert (
        main(
            [
                "indexlab",
                "workspace",
                "create",
                "--library",
                str(library),
                "--name",
                name,
                "--touch-adapter",
                touch_adapter,
            ]
        )
        == 0
    )
    return json.loads(capsys.readouterr().out)


def _selection(library, workspace: str) -> list[str]:
    return ["--library", str(library), "--workspace", workspace]


def test_cli_creates_captures_projects_and_exposes_the_bloberia_depot(
    tmp_path, capsys
) -> None:
    library = tmp_path / "library"
    manifest = tmp_path / "capture.json"
    _manifest(manifest)
    _initialize_library(library, capsys)
    created = _create_workspace(library, "main", capsys)
    depot = created["depot"]

    assert created["workspace"] == depot
    assert created["name"] == "main"
    assert (
        main(
            [
                "indexlab",
                "capture",
                *_selection(library, "main"),
                "--manifest",
                str(manifest),
            ]
        )
        == 0
    )
    captured = json.loads(capsys.readouterr().out)
    assert captured["ordinals"] == [1, 2]

    assert main(["indexlab", "records", *_selection(library, "main")]) == 0
    records = json.loads(capsys.readouterr().out)
    assert [record["id"] for record in records["records"]] == [
        "record-block",
        "record-line",
    ]

    assert main(["indexlab", "project", *_selection(library, "main")]) == 0
    projection = json.loads(capsys.readouterr().out)
    assert projection["blocks"][0]["line_ids"] == ["line-a"]

    assert (
        main(
            [
                "bloberia",
                "all",
                "--depot",
                str(depot),
                "--query-json",
                '{"operation.type":{"equals":"block.create"}}',
            ]
        )
        == 0
    )
    generic_query = json.loads(capsys.readouterr().out)
    assert generic_query["count"] == 1
    assert generic_query["records"][0]["id"] == "record-block"


def test_cli_lists_workspaces_and_accepts_stable_uuid_selector(tmp_path, capsys) -> None:
    library = tmp_path / "library"
    _initialize_library(library, capsys)
    created = _create_workspace(library, "main", capsys)
    _create_workspace(library, "scenarios", capsys, touch_adapter="mock")

    assert main(["indexlab", "workspace", "list", "--library", str(library)]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert [item["name"] for item in listing["workspaces"]] == ["main", "scenarios"]

    assert (
        main(
            [
                "indexlab",
                "records",
                *_selection(library, str(created["id"])),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["count"] == 0


def test_cli_refuses_uninitialized_library_and_unknown_workspace(tmp_path, capsys) -> None:
    library = tmp_path / "not-initialized"
    result = main(["indexlab", "records", *_selection(library, "main")])

    assert result == 1
    assert "not an initialized Index.Library" in capsys.readouterr().err

    _initialize_library(library, capsys)
    result = main(["indexlab", "records", *_selection(library, "absent")])
    assert result == 1
    assert "unknown Index.Workspace" in capsys.readouterr().err


def test_mock_scenario_is_deterministic_and_lints_cleanly(tmp_path, capsys) -> None:
    library = tmp_path / "library"
    _initialize_library(library, capsys)
    projections = []
    for name in ("first", "second"):
        _create_workspace(library, name, capsys, touch_adapter="mock")
        assert (
            main(
                [
                    "indexlab",
                    "scenario",
                    "seed-mock",
                    *_selection(library, name),
                ]
            )
            == 0
        )
        scenario = json.loads(capsys.readouterr().out)
        assert scenario["lint"]["verified"] is True
        projections.append(scenario["projection"])

        assert main(["indexlab", "lint", *_selection(library, name)]) == 0
        assert json.loads(capsys.readouterr().out)["verified"] is True

    assert projections[0] == projections[1]


def test_mock_adapter_is_explicit_and_fails_closed_without_its_material(
    tmp_path, capsys
) -> None:
    library = tmp_path / "library"
    _initialize_library(library, capsys)
    _create_workspace(library, "main", capsys)

    result = main(
        ["indexlab", "scenario", "seed-mock", *_selection(library, "main")]
    )
    assert result == 1
    assert "touch_adapter 'mock'" in capsys.readouterr().err

    mock_workspace = _create_workspace(
        library, "mock-without-material", capsys, touch_adapter="mock"
    )
    result = main(
        ["indexlab", "lint", *_selection(library, "mock-without-material")]
    )
    assert result == 1
    assert TOUCH_MOCK_FILENAME in capsys.readouterr().err
    assert mock_workspace["touch_adapter"] == "mock"


def test_indexlab_help_exposes_library_and_workspace_boundaries(capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["indexlab", "--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "experimental" in output.lower()
    assert "library" in output.lower()
    assert "workspace" in output.lower()


def test_lint_exits_nonzero_when_a_check_is_blocked(tmp_path, capsys) -> None:
    """Fail closed: blocked is not a pass, even though nothing failed."""

    library = tmp_path / "library"
    _initialize_library(library, capsys)
    created = _create_workspace(library, "blocked", capsys, touch_adapter="mock")

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": CAPTURE_MANIFEST_SCHEMA,
                "records": [
                    {
                        "id": "record-blocked",
                        "ordinal": 0,
                        "context": {
                            "session": "absent-chat",
                            "horizon": {"address": "turn-1", "hash": "hash-turn-1"},
                        },
                        "operation": {
                            "type": "block.create",
                            "parameters": {
                                "block_id": "b1",
                                "isoblock_id": "iso-b1",
                                "name": "Block",
                            },
                        },
                        "support": {
                            "neighborhoods": [
                                {
                                    "session": "absent-chat",
                                    "grounding": [
                                        {"address": "message-1", "hash": "hash-1"}
                                    ],
                                }
                            ]
                        },
                    }
                ],
            }
        ),
        "utf-8",
    )
    main(
        [
            "indexlab",
            "capture",
            *_selection(library, "blocked"),
            "--manifest",
            str(manifest),
        ]
    )
    capsys.readouterr()
    workspace_root = created["workspace"]
    (Path(str(workspace_root)) / TOUCH_MOCK_FILENAME).write_text(
        json.dumps({"schema": "tarav.indexlab-user-touch-mock.v1", "sessions": {}}),
        "utf-8",
    )

    exit_code = main(["indexlab", "lint", *_selection(library, "blocked")])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["clean"] is True
    assert payload["verified"] is False
    assert "ok" not in payload
    assert payload["counts"]["blocked"] >= 1
