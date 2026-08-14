# $kw: ^native-surface-primitives --from Floor.Model --note [DF] source location and diagnostic primitives shared by native surface models ^c20260812-0u
"""Primitives shared by native source models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpan:
    """A half-open source span with one-based lines and zero-based columns."""

    start_line: int
    start_column: int
    end_line: int
    end_column: int


@dataclass(frozen=True)
class SourceDiagnostic:
    """A normalization problem that leaves the partial native model usable."""

    message: str
    span: SourceSpan | None = None


__all__ = ["SourceDiagnostic", "SourceSpan"]
