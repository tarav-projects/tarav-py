from __future__ import annotations

from pathlib import Path


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_manifest_projects_block_bounded_line_context(tmp_path: Path) -> None:
    from agentos.index.line_manifest import build_index_line_manifest

    depot = tmp_path / "depot"
    _write(
        depot / "design" / "100-design.md",
        "****\n## First.Block\n\n"
        "- [DF] first sibling ^c20260811-1u\n"
        "- [CT] selected body ^c20260811-2u\n"
        "- [PR] last sibling ^c20260811-3u\n"
        "****\n\n## Second.Block\n\n"
        "- [DC] must not leak ^c20260811-4u\n"
        "****\n",
    )

    manifest = build_index_line_manifest(
        depot_root=depot,
        anchors=("c20260811-2u",),
        neighbors=1,
        generated_at="2026-08-11T01:00:00Z",
    )

    assert manifest["schema"] == "agentos.index-line-manifest.v2"
    line = manifest["lines"][0]
    assert line["statement"]["type"] == "CT"
    assert line["statement"]["body"] == "selected body"
    assert line["block"]["path"] == "First.Block"
    assert line["block"]["line_ordinal"] == 2
    assert line["block"]["line_count"] == 3
    assert [item["statement"]["body"] for item in line["context"]["before"]] == [
        "first sibling"
    ]
    assert [item["statement"]["body"] for item in line["context"]["after"]] == [
        "last sibling"
    ]
    assert line["context"]["omitted_before"] == 0
    assert line["context"]["omitted_after"] == 0
    assert "must not leak" not in str(line["context"])


def test_manifest_reports_context_omissions_and_supports_unanchored_scope(
    tmp_path: Path,
) -> None:
    from agentos.index.line_manifest import build_index_line_manifest

    depot = tmp_path / "depot"
    _write(
        depot / "design" / "100-design.md",
        "****\n## Example.Block\n\n"
        "- [DF] zero\n"
        "- [CT] one\n"
        "- [DC] two ^c20260811-2u\n"
        "- [PR] three\n"
        "- [EX] four\n"
        "****\n",
    )

    manifest = build_index_line_manifest(
        depot_root=depot,
        scopes=("design/100-design.md",),
        neighbors=1,
        limit=3,
    )

    assert manifest["summary"] == {
        "requested_line_count": 5,
        "line_count": 3,
        "omitted_line_count": 2,
        "anchor_count": 1,
        "turn_count": 0,
        "referenced_session_count": 0,
        "verified_session_count": 0,
    }
    selected = manifest["lines"][2]
    assert selected["statement"]["body"] == "two"
    assert selected["context"]["omitted_before"] == 1
    assert selected["context"]["omitted_after"] == 1


def test_manifest_merges_injected_relationship_projection(tmp_path: Path) -> None:
    from agentos.index.line_manifest import (
        build_index_line_manifest,
        format_index_line_manifest_text,
    )

    depot = tmp_path / "depot"
    _write(
        depot / "design" / "100-design.md",
        "****\n## Example.Block\n\n"
        "- [CT] selected ^c20260811-2u\n"
        "****\n",
    )
    calls: list[tuple[str, str]] = []

    def project(anchor: str, source: str) -> dict[str, object]:
        calls.append((anchor, source))
        return {
            "anchor": {
                "anchor": anchor,
                "relationships": {
                    "support": {},
                    "gates": {
                        "semantic_approval": [
                            {
                                "approval_turn": "session:turn-1",
                                "approval_turn_verification": "stored",
                            }
                        ]
                    },
                    "provenance": {"predecessor_anchors": ["c20260810-1u"]},
                },
            },
            "turns": {
                "session:turn-1": {
                    "ref": {"session": "session", "turn_id": "turn-1"},
                    "verification": "stored",
                }
            },
            "verified_sessions": [],
        }

    manifest = build_index_line_manifest(
        depot_root=depot,
        anchors=("c20260811-2u",),
        relationship_projector=project,
    )

    assert calls == [
        ("c20260811-2u", "- [CT] selected ^c20260811-2u")
    ]
    assert manifest["lines"][0]["anchors"][0]["relationships"]["support"] == {}
    assert manifest["turns"]["session:turn-1"]["verification"] == "stored"
    rendered = format_index_line_manifest_text(manifest)
    assert "gate semantic_approval:" in rendered
    assert "approval_turn [stored]: session:turn-1" in rendered
    assert 'provenance predecessor_anchors: ["c20260810-1u"]' in rendered
