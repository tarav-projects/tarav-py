# $kw: ^markdown-normalizer --from Normalization.Pipeline --from Floor.Model --note [DF] line-oriented production of the minimal Markdown normal model ^c20260812-0u
"""Normalize raw Markdown into a small native model."""

from __future__ import annotations

import re

from tarav.surfaces.model import SourceSpan

from .model import MarkdownFence, MarkdownHeading, MarkdownLine, MarkdownNormalModel


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_CLOSING_HASHES_RE = re.compile(r"[ \t]+#+[ \t]*$")


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
    open_length = 0
    open_span: SourceSpan | None = None
    for line in lines:
        fence_match = _FENCE_RE.match(line.text)
        if open_marker is not None:
            if fence_match is not None:
                run = fence_match.group(1)
                remainder = line.text[fence_match.end() :]
                if (
                    run[0] == open_marker
                    and len(run) >= open_length
                    and not remainder.strip()
                ):
                    assert open_span is not None
                    fences.append(
                        MarkdownFence(
                            marker=open_marker,
                            length=open_length,
                            start=open_span,
                            end=line.span,
                            closing_length=len(run),
                        )
                    )
                    open_marker = None
                    open_length = 0
                    open_span = None
            continue
        if fence_match is not None:
            run = fence_match.group(1)
            open_marker = run[0]
            open_length = len(run)
            open_span = line.span
            continue
        heading_match = _HEADING_RE.match(line.text)
        if heading_match is not None:
            heading_text = _CLOSING_HASHES_RE.sub("", heading_match.group(2)).strip()
            headings.append(
                MarkdownHeading(
                    level=len(heading_match.group(1)),
                    text=heading_text,
                    span=line.span,
                )
            )
    if open_marker is not None:
        assert open_span is not None
        fences.append(
            MarkdownFence(
                marker=open_marker,
                length=open_length,
                start=open_span,
                end=None,
            )
        )
    return MarkdownNormalModel(
        text=text,
        lines=lines,
        headings=tuple(headings),
        fences=tuple(fences),
        diagnostics=(),
    )


__all__ = ["normalize_markdown"]
