from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.index.commands import _cmd_blocks
from agentos.index.model import block_grounding_stats, parse_depot

CHAPTER = """> router line

****

## Stamped.Block

- first line ^20260101-0
- second line ^20260101-0
- third line ^20260101-0
****

## Worked.Block

- first line ^20260101-1
- second line ^20260101-2
****

## Bare.Block

- first line
- second line
****

## Line.Type:Param

- parameterized block line ^20260101-3
****
"""

APPENDIX = """****

## Worked.Block/Grounding.Head

- [DC] evidence spot for the worked block ^20260101-9

****

## Bare.Block/Notes

- [DC] anchored grounding line under the WRONG section name ^20260101-8
"""


def _write_depot(root: Path) -> Path:
    depot = root / "skills" / "fixture-pkg"
    (depot / "design").mkdir(parents=True)
    (depot / "appendix").mkdir(parents=True)
    (depot / "000-INDEX.md").write_text(
        "- `design/100-design.md` — Stamped.Block, Worked.Block, Bare.Block, Line.Type:Param\n",
        encoding="utf-8",
    )
    (depot / "design" / "100-design.md").write_text(CHAPTER, encoding="utf-8")
    (depot / "appendix" / "Worked.Block-appendix.md").write_text(
        APPENDIX, encoding="utf-8"
    )
    return depot


def _blocks_args(depot: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "depot": [str(depot)],
        "scope": [],
        "sort": None,
        "limit": None,
        "json": True,
        "_support_reference_resolver": lambda _anchor: True,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_block_grounding_stats_computation(tmp_path: Path) -> None:
    depot = _write_depot(tmp_path)
    stats = {
        row.block_path: row
        for row in block_grounding_stats(
            parse_depot(depot),
            resolve_support_reference=lambda _anchor: True,
        )
    }

    assert set(stats) == {
        "Stamped.Block",
        "Worked.Block",
        "Bare.Block",
        "Line.Type:Param",
    }

    stamped = stats["Stamped.Block"]
    assert stamped.kernel_lines == 3
    assert stamped.unique_anchors == 1
    assert stamped.gr_density == pytest.approx(1 / 3)
    assert stamped.grounded_lines == 3

    worked = stats["Worked.Block"]
    assert worked.kernel_lines == 2
    assert worked.unique_anchors == 2
    assert worked.gr_density == pytest.approx(1.0)
    assert worked.grounded_lines == 2

    bare = stats["Bare.Block"]
    assert bare.unique_anchors == 0
    assert bare.gr_density == 0.0
    assert bare.grounded_lines == 0
    assert not hasattr(bare, "board")

    param = stats["Line.Type:Param"]
    assert param.kernel_lines == 1
    assert param.unique_anchors == 1


def test_block_grounding_stats_reject_anchor_only_grounding(tmp_path: Path) -> None:
    depot = _write_depot(tmp_path)
    stats = {
        row.block_path: row
        for row in block_grounding_stats(
            parse_depot(depot),
            resolve_support_reference=lambda _anchor: False,
        )
    }

    assert stats["Stamped.Block"].unique_anchors == 0
    assert stats["Stamped.Block"].grounded_lines == 0
    assert stats["Stamped.Block"].gr_density == 0.0


def test_blocks_cli_sorts_by_gr_density(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_depot(tmp_path)
    monkeypatch.chdir(tmp_path)
    exit_code = _cmd_blocks(_blocks_args(Path("skills/fixture-pkg"), sort="gr-density"))
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    names = [row["block_path"] for row in payload["blocks"]]
    assert names[0] == "Bare.Block"
    assert names[1] == "Stamped.Block"
    assert set(names[2:]) == {"Worked.Block", "Line.Type:Param"}
    rows = {row["block_path"]: row for row in payload["blocks"]}
    assert rows["Stamped.Block"]["grounded_lines"] == 3
    assert rows["Bare.Block"]["grounded_lines"] == 0
    assert "board" not in rows["Worked.Block"]
    summary = payload["summary"]
    assert summary["blocks"] == 4
    assert summary["kernel_lines"] == 8
    assert summary["unique_anchors"] == 4
    assert summary["gr_density"] == pytest.approx(4 / 8)


def test_blocks_cli_scope_and_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_depot(tmp_path)
    monkeypatch.chdir(tmp_path)
    exit_code = _cmd_blocks(
        _blocks_args(
            Path("skills/fixture-pkg"),
            sort="gr-density",
            scope=["skills/fixture-pkg/design"],
            limit=2,
        )
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["blocks"]) == 2
    assert payload["blocks"][0]["block_path"] == "Bare.Block"
    assert payload["summary"]["blocks"] == 4

    with pytest.raises(CliError):
        _cmd_blocks(
            _blocks_args(
                Path("skills/fixture-pkg"),
                scope=["skills/fixture-pkg/nonexistent"],
            )
        )


def test_blocks_cli_rejects_unknown_sort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_depot(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(CliError):
        _cmd_blocks(_blocks_args(Path("skills/fixture-pkg"), sort="alphabetical"))


def test_blocks_cli_requires_support_resolver(tmp_path: Path) -> None:
    depot = _write_depot(tmp_path)
    args = _blocks_args(depot)
    delattr(args, "_support_reference_resolver")

    with pytest.raises(CliError, match="support-reference resolver"):
        _cmd_blocks(args)
