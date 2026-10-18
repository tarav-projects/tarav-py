"""Normalized TypeScript source facts: the comments, found by a small lexer.

This is not a parser. It walks the text once, skipping strings, template
literals (with nested `${...}` expressions), block comments and regular
expression literals, so that a `//` inside any of them is not read as a
comment. A `/` starts a regular expression when the previous significant
token cannot end an expression; otherwise it is division. Known limit: in
`.tsx`, `//` inside JSX text reads as a comment.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from pydantic import ConfigDict, TypeAdapter, field_validator
from tarav.l0.kernel import TaravClass, TaravObject, TypeShip, entity
from tarav.l1.surfaces.model import SourceDiagnostic, SourceSpan
from tarav.l1.surfaces.workflow import SURFACES_WORKFLOW_SHIP

# After one of these keywords an expression starts, so `/` opens a regex.
_EXPRESSION_KEYWORDS = frozenset({
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
    "throw", "case", "do", "else", "yield", "await",
})
# After one of these characters an expression ends, so `/` is division.
_EXPRESSION_END = frozenset(")]}")


@dataclass(frozen=True)
class TypeScriptComment:
    """A lexer-confirmed comment: `line` for `//`, `block` for `/* */`."""

    kind: str
    text: str
    span: SourceSpan


# tarav.breadcrumb ba7f5984d4ab
@dataclass
class TypeScriptNormalModel(TaravObject):
    """The TypeScript facts current consumers need: comments and diagnostics."""

    text: str
    comments: tuple[TypeScriptComment, ...]
    diagnostics: tuple[SourceDiagnostic, ...]

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("7af7d62a-858f-4d1c-afa4-030cf77ad193"),
            name="Tarav.Surfaces.TypeScriptNormalModel",
            workflow=SURFACES_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: str
        text: str
        comments: tuple[TypeScriptComment, ...]
        diagnostics: tuple[SourceDiagnostic, ...]

        @field_validator("comments", "diagnostics", mode="before")
        @classmethod
        def read_items(cls, value, info):
            return TypeAdapter(
                cls.model_fields[info.field_name].annotation
            ).validate_json(json.dumps(value), strict=True)

    def __post_init__(self):
        TaravObject.__init__(self)

    @classmethod
    def from_text(cls, text: str):
        comments, diagnostics = _lex(text)
        return cls(text=text, comments=tuple(comments), diagnostics=tuple(diagnostics))

    @classmethod
    def from_path(cls, path: Path | str):
        return cls.from_text(Path(path).expanduser().read_text(encoding="utf-8"))

    def _to_record(self):
        return {"type": entity(type(self)).name, **json.loads(json.dumps(asdict(self)))}

    @classmethod
    def _from_record(cls, record_data):
        return cls(text=record_data.text, comments=record_data.comments,
                   diagnostics=record_data.diagnostics)

    class Records(TaravObject.Records):
        def record_example(self):
            return self._owner.from_text("").records.to_record()


class _Cursor:
    """Offsets to one-based lines and zero-based columns."""

    def __init__(self, text: str) -> None:
        self.starts = [0]
        for index, char in enumerate(text):
            if char == "\n":
                self.starts.append(index + 1)

    def position(self, offset: int) -> tuple[int, int]:
        low, high = 0, len(self.starts) - 1
        while low < high:
            middle = (low + high + 1) // 2
            if self.starts[middle] <= offset:
                low = middle
            else:
                high = middle - 1
        return low + 1, offset - self.starts[low]

    def span(self, start: int, end: int) -> SourceSpan:
        start_line, start_column = self.position(start)
        end_line, end_column = self.position(end)
        return SourceSpan(start_line, start_column, end_line, end_column)


def _lex(text: str) -> tuple[list[TypeScriptComment], list[SourceDiagnostic]]:
    cursor = _Cursor(text)
    comments: list[TypeScriptComment] = []
    diagnostics: list[SourceDiagnostic] = []
    # Each open template literal remembers the brace depth of its `${`.
    templates: list[int] = []
    depth = 0
    previous = ""  # last significant token: a character or a word
    index, size = 0, len(text)

    def problem(message: str, start: int) -> None:
        diagnostics.append(SourceDiagnostic(message, cursor.span(start, size)))

    def template_body(start: int) -> int:
        """Scan template text from `start`; return the offset after its end or `${`."""
        position = start
        while position < size:
            char = text[position]
            if char == "\\":
                position += 2
            elif char == "`":
                templates.pop()
                return position + 1
            elif char == "$" and text.startswith("${", position):
                return position + 2
            else:
                position += 1
        problem("Unterminated template literal", start)
        return size

    while index < size:
        char = text[index]
        if char in " \t\r\n\f\v﻿":
            index += 1
        elif text.startswith("//", index):
            end = text.find("\n", index)
            end = size if end < 0 else end
            body = text[index:end].rstrip("\r")
            comments.append(TypeScriptComment("line", body, cursor.span(index, index + len(body))))
            index = end
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                problem("Unterminated block comment", index)
                end = size
            else:
                end += 2
            comments.append(TypeScriptComment("block", text[index:end], cursor.span(index, end)))
            index = end
        elif char in "'\"":
            position = index + 1
            while position < size and text[position] not in (char, "\n"):
                position += 2 if text[position] == "\\" else 1
            if position >= size or text[position] != char:
                problem("Unterminated string literal", index)
            index = min(position + 1, size)
            previous = "string"
        elif char == "`":
            templates.append(depth)
            index = template_body(index + 1)
            previous = "string"
        elif char == "/" and (previous == "" or previous in _EXPRESSION_KEYWORDS
                              or (len(previous) == 1 and previous not in _EXPRESSION_END)):
            position, in_class = index + 1, False
            while position < size and text[position] != "\n":
                current = text[position]
                if current == "\\":
                    position += 2
                    continue
                if current == "[":
                    in_class = True
                elif current == "]":
                    in_class = False
                elif current == "/" and not in_class:
                    break
                position += 1
            if position >= size or text[position] != "/":
                problem("Unterminated regular expression literal", index)
                index = position
            else:
                index = position + 1
                while index < size and (text[index].isalnum() or text[index] == "_"):
                    index += 1
            previous = "regex"
        elif char.isalnum() or char in "_$":
            start = index
            while index < size and (text[index].isalnum() or text[index] in "_$"):
                index += 1
            previous = text[start:index]
        elif char == "{":
            depth += 1
            previous = char
            index += 1
        elif char == "}":
            if templates and templates[-1] == depth:
                index = template_body(index + 1)
                previous = "string"
            else:
                depth -= 1
                previous = char
                index += 1
        else:
            previous = char
            index += 1
    return comments, diagnostics


__all__ = ["TypeScriptComment", "TypeScriptNormalModel"]
