from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .model import BlockHeading, IndexDepotModel, KernelLine


ISSUE_BLOCK_RE = re.compile(
    r"^(?P<identity>Issue\.I(?P<number>[0-9]{4}))"
    r"(?:\.(?P<name>[A-Z][A-Za-z0-9]*(?:\.[A-Z][A-Za-z0-9]*)*))?$"
)
ISSUE_FILENAME_RE = re.compile(r"^[1-9][0-9]{2}-issues\.md$")
IssueState = Literal["open", "resolved"]
ReferenceResolver = Callable[[str], bool]
ReviewResolver = Callable[[str, str], bool]


@dataclass(frozen=True)
class IssueLine:
    line: int
    line_type: str | None
    text: str
    anchors: tuple[str, ...]
    grounded: bool
    reviewed: bool


@dataclass(frozen=True)
class IssueRecord:
    identity: str
    number: int
    name: str | None
    block_path: str
    path: Path
    line: int
    state: IssueState
    lines: tuple[IssueLine, ...]
    resolution_lines: tuple[int, ...]

    @property
    def healthy(self) -> bool:
        return bool(self.lines) and all(
            line.line_type is not None and line.grounded for line in self.lines
        )


def issue_inventory(
    model: IndexDepotModel,
    *,
    resolve_support_reference: ReferenceResolver,
    resolve_review_reference: ReviewResolver,
) -> tuple[IssueRecord, ...]:
    records: list[IssueRecord] = []
    for document in model.documents:
        if document.surface_kind != "issues" or document.path is None:
            continue
        headings = {
            str(node.parsed.get("path", "")): node
            for node in document.nodes
            if isinstance(node, BlockHeading)
        }
        lines_by_block: dict[str, list[KernelLine]] = {}
        for node in document.nodes:
            if isinstance(node, KernelLine):
                lines_by_block.setdefault(
                    str(node.parsed.get("block_path", "")), []
                ).append(node)
        for block_path, heading in headings.items():
            match = ISSUE_BLOCK_RE.fullmatch(block_path)
            if match is None:
                continue
            issue_lines: list[IssueLine] = []
            resolution_lines: list[int] = []
            for line in lines_by_block.get(block_path, []):
                anchors = tuple(
                    str(span.parsed["anchor"])
                    for span in line.spans
                    if span.kind == "anchor"
                )
                grounded = any(resolve_support_reference(anchor) for anchor in anchors)
                reviewed = any(
                    resolve_review_reference(anchor, line.src) for anchor in anchors
                )
                line_type = line.parsed.get("act")
                if line_type == "DC" and reviewed:
                    resolution_lines.append(line.start_line)
                issue_lines.append(
                    IssueLine(
                        line=line.start_line,
                        line_type=str(line_type) if line_type is not None else None,
                        text=line.src,
                        anchors=anchors,
                        grounded=grounded,
                        reviewed=reviewed,
                    )
                )
            records.append(
                IssueRecord(
                    identity=match.group("identity"),
                    number=int(match.group("number")),
                    name=match.group("name"),
                    block_path=block_path,
                    path=document.path,
                    line=heading.start_line,
                    state="resolved" if resolution_lines else "open",
                    lines=tuple(issue_lines),
                    resolution_lines=tuple(resolution_lines),
                )
            )
    return tuple(sorted(records, key=lambda issue: (issue.number, str(issue.path))))
