"""LineMarkdown: a strict floor dialect for Markdown formats a project owns.

Every block delimiter sits alone on its own line. Code fences follow ordinary
fence syntax with the opener's info string free of backticks, and ``$$`` opens
or closes a math block only as the whole stripped line. Parsing stops at the
first violation: once a delimiter is wrong, every later fence and block
boundary is untrustworthy, so no partial model is returned.

The lenient ``MarkdownNormalModel`` parser remains the right choice for
ordinary hand-written Markdown.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re

from pydantic import TypeAdapter, field_validator

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.surfaces.markdown.model import (
    MarkdownFence,
    MarkdownHeading,
    MarkdownLine,
    MarkdownNormalModel,
    _CLOSING_HASHES_RE,
    _FENCE_RE,
    _HEADING_RE,
    _line_span,
)
from tarav.l1.surfaces.model import SourceSpan
from tarav.l1.surfaces.workflow import SURFACES_WORKFLOW_SHIP

MATH_NOT_ALONE = "LineMarkdown.Math.NotAlone"
MATH_UNCLOSED = "LineMarkdown.Math.Unclosed"
FENCE_INLINE_CLOSE = "LineMarkdown.Fence.InlineClose"
FENCE_UNCLOSED = "LineMarkdown.Fence.Unclosed"

MATH_DELIMITER = "$$"


@dataclass(frozen=True)
class MarkdownMathBlock:
    """A ``$$`` block; ``start`` and ``end`` are its delimiter lines."""

    start: SourceSpan
    end: SourceSpan


# tarav.breadcrumb 1edb1d876423
class LineMarkdownViolation(ValueError):
    """The first place where text leaves the LineMarkdown dialect."""

    def __init__(self, rule: str, message: str, span: SourceSpan) -> None:
        self.rule = rule
        self.message = message
        self.span = span
        super().__init__(f"{rule} at line {span.start_line}: {message}")

    @property
    def line(self) -> int:
        return self.span.start_line


# tarav.breadcrumb d70667449203
@dataclass
class LineMarkdownModel(MarkdownNormalModel):
    """Markdown facts of a text that conforms to the LineMarkdown dialect."""

    math_blocks: tuple[MarkdownMathBlock, ...]

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("3f788a00-c445-40b2-a62f-2f8c33c1a3b0"),
            name="Tarav.Surfaces.LineMarkdownModel",
            workflow=SURFACES_WORKFLOW_SHIP,
        )

    class RecordInterface(MarkdownNormalModel.RecordInterface):
        math_blocks: tuple[MarkdownMathBlock, ...]

        @field_validator("math_blocks", mode="before")
        @classmethod
        def read_math_blocks(cls, value, info):
            return TypeAdapter(
                cls.model_fields[info.field_name].annotation
            ).validate_json(json.dumps(value), strict=True)

    @classmethod
    def from_text(cls, text: str):
        """Parse ``text``; raise ``LineMarkdownViolation`` at the first violation."""

        return _parse_line_markdown(text, model_type=cls)

    @classmethod
    def _from_record(cls, record_data):
        return cls(
            text=record_data.text,
            lines=record_data.lines,
            headings=record_data.headings,
            fences=record_data.fences,
            diagnostics=record_data.diagnostics,
            math_blocks=record_data.math_blocks,
        )

    def math_line_numbers(self) -> frozenset[int]:
        """Return every source line belonging to a math block, delimiters included."""

        return frozenset(
            line_number
            for block in self.math_blocks
            for line_number in range(block.start.start_line, block.end.start_line + 1)
        )


_UNESCAPED_MATH_DELIMITER_RE = re.compile(r"(?<!\\)\$\$")


def _has_math_delimiter(text: str) -> bool:
    return _UNESCAPED_MATH_DELIMITER_RE.search(text) is not None


# tarav.breadcrumb 1ab6790c9152
def _parse_line_markdown(
    text: str, *, model_type: type[LineMarkdownModel]
) -> LineMarkdownModel:
    lines = tuple(
        MarkdownLine(line, _line_span(index, line))
        for index, line in enumerate(text.splitlines(), start=1)
    )
    headings: list[MarkdownHeading] = []
    fences: list[MarkdownFence] = []
    math_blocks: list[MarkdownMathBlock] = []

    fence_marker: str | None = None
    fence_length = 0
    fence_start: SourceSpan | None = None
    math_start: SourceSpan | None = None

    for line in lines:
        stripped = line.text.strip()

        if fence_marker is not None:
            fence_match = _FENCE_RE.match(line.text)
            if fence_match is not None:
                run = fence_match.group(1)
                remainder = line.text[fence_match.end() :]
                if run[0] == fence_marker and len(run) >= fence_length and not remainder.strip():
                    assert fence_start is not None
                    fences.append(
                        MarkdownFence(
                            marker=fence_marker,
                            length=fence_length,
                            start=fence_start,
                            end=line.span,
                            closing_length=len(run),
                        )
                    )
                    fence_marker = None
                    fence_length = 0
                    fence_start = None
            continue

        if math_start is not None:
            if stripped == MATH_DELIMITER:
                math_blocks.append(MarkdownMathBlock(start=math_start, end=line.span))
                math_start = None
            elif _has_math_delimiter(line.text):
                raise LineMarkdownViolation(
                    MATH_NOT_ALONE,
                    "a math block closes only with a line holding exactly $$",
                    line.span,
                )
            continue

        if stripped == MATH_DELIMITER:
            math_start = line.span
            continue
        if _has_math_delimiter(line.text):
            raise LineMarkdownViolation(
                MATH_NOT_ALONE,
                "$$ must sit alone on its own line",
                line.span,
            )

        fence_match = _FENCE_RE.match(line.text)
        if fence_match is not None:
            run = fence_match.group(1)
            info = line.text[fence_match.end() :]
            if run[0] == "`" and "`" in info:
                raise LineMarkdownViolation(
                    FENCE_INLINE_CLOSE,
                    "a code fence must open and close on separate lines",
                    line.span,
                )
            fence_marker = run[0]
            fence_length = len(run)
            fence_start = line.span
            continue

        heading_match = _HEADING_RE.match(line.text)
        if heading_match is not None:
            headings.append(
                MarkdownHeading(
                    level=len(heading_match.group(1)),
                    text=_CLOSING_HASHES_RE.sub("", heading_match.group(2)).strip(),
                    span=line.span,
                )
            )

    if fence_start is not None:
        raise LineMarkdownViolation(
            FENCE_UNCLOSED, "code fence is never closed", fence_start
        )
    if math_start is not None:
        raise LineMarkdownViolation(
            MATH_UNCLOSED, "math block is never closed", math_start
        )

    return model_type(
        text=text,
        lines=lines,
        headings=tuple(headings),
        fences=tuple(fences),
        diagnostics=(),
        math_blocks=tuple(math_blocks),
    )


__all__ = [
    "FENCE_INLINE_CLOSE",
    "FENCE_UNCLOSED",
    "LineMarkdownModel",
    "LineMarkdownViolation",
    "MATH_NOT_ALONE",
    "MATH_UNCLOSED",
    "MarkdownMathBlock",
]
