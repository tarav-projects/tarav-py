# $kw: ^skw-python-adapter --from Skw.Backend --from Floor.Model --note [DF] maps Python normal comments into common Skillware carrier facts ^c20260812-0u
"""Adapt a Python normal model to the common Skillware carrier model."""

from __future__ import annotations

import re

from tarav.surfaces.python import PythonNormalModel

from ..surface_model import (
    SkwHostPoint,
    SkwSurfaceAnnotation,
    SkwSurfaceLine,
    SkwSurfaceModel,
)


_OPEN_RE = re.compile(r"^#\s*\$kw:\s?(.*)$")
_CLOSE_RE = re.compile(r"^#\s*\$kw\.\s*(.*)$")
_FLAG_RE = re.compile(r"^#\s*(--[a-z][a-z0-9-]*(?:\s.*)?)$")


def _content(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.match(text)
    return match.group(1) if match is not None else None


def adapt_python_skw(
    model: PythonNormalModel,
    *,
    machinery_lines: frozenset[int] | None = None,
) -> SkwSurfaceModel:
    """Recognize Skillware only in tokenizer-confirmed full-line comments."""

    text_lines = model.text.splitlines()
    comments = {
        comment.span.start_line: comment
        for comment in model.comments
        if not text_lines[comment.span.start_line - 1][
            : comment.span.start_column
        ].strip()
        and (machinery_lines is None or comment.span.start_line in machinery_lines)
    }
    lines = []
    for line_number, text in enumerate(model.text.splitlines(), start=1):
        comment = comments.get(line_number)
        carrier_text = comment.text if comment is not None else ""
        lines.append(
            SkwSurfaceLine(
                text=text,
                open_content=_content(_OPEN_RE, carrier_text),
                close_content=_content(_CLOSE_RE, carrier_text),
                flag_content=_content(_FLAG_RE, carrier_text),
            )
        )
    return SkwSurfaceModel(
        carrier="python",
        lines=tuple(lines),
        host_points=tuple(
            SkwHostPoint(
                kind="class" if element.kind == "class" else "function",
                name=element.qualified_name,
                span=element.span,
            )
            for element in model.elements
        ),
        annotations=tuple(
            SkwSurfaceAnnotation(
                text=comment.text,
                span=comment.span,
                classification=(
                    "external-directive"
                    if comment.directive is not None
                    else "unclassified"
                ),
                external_kind=(
                    comment.directive.kind if comment.directive is not None else None
                ),
            )
            for comment in model.comments
        ),
        diagnostics=model.diagnostics,
    )


__all__ = ["adapt_python_skw"]
