# $kw: ^markdown-normal-model --from Floor.Model --note [DF] minimal normalized Markdown facts required by current surface consumers ^c20260812-0u
"""Normalized Markdown source facts."""

from __future__ import annotations

from dataclasses import dataclass

from agentos.surfaces.model import SourceDiagnostic, SourceSpan


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
    start: SourceSpan
    end: SourceSpan | None


@dataclass(frozen=True)
class MarkdownNormalModel:
    """The Markdown facts currently required by downstream consumers."""

    text: str
    lines: tuple[MarkdownLine, ...]
    headings: tuple[MarkdownHeading, ...]
    fences: tuple[MarkdownFence, ...]
    diagnostics: tuple[SourceDiagnostic, ...]


__all__ = [
    "MarkdownFence",
    "MarkdownHeading",
    "MarkdownLine",
    "MarkdownNormalModel",
]
