# $kw: ^markdown-normal-model --from Floor.Model --note [DF] minimal normalized Markdown facts required by current surface consumers ^c20260812-0u
"""Normalized Markdown source facts."""

from __future__ import annotations

from dataclasses import dataclass

from tarav.surfaces.model import SourceDiagnostic, SourceSpan


@dataclass(frozen=True)
class MarkdownLine:
    """One source line retained for downstream surface adapters."""

    text: str
    span: SourceSpan


@dataclass(frozen=True)
class MarkdownHeading:
    """An ATX heading outside a fenced region."""

    level: int
    text: str
    span: SourceSpan


@dataclass(frozen=True)
class MarkdownFence:
    """A fenced region, whose end is absent when the source leaves it open."""

    marker: str
    length: int
    start: SourceSpan
    end: SourceSpan | None
    closing_length: int | None = None


@dataclass(frozen=True)
class MarkdownNormalModel:
    """The Markdown facts currently required by downstream consumers."""

    text: str
    lines: tuple[MarkdownLine, ...]
    headings: tuple[MarkdownHeading, ...]
    fences: tuple[MarkdownFence, ...]
    diagnostics: tuple[SourceDiagnostic, ...]

    def fenced_line_numbers(self) -> frozenset[int]:
        """Return every source line belonging to a fenced region."""

        last_line = len(self.lines)
        return frozenset(
            line_number
            for fence in self.fences
            for line_number in range(
                fence.start.start_line,
                (fence.end.start_line if fence.end is not None else last_line) + 1,
            )
        )


__all__ = [
    "MarkdownFence",
    "MarkdownHeading",
    "MarkdownLine",
    "MarkdownNormalModel",
]
