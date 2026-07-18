"""Grounding statistics over the parsed index model.

Computation lives here so any consumer (CLI report, future linter meters,
agents importing the library) reads the same numbers from the same parse.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .nodes import BlockHeading, IndexDepotModel, KernelLine


@dataclass(frozen=True)
class BlockGroundingStats:
    block_path: str
    path: Path | None
    line: int
    kernel_lines: int
    anchors: frozenset[str]
    gr_density: float
    grounded_lines: int

    @property
    def unique_anchors(self) -> int:
        return len(self.anchors)


def block_grounding_stats(model: IndexDepotModel) -> list[BlockGroundingStats]:
    """Per-concept-block grounding stats: `Grounding.Density` plus line coverage.

    Concept blocks are chapter-surface top-level headings (valid path, no
    segments) — the same denominator the linter's block coverage meter uses.
    Grounding is a line property: `grounded_lines` counts kernel lines carrying
    at least one trailing anchor; density counts unique inline anchors only.
    """
    stats: list[BlockGroundingStats] = []
    for document in model.documents:
        if document.surface_kind != "chapter":
            continue
        lines_by_block: dict[str, list[KernelLine]] = {}
        for node in document.nodes:
            if isinstance(node, KernelLine):
                block = str(node.parsed.get("block_path", ""))
                lines_by_block.setdefault(block, []).append(node)
        for node in document.nodes:
            if not isinstance(node, BlockHeading):
                continue
            if not node.parsed.get("valid") or node.parsed.get("segments") != []:
                continue
            block_path = str(node.parsed["path"]).strip()
            lines = lines_by_block.get(block_path, [])
            anchors = {
                str(span.parsed["anchor"])
                for line in lines
                for span in line.spans
                if span.kind == "anchor"
            }
            kernel_lines = len(lines)
            grounded_lines = sum(
                1
                for line in lines
                if any(span.kind == "anchor" for span in line.spans)
            )
            stats.append(
                BlockGroundingStats(
                    block_path=block_path,
                    path=node.path,
                    line=node.start_line,
                    kernel_lines=kernel_lines,
                    anchors=frozenset(anchors),
                    gr_density=(len(anchors) / kernel_lines) if kernel_lines else 0.0,
                    grounded_lines=grounded_lines,
                )
            )
    return stats


__all__ = ["BlockGroundingStats", "block_grounding_stats"]
