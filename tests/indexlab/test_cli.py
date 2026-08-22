from __future__ import annotations

import json

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
        )
    )


def test_cli_initializes_captures_lists_and_projects(tmp_path, capsys) -> None:
    workspace = tmp_path / "lab"
    manifest = tmp_path / "capture.json"
    _manifest(manifest)

    assert main(["indexlab", "workspace", "init", "--workspace", str(workspace)]) == 0
    initialized = json.loads(capsys.readouterr().out)
    assert initialized["workspace"] == str(workspace.resolve())

    assert (
        main(
            [
                "indexlab",
                "capture",
                "--workspace",
                str(workspace),
                "--manifest",
                str(manifest),
            ]
        )
        == 0
    )
    captured = json.loads(capsys.readouterr().out)
    assert captured["ordinals"] == [1, 2]

    assert main(["indexlab", "records", "--workspace", str(workspace)]) == 0
    records = json.loads(capsys.readouterr().out)
    assert [record["id"] for record in records["records"]] == [
        "record-block",
        "record-line",
    ]

    assert main(["indexlab", "project", "--workspace", str(workspace)]) == 0
    projection = json.loads(capsys.readouterr().out)
    assert projection["blocks"][0]["line_ids"] == ["line-a"]


def test_cli_refuses_uninitialized_workspace(tmp_path, capsys) -> None:
    result = main(
        ["indexlab", "records", "--workspace", str(tmp_path / "not-initialized")]
    )

    assert result == 1
    assert "not an initialized IndexLab workspace" in capsys.readouterr().err


def test_mock_scenario_is_deterministic_and_lints_cleanly(tmp_path, capsys) -> None:
    projections = []
    for name in ("first", "second"):
        workspace = tmp_path / name
        assert (
            main(["indexlab", "workspace", "init", "--workspace", str(workspace)])
            == 0
        )
        capsys.readouterr()
        assert (
            main(
                [
                    "indexlab",
                    "scenario",
                    "seed-mock",
                    "--workspace",
                    str(workspace),
                ]
            )
            == 0
        )
        scenario = json.loads(capsys.readouterr().out)
        assert scenario["lint"]["verified"] is True
        projections.append(scenario["projection"])

        assert main(["indexlab", "lint", "--workspace", str(workspace)]) == 0
        assert json.loads(capsys.readouterr().out)["verified"] is True

    assert projections[0] == projections[1]


def test_indexlab_help_exposes_the_sandbox_boundary(capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["indexlab", "--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "experimental" in output.lower()
    assert "workspace" in output.lower()


def test_lint_exits_nonzero_when_a_check_is_blocked(tmp_path, capsys) -> None:
    """Fail closed: blocked is not a pass, even though nothing failed."""

    workspace = tmp_path / "lab"
    main(["indexlab", "workspace", "init", "--workspace", str(workspace)])
    capsys.readouterr()

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
            "--workspace",
            str(workspace),
            "--manifest",
            str(manifest),
        ]
    )
    capsys.readouterr()
    # An empty mock resolves nothing, so every check on this record is blocked.
    (workspace / TOUCH_MOCK_FILENAME).write_text(
        json.dumps({"schema": "tarav.indexlab-user-touch-mock.v1", "sessions": {}}),
        "utf-8",
    )

    exit_code = main(["indexlab", "lint", "--workspace", str(workspace)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["clean"] is True
    assert payload["verified"] is False
    assert "ok" not in payload
    assert payload["counts"]["blocked"] >= 1
