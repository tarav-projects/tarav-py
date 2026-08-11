from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


IndexSurfaceKind = Literal[
    "router", "chapter", "appendix", "agendix", "issues", "unknown"
]


@dataclass(frozen=True)
class InlineSpan:
    kind: str
    src: str
    start: int
    end: int
    line: int
    column: int
    parsed: dict[str, Any] = field(default_factory=dict)


@dataclass
class Node:
    src: str
    start_line: int
    end_line: int
    parsed: dict[str, Any] = field(default_factory=dict)
    spans: list[InlineSpan] = field(default_factory=list)
    path: Path | None = None

    @property
    def type(self) -> str:
        return type(self).__name__


@dataclass
class Separator(Node):
    pass


@dataclass
class BlockHeading(Node):
    pass


@dataclass
class KernelLine(Node):
    pass


@dataclass
class MetaHeading(Node):
    pass


@dataclass
class MetaLine(Node):
    pass


@dataclass
class RouterEntry(Node):
    pass


@dataclass
class BlankLine(Node):
    pass


@dataclass
class Text(Node):
    pass


@dataclass
class CodeFence(Node):
    pass


@dataclass
class Diagnostic(Node):
    reason: str = ""


@dataclass
class IndexDocument:
    nodes: list[Node] = field(default_factory=list)
    path: Path | None = None
    surface_kind: IndexSurfaceKind = "unknown"

    def diagnostics(self) -> list[Diagnostic]:
        return [node for node in self.nodes if isinstance(node, Diagnostic)]

    def kernel_lines(self) -> list[KernelLine]:
        return [node for node in self.nodes if isinstance(node, KernelLine)]


@dataclass
class IndexDepotModel:
    root: Path
    documents: tuple[IndexDocument, ...]

    def kernel_lines(self) -> list[KernelLine]:
        return [line for document in self.documents for line in document.kernel_lines()]

    def blocks_by_anchor(self, anchor: str) -> list[KernelLine]:
        token = normalize_anchor(anchor)
        return [
            line
            for line in self.kernel_lines()
            if token in kernel_line_anchors(line)
        ]

    def anchors_by_block(self, block_path: str) -> list[str]:
        anchors: list[str] = []
        for line in self.kernel_lines():
            if line.parsed.get("block_path") != block_path:
                continue
            for span in line.spans:
                if span.kind == "anchor":
                    anchors.append(str(span.parsed["anchor"]))
        return anchors


def normalize_anchor(anchor: str) -> str:
    """Return the provider-neutral anchor key without a citation sigil."""
    token = anchor.strip()
    return token[1:] if token.startswith(("^", "@")) else token


def kernel_line_anchors(line: KernelLine) -> tuple[str, ...]:
    """Return every anchor attached to one parsed Index line, in source order."""
    return tuple(
        str(span.parsed["anchor"])
        for span in line.spans
        if span.kind == "anchor" and span.parsed.get("anchor")
    )
