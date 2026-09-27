# $kw: ^markdown-normal-model --from Floor.Model --note [DF] minimal normalized Markdown facts required by current surface consumers ^c20260812-0u
"""Normalized Markdown source facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re

import json
from pydantic import ConfigDict, TypeAdapter, field_validator
from tarav.kernel import TaravObject, TaravClass, TypeShip, entity
from tarav.surfaces.workflow import SURFACES_WORKFLOW_SHIP

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


@dataclass
class MarkdownNormalModel(TaravObject):
    """The Markdown facts currently required by downstream consumers."""

    text: str
    lines: tuple[MarkdownLine, ...]
    headings: tuple[MarkdownHeading, ...]
    fences: tuple[MarkdownFence, ...]
    diagnostics: tuple[SourceDiagnostic, ...]

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("783d9112-bad2-4a81-bb8c-609f3958519e"),
            name="Tarav.Surfaces.MarkdownNormalModel",
            workflow=SURFACES_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: str
        text: str
        lines: tuple[MarkdownLine, ...]
        headings: tuple[MarkdownHeading, ...]
        fences: tuple[MarkdownFence, ...]
        diagnostics: tuple[SourceDiagnostic, ...]

        @field_validator("lines", "headings", "fences", "diagnostics", mode="before")
        @classmethod
        def read_items(cls, value, info):
            # JSON-mode validation reconstructs dataclasses from JSON objects.
            # Tarav's Record boundary checks that serialization is unchanged.
            return TypeAdapter(
                cls.model_fields[info.field_name].annotation
            ).validate_json(json.dumps(value), strict=True)

    def __post_init__(self):
        TaravObject.__init__(self)

    @classmethod
    def from_text(cls, text: str):
        return _parse(text, model_type=cls)

    @classmethod
    def from_path(cls, path: Path | str):
        return cls.from_text(Path(path).expanduser().read_text(encoding="utf-8"))

    def _to_record(self):
        return {"type": entity(type(self)).name, **json.loads(json.dumps(asdict(self)))}

    @classmethod
    def _from_record(cls, record_data):
        return cls(
            text=record_data.text,
            lines=record_data.lines,
            headings=record_data.headings,
            fences=record_data.fences,
            diagnostics=record_data.diagnostics,
        )

    @classmethod
    def record_example(cls):
        return cls.from_text("").to_record()

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


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_CLOSING_HASHES_RE = re.compile(r"[ \t]+#+[ \t]*$")


def _line_span(line_number: int, text: str) -> SourceSpan:
    return SourceSpan(line_number, 0, line_number, len(text))


def _parse(text: str, *, model_type: type[MarkdownNormalModel]) -> MarkdownNormalModel:
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
    return model_type(
        text=text,
        lines=lines,
        headings=tuple(headings),
        fences=tuple(fences),
        diagnostics=(),
    )
