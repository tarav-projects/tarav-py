from __future__ import annotations

import json
from pathlib import Path

from agentos.cli import main
from _helpers import write_text_file as _write


def test_blocks_parses_separator_anchored_blocks(tmp_path: Path, capsys) -> None:
    md_path = tmp_path / "doc.md"
    _write(
        md_path,
        "\n".join(
            [
                "****",
                "## block-a",
                "A1",
                "****",
                "### block-b",
                "B1",
                "",
            ]
        ),
    )

    assert main(["stdlib", "mdblocks", "blocks", str(md_path), "--root", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["block_count"] == 2
    blocks = payload["files"][0]["blocks"]

    assert blocks[0]["title"] == "block-a"
    assert blocks[0]["separator_open_line"] == 1
    assert blocks[0]["separator_close_line"] == 4

    assert blocks[1]["title"] == "block-b"
    assert blocks[1]["separator_open_line"] == 4
    assert blocks[1]["separator_close_line"] is None


def test_blocks_supports_split_tmp_output_mode(tmp_path: Path, capsys) -> None:
    md_path = tmp_path / "doc.md"
    _write(md_path, "****\n## block-a\nA1\n")

    assert (
        main(
            [
                "stdlib",
                "mdblocks",
                "blocks",
                str(md_path),
                "--root",
                str(tmp_path),
                "--json",
                "--output-mode",
                "split-tmp",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["output_mode"] == "split-tmp"
    manifest_path = Path(payload["manifest_path"])
    assert manifest_path.is_file()


def test_blocks_respects_line_region(tmp_path: Path, capsys) -> None:
    md_path = tmp_path / "doc.md"
    _write(
        md_path,
        "\n".join(
            [
                "****",
                "## first",
                "first body",
                "****",
                "## second",
                "second body",
                "****",
                "## third",
                "third body",
                "",
            ]
        ),
    )

    assert (
        main(
            [
                "stdlib",
                "mdblocks",
                "blocks",
                str(md_path),
                "--root",
                str(tmp_path),
                "--start-line",
                "4",
                "--end-line",
                "7",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["start_line"] == 4
    assert payload["end_line"] == 7
    assert payload["block_count"] == 1
    file_payload = payload["files"][0]
    assert file_payload["scan_start_line"] == 4
    assert file_payload["scan_end_line"] == 7
    assert file_payload["blocks"][0]["title"] == "second"
    assert file_payload["blocks"][0]["start_line"] == 5


def test_find_respects_line_region(tmp_path: Path, capsys) -> None:
    md_path = tmp_path / "doc.md"
    _write(
        md_path,
        "\n".join(
            [
                "****",
                "## alpha",
                "payload alpha",
                "****",
                "## beta",
                "payload beta",
                "",
            ]
        ),
    )

    assert (
        main(
            [
                "stdlib",
                "mdblocks",
                "find",
                str(md_path),
                "--root",
                str(tmp_path),
                "--start-line",
                "4",
                "--query",
                "alpha",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["start_line"] == 4
    assert payload["match_count"] == 0


def test_lint_reports_separator_outside_semantics_as_error(tmp_path: Path, capsys) -> None:
    md_path = tmp_path / "doc.md"
    _write(
        md_path,
        "\n".join(
            [
                "****",
                "plain text before any h2 anchor",
                "****",
                "## valid-block",
                "body",
                "",
            ]
        ),
    )

    assert main(["stdlib", "mdblocks", "lint", str(md_path), "--root", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["error_count"] >= 1
    codes = [issue["code"] for issue in payload["issues"]]
    assert "separator_outside_block_semantics" in codes


def test_lint_enforces_hard_25_line_block_limit(tmp_path: Path, capsys) -> None:
    md_path = tmp_path / "doc.md"
    lines = ["****", "## too-long"] + [f"line {index}" for index in range(1, 26)] + ["****", ""]
    _write(md_path, "\n".join(lines))

    assert main(["stdlib", "mdblocks", "lint", str(md_path), "--root", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    issues = [issue for issue in payload["issues"] if issue["code"] == "block_too_long"]
    assert len(issues) == 1
    assert issues[0]["severity"] == "error"
    assert issues[0]["details"]["max_block_lines"] == 25
