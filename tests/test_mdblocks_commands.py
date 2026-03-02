from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli import main


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


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

    assert main(["mdblocks", "blocks", str(md_path), "--root", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["block_count"] == 2
    blocks = payload["files"][0]["blocks"]

    assert blocks[0]["title"] == "block-a"
    assert blocks[0]["separator_open_line"] == 1
    assert blocks[0]["separator_close_line"] == 4

    assert blocks[1]["title"] == "block-b"
    assert blocks[1]["separator_open_line"] == 4
    assert blocks[1]["separator_close_line"] is None


def test_blocks_ignores_triple_star_separator(tmp_path: Path, capsys) -> None:
    md_path = tmp_path / "doc.md"
    _write(
        md_path,
        "\n".join(
            [
                "***",
                "## not-a-block",
                "body",
                "***",
                "",
            ]
        ),
    )

    assert main(["mdblocks", "blocks", str(md_path), "--root", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["block_count"] == 0


def test_blocks_supports_split_tmp_output_mode(tmp_path: Path, capsys) -> None:
    md_path = tmp_path / "doc.md"
    _write(md_path, "****\n## block-a\nA1\n")

    assert (
        main(
            [
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

    assert main(["mdblocks", "lint", str(md_path), "--root", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["error_count"] >= 1
    codes = [issue["code"] for issue in payload["issues"]]
    assert "separator_outside_block_semantics" in codes


def test_lint_enforces_hard_25_line_block_limit(tmp_path: Path, capsys) -> None:
    md_path = tmp_path / "doc.md"
    lines = ["****", "## too-long"] + [f"line {index}" for index in range(1, 26)] + ["****", ""]
    _write(md_path, "\n".join(lines))

    assert main(["mdblocks", "lint", str(md_path), "--root", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    issues = [issue for issue in payload["issues"] if issue["code"] == "block_too_long"]
    assert len(issues) == 1
    assert issues[0]["severity"] == "error"
    assert issues[0]["details"]["max_block_lines"] == 25


def test_cli_rejects_min_level_below_two(capsys) -> None:
    with pytest.raises(SystemExit, match="--min-level must be between 2 and 6"):
        main(["mdblocks", "blocks", "--min-level", "1"])


def test_lint_help_does_not_expose_max_block_lines_flag(capsys) -> None:
    with pytest.raises(SystemExit, match="0"):
        main(["mdblocks", "lint", "--help"])
    output = capsys.readouterr().out
    assert "--max-block-lines" not in output
