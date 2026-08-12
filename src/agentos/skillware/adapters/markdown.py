# $kw: ^skw-markdown-adapter --from Skw.Backend --from Floor.Model --note [DF] maps Markdown normal nodes into common Skillware carrier facts ^c20260812-0u
"""Adapt a Markdown normal model to the common Skillware carrier model."""

from __future__ import annotations

import re

from agentos.surfaces.markdown import MarkdownNormalModel

from ..surface_model import SkwSurfaceLine, SkwSurfaceModel


_OPEN_RE = re.compile(r"^>\s*\$kw:\s?(.*)$")
_CLOSE_RE = re.compile(r"^>\s*\$kw\.\s*(.*)$")
_FLAG_RE = re.compile(r"^>\s*(--\S.*)$")


def _content(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.match(text)
    return match.group(1) if match is not None else None


def adapt_markdown_skw(model: MarkdownNormalModel) -> SkwSurfaceModel:
    """Map headings and fence endpoints while preserving native line text."""

    headings = {heading.span.start_line: heading.text for heading in model.headings}
    fence_lines = {
        span.start_line
        for fence in model.fences
        for span in (fence.start, fence.end)
        if span is not None
    }
    return SkwSurfaceModel(
        carrier="markdown",
        boundary_label="heading",
        lines=tuple(
            SkwSurfaceLine(
                text=line.text,
                open_content=_content(_OPEN_RE, line.text),
                close_content=_content(_CLOSE_RE, line.text),
                flag_content=_content(_FLAG_RE, line.text),
                fence=line.span.start_line in fence_lines,
                boundary_name=headings.get(line.span.start_line),
            )
            for line in model.lines
        ),
        diagnostics=model.diagnostics,
    )


__all__ = ["adapt_markdown_skw"]
