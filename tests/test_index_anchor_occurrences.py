from __future__ import annotations

from pathlib import Path


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_anchor_occurrence_groups_identical_materializations(tmp_path: Path) -> None:
    from tarav.index_model import (
        group_index_line_anchor_occurrences,
        parse_depot,
    )

    depot = tmp_path / "depot"
    _write(
        depot / "design" / "100-design.md",
        "****\n## First\n\n- [CT] shared body ^c20260811-1u\n****\n",
    )
    _write(
        depot / "appendix" / "First.Block-appendix.md",
        "****\n## First.Block/Detail\n\n- [CT] shared body ^c20260811-1u\n****\n",
    )

    group = group_index_line_anchor_occurrences(
        parse_depot(depot).kernel_lines()
    )["c20260811-1u"]

    assert group.standing == "agreed"
    assert group.projection_count == 1
    assert len(group.occurrences) == 2
    assert {item.location(depot)["path"] for item in group.occurrences} == {
        "design/100-design.md",
        "appendix/First.Block-appendix.md",
    }


def test_anchor_occurrence_groups_type_and_body_conflicts(tmp_path: Path) -> None:
    from tarav.index_model import (
        group_index_line_anchor_occurrences,
        parse_depot,
    )

    depot = tmp_path / "depot"
    _write(
        depot / "design" / "100-design.md",
        "****\n## First\n\n"
        "- [CT] shared body ^c20260811-1u\n"
        "- [DC] shared body ^c20260811-1u\n"
        "- [CT] other body ^c20260811-1u\n"
        "****\n",
    )

    group = group_index_line_anchor_occurrences(
        parse_depot(depot).kernel_lines()
    )["c20260811-1u"]

    assert group.standing == "ambiguous"
    assert group.projection_count == 3
    assert len({item["statement_hash"] for item in group.projections()}) == 3
    payload = group.to_payload(depot)
    assert payload["standing"] == "ambiguous"
    assert payload["occurrence_count"] == 3
    assert payload["projection_count"] == 3
