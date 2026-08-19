# $kw: --from Anchory.System --from Index.Line.Anchor
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from .identity import (
    canonical_index_line_anchor_triplet,
    canonical_index_line_statement,
    index_line_anchor_triplet_hash,
    index_line_statement_hash,
    index_line_statement_parts,
)
from .nodes import KernelLine, kernel_line_anchors, normalize_anchor


AnchorOccurrenceStanding = Literal["agreed", "ambiguous"]


@dataclass(frozen=True)
class IndexLineAnchorOccurrence:
    """One parsed occurrence of an anchor on an Index line."""

    anchor: str
    line: KernelLine
    line_type: str | None
    body: str
    statement_key: str
    statement_hash: str
    triplet_hash: str
    canonical_triplet: str

    @classmethod
    def from_line(cls, anchor: str, line: KernelLine) -> "IndexLineAnchorOccurrence":
        normalized = normalize_anchor(anchor)
        line_type, body = index_line_statement_parts(line.src)
        return cls(
            anchor=normalized,
            line=line,
            line_type=line_type,
            body=body,
            statement_key=canonical_index_line_statement(line.src),
            statement_hash=index_line_statement_hash(line.src),
            triplet_hash=index_line_anchor_triplet_hash(line.src, normalized),
            canonical_triplet=canonical_index_line_anchor_triplet(
                line.src, normalized
            ),
        )

    def location(self, root: Path) -> dict[str, object]:
        path = self.line.path
        if path is None:
            relative = "."
        else:
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                relative = str(path)
        return {
            "path": relative,
            "line": self.line.start_line,
            "path_line": f"{relative}:{self.line.start_line}",
        }


@dataclass(frozen=True)
class IndexLineAnchorOccurrenceGroup:
    """All parsed occurrences and projections observed for one anchor."""

    anchor: str
    occurrences: tuple[IndexLineAnchorOccurrence, ...]

    @property
    def projection_count(self) -> int:
        return len({item.statement_key for item in self.occurrences})

    @property
    def standing(self) -> AnchorOccurrenceStanding:
        return "agreed" if self.projection_count <= 1 else "ambiguous"

    @property
    def ambiguous(self) -> bool:
        return self.standing == "ambiguous"

    def projections(self) -> tuple[dict[str, str | None], ...]:
        by_statement: dict[str, IndexLineAnchorOccurrence] = {}
        for occurrence in self.occurrences:
            by_statement.setdefault(occurrence.statement_key, occurrence)
        return tuple(
            {
                "statement_hash": occurrence.statement_hash,
                "triplet_hash": occurrence.triplet_hash,
                "line_type": occurrence.line_type,
                "body": occurrence.body,
                "canonical": occurrence.canonical_triplet,
            }
            for _key, occurrence in sorted(by_statement.items())
        )

    def to_payload(self, root: Path) -> dict[str, object]:
        return {
            "anchor": self.anchor,
            "standing": self.standing,
            "occurrence_count": len(self.occurrences),
            "projection_count": self.projection_count,
            "occurrences": [
                {
                    **occurrence.location(root),
                    "statement_hash": occurrence.statement_hash,
                    "triplet_hash": occurrence.triplet_hash,
                }
                for occurrence in self.occurrences
            ],
        }


def group_index_line_anchor_occurrences(
    lines: Iterable[KernelLine],
    *,
    anchors: Iterable[str] = (),
) -> dict[str, IndexLineAnchorOccurrenceGroup]:
    """Group parsed lines by anchor using one canonical projection model."""

    wanted = {normalize_anchor(anchor) for anchor in anchors}
    grouped: dict[str, list[IndexLineAnchorOccurrence]] = {}
    for line in lines:
        for anchor in dict.fromkeys(kernel_line_anchors(line)):
            if wanted and anchor not in wanted:
                continue
            grouped.setdefault(anchor, []).append(
                IndexLineAnchorOccurrence.from_line(anchor, line)
            )
    return {
        anchor: IndexLineAnchorOccurrenceGroup(anchor, tuple(occurrences))
        for anchor, occurrences in sorted(grouped.items())
    }


__all__ = [
    "AnchorOccurrenceStanding",
    "IndexLineAnchorOccurrence",
    "IndexLineAnchorOccurrenceGroup",
    "group_index_line_anchor_occurrences",
]
