from __future__ import annotations

from pathlib import Path


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_locator_loads_only_fingerprinted_anchor_sources(tmp_path: Path) -> None:
    from tarav.index.anchor_locator import (
        load_index_anchor_locator_selection,
        materialize_index_anchor_locator,
    )
    from tarav.index_model import parse_depot

    depot = tmp_path / "depot"
    workspace = tmp_path / "workspace"
    _write(
        depot / "design" / "100-design.md",
        "****\n## One\n\n- [CT] selected ^c20260811-1u\n****\n",
    )
    _write(
        depot / "design" / "200-design.md",
        "****\n## Two\n\n- [CT] unrelated ^c20260811-2u\n****\n",
    )
    model = parse_depot(depot)
    materialize_index_anchor_locator(
        depot_root=depot,
        lines=model.kernel_lines(),
        workspace_root=workspace,
        generated_at="2026-08-11T01:00:00Z",
    )

    selection = load_index_anchor_locator_selection(
        depot_root=depot,
        anchors=("c20260811-1u",),
        workspace_root=workspace,
    )

    assert selection.standing == "hit"
    assert selection.generated_at == "2026-08-11T01:00:00Z"
    assert selection.model is not None
    assert [document.path.name for document in selection.model.documents] == [
        "100-design.md"
    ]


def test_locator_rejects_changed_source(tmp_path: Path) -> None:
    from tarav.index.anchor_locator import (
        load_index_anchor_locator_selection,
        materialize_index_anchor_locator,
    )
    from tarav.index_model import parse_depot

    depot = tmp_path / "depot"
    workspace = tmp_path / "workspace"
    source = depot / "design" / "100-design.md"
    _write(source, "****\n## One\n\n- [CT] before ^c20260811-1u\n****\n")
    materialize_index_anchor_locator(
        depot_root=depot,
        lines=parse_depot(depot).kernel_lines(),
        workspace_root=workspace,
    )
    _write(source, "****\n## One\n\n- [CT] after ^c20260811-1u\n****\n")

    selection = load_index_anchor_locator_selection(
        depot_root=depot,
        anchors=("c20260811-1u",),
        workspace_root=workspace,
    )

    assert selection.standing == "stale"
    assert selection.reason == "locator source changed: design/100-design.md"


def test_locator_preserves_ambiguous_occurrence_standing(tmp_path: Path) -> None:
    from tarav.index.anchor_locator import (
        index_anchor_locator_path,
        materialize_index_anchor_locator,
    )
    from tarav.index_model import parse_depot
    import json

    depot = tmp_path / "depot"
    workspace = tmp_path / "workspace"
    _write(
        depot / "design" / "100-design.md",
        "****\n## One\n\n"
        "- [CT] first ^c20260811-1u\n"
        "- [CT] second ^c20260811-1u\n"
        "****\n",
    )
    materialize_index_anchor_locator(
        depot_root=depot,
        lines=parse_depot(depot).kernel_lines(),
        workspace_root=workspace,
    )

    payload = json.loads(
        index_anchor_locator_path(depot, workspace_root=workspace).read_text()
    )
    group = payload["anchors"]["c20260811-1u"]
    assert group["standing"] == "ambiguous"
    assert group["projection_count"] == 2
