# $kw: ^markdown-normalizer --from Normalization.Pipeline --from Floor.Model --note [DF] line-oriented production of the minimal Markdown normal model ^c20260812-0u
"""Normalize raw Markdown into a small native model."""

from __future__ import annotations

import re

from agentos.surfaces.model import SourceSpan

from .model import MarkdownFence, MarkdownHeading, MarkdownLine, MarkdownNormalModel


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")


def _line_span(line_number: int, text: str) -> SourceSpan:
    return SourceSpan(line_number, 0, line_number, len(text))


def normalize_markdown(text: str) -> MarkdownNormalModel:
    """Recognize only lines, ATX headings, and fenced regions."""

    raw_lines = text.splitlines()
    lines = tuple(
        MarkdownLine(line, _line_span(index, line))
        for index, line in enumerate(raw_lines, start=1)
    )
    headings: list[MarkdownHeading] = []
    fences: list[MarkdownFence] = []
    open_marker: str | None = None
    open_span: SourceSpan | None = None
    for line in lines:
        fence_match = _FENCE_RE.match(line.text)
        if fence_match is not None:
            marker = fence_match.group(1)[0]
            if open_marker is None:
                open_marker = marker
                open_span = line.span
            elif marker == open_marker:
                assert open_span is not None
                fences.append(MarkdownFence(marker, open_span, line.span))
                open_marker = None
                open_span = None
            continue
        if open_marker is not None:
            continue
        heading_match = _HEADING_RE.match(line.text)
        if heading_match is not None:
            headings.append(
                MarkdownHeading(
                    level=len(heading_match.group(1)),
                    text=heading_match.group(2).strip(),
                    span=line.span,
                )
            )
    if open_marker is not None:
        assert open_span is not None
        fences.append(MarkdownFence(open_marker, open_span, None))
    return MarkdownNormalModel(
        text=text,
        lines=lines,
        headings=tuple(headings),
        fences=tuple(fences),
        diagnostics=(),
    )


__all__ = ["normalize_markdown"]
