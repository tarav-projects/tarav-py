from __future__ import annotations

from pathlib import Path

from agentos.index.model import (
    BlockHeading,
    CodeFence,
    Diagnostic,
    KernelLine,
    MetaLine,
    RouterEntry,
    parse_depot,
    parse_index_file,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_index_model_parses_structural_nodes_and_diagnostics() -> None:
    document = parse_index_file(
        "\n".join(
            [
                "> prologue",
                "## Missing.Separator",
                "",
                "****",
                "",
                "## Agentos.Skillware",
                "",
                "- `Agentos.Skillware` is a discipline.",
                "****",
                "```json",
                '{"anchor": "^20260708-0"}',
                "",
            ]
        )
    )

    assert [type(node).__name__ for node in document.nodes[:7]] == [
        "Text",
        "Diagnostic",
        "BlockHeading",
        "BlankLine",
        "Separator",
        "BlankLine",
        "BlockHeading",
    ]
    assert any(
        isinstance(node, BlockHeading) and node.parsed["path"] == "Agentos.Skillware"
        for node in document.nodes
    )
    assert any(
        isinstance(node, Diagnostic) and node.reason == "heading_without_separator"
        for node in document.nodes
    )
    assert any(
        isinstance(node, Diagnostic) and node.reason == "unclosed_code_fence"
        for node in document.nodes
    )


def test_index_model_parses_kernel_lines_spans_meta_and_fences() -> None:
    document = parse_index_file(
        "\n".join(
            [
                "****",
                "## Example.Concept",
                "",
                "- [AS:CT] text cites `Example.Concept` and `notes/live/x.md` ^20260708-0",
                "- untyped legacy line",
                "",
                "### meta",
                "",
                "- aliases: `Example.Alias`",
                "",
                "```json",
                '{"fake": "^20260708-1", "concept": "Example.Hidden"}',
                "```",
                "****",
                "",
            ]
        )
    )

    typed = next(node for node in document.nodes if isinstance(node, KernelLine))
    assert typed.parsed["act"] == "CT"
    assert typed.parsed["source"] == "AS"
    assert [(span.kind, typed.src[span.start : span.end]) for span in typed.spans] == [
        ("type_bracket", "[AS:CT]"),
        ("concept_cite", "`Example.Concept`"),
        ("file_mention", "`notes/live/x.md`"),
        ("anchor", "^20260708-0"),
    ]
    assert any(isinstance(node, MetaLine) for node in document.nodes)
    assert not [
        span
        for node in document.nodes
        if isinstance(node, CodeFence)
        for span in node.spans
        if span.kind == "anchor"
    ]


def test_index_model_parses_router_dialects_depot_and_anchor_queries(tmp_path: Path) -> None:
    depot = tmp_path / "depot"
    _write(
        depot / "000-INDEX.md",
        "# Router\n\n"
        "## Routing\n\n"
        "- `design/100-design.md` — Example.Concept[+1], Other.Concept\n\n"
        "## Chapters\n\n"
        "### design\n\n"
        "- `design/101-design.md` — Third.Concept\n",
    )
    _write(
        depot / "design" / "100-design.md",
        "****\n## Example.Concept\n\n- [GR] linked ^20260705-0\n****\n",
    )
    _write(depot / "design" / "101-design.md", "****\n## Third.Concept\n\n- text\n****\n")
    _write(depot / "appendix" / "Example.Concept-appendix.md", "****\n## Example.Concept/Depth\n\n- depth\n****\n")
    _write(depot / "agendix" / "Example.Concept-agendix.md", "****\n## Example.Concept/Agendix\n\n- [AS:CT] capture ^20260708-0\n****\n")
    _write(depot / "design" / "AGENTS.md", "# ignored\n")

    model = parse_depot(depot)

    router_entries = [
        node
        for document in model.documents
        for node in document.nodes
        if isinstance(node, RouterEntry)
    ]
    assert [entry.parsed["file"] for entry in router_entries] == [
        "design/100-design.md",
        "design/101-design.md",
    ]
    assert router_entries[0].parsed["concepts"][0] == {
        "concept": "Example.Concept",
        "plus_n": 1,
        "raw": "Example.Concept[+1]",
    }
    assert {document.surface_kind for document in model.documents} == {
        "router",
        "chapter",
        "appendix",
        "agendix",
    }
    assert all(document.path is None or document.path.name != "AGENTS.md" for document in model.documents)
    assert [(line.path.name, line.start_line) for line in model.blocks_by_anchor("20260705-0")] == [
        ("100-design.md", 4)
    ]
    assert model.anchors_by_block("Example.Concept") == ["20260705-0"]
