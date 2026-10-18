# $kw: ^python-normal-model --from Floor.Model --note [DF] minimal normalized Python facts required by current surface consumers ^c20260812-0u
# --note [CT] `PythonNormalModel` stays independent of Skillware and exposes only the minimal Python structure and source facts required by consumers. ^c20260820-0u
"""Normalized Python source facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import ast
import io
import re
import tokenize

import json
from pydantic import ConfigDict, TypeAdapter, field_validator
from tarav.l0.kernel import TaravObject, TaravClass, TypeShip, entity
from tarav.l1.surfaces.workflow import SURFACES_WORKFLOW_SHIP

from tarav.l1.surfaces.model import SourceDiagnostic, SourceSpan
from tarav.l0.kernel import LoadedRecord


@dataclass(frozen=True)
class PythonElement:
    """One neutral Python declaration exposed to downstream consumers."""

    kind: str
    name: str
    qualified_name: str
    span: SourceSpan


@dataclass(frozen=True)
class PythonDirective:
    """A comment whose complete syntax belongs to a recognized external tool."""

    kind: str
    text: str
    span: SourceSpan


@dataclass(frozen=True)
class PythonComment:
    """A tokenizer-confirmed Python comment."""

    text: str
    span: SourceSpan
    directive: PythonDirective | None = None


@dataclass
class PythonNormalModel(TaravObject):
    """The Python facts currently required by downstream consumers."""

    text: str
    elements: tuple[PythonElement, ...]
    comments: tuple[PythonComment, ...]
    directives: tuple[PythonDirective, ...]
    diagnostics: tuple[SourceDiagnostic, ...]

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("a1ddc991-2f35-4e88-bb49-7fcae653bc64"),
            name="Tarav.Surfaces.PythonNormalModel",
            workflow=SURFACES_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: str
        text: str
        elements: tuple[PythonElement, ...]
        comments: tuple[PythonComment, ...]
        directives: tuple[PythonDirective, ...]
        diagnostics: tuple[SourceDiagnostic, ...]

        @field_validator(
            "elements", "comments", "directives", "diagnostics", mode="before"
        )
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
    def _from_record(cls, loaded: LoadedRecord):
        return cls(
            text=loaded.data.text,
            elements=loaded.data.elements,
            comments=loaded.data.comments,
            directives=loaded.data.directives,
            diagnostics=loaded.data.diagnostics,
        )

    class Records(TaravObject.Records):
        def record_example(self):
            cls = self._owner
            return cls.from_text("").records.to_record()



__all__ = [
    "PythonComment",
    "PythonDirective",
    "PythonElement",
    "PythonNormalModel",
]


PYTHON_EXTERNAL_DIRECTIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "typing-ignore",
        re.compile(r"#\s*type:\s*ignore(?:\[[A-Za-z0-9_, -]+\])?\s*$"),
    ),
    (
        "lint-noqa",
        re.compile(r"#\s*noqa(?:\s*:\s*[A-Z][A-Z0-9]*(?:\s*,\s*[A-Z][A-Z0-9]*)*)?\s*$"),
    ),
    (
        "coverage-pragma",
        re.compile(r"#\s*pragma:\s*no\s+(?:cover|branch)(?:\s+-\s+\S.*)?\s*$"),
    ),
    (
        "formatter-control",
        re.compile(r"#\s*fmt:\s*(?:on|off|skip)\s*$"),
    ),
    (
        "import-sorter-control",
        re.compile(
            r"#\s*isort:\s*(?:on|off|skip|skip_file|split|dont-add-imports)\s*$"
        ),
    ),
    (
        "pylint-control",
        re.compile(r"#\s*pylint:\s*(?:disable|enable)=[a-z0-9_, -]+\s*$"),
    ),
    (
        "pyright-control",
        re.compile(
            r"#\s*pyright:\s*(?:ignore(?:\[[A-Za-z0-9_, -]+\])?|strict|basic|standard|off)\s*$"
        ),
    ),
    (
        "mypy-control",
        re.compile(r"#\s*mypy:\s*[a-z][a-z0-9_-]*(?:\s*=\s*[^#]+)?\s*$"),
    ),
    (
        "ruff-control",
        re.compile(
            r"#\s*ruff:\s*noqa(?:\s*:\s*[A-Z][A-Z0-9]*(?:\s*,\s*[A-Z][A-Z0-9]*)*)?\s*$"
        ),
    ),
)


def _directive(text: str, span: SourceSpan) -> PythonDirective | None:
    for kind, pattern in PYTHON_EXTERNAL_DIRECTIVE_PATTERNS:
        if pattern.fullmatch(text) is not None:
            return PythonDirective(kind=kind, text=text, span=span)
    return None


def _element_span(
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
) -> SourceSpan:
    first = min(node.decorator_list, key=lambda item: item.lineno, default=node)
    return SourceSpan(
        start_line=first.lineno,
        start_column=first.col_offset,
        end_line=node.end_lineno or node.lineno,
        end_column=node.end_col_offset or node.col_offset,
    )


class _ElementCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.elements: list[PythonElement] = []
        self._parents: list[str] = []

    def _visit_declaration(
        self,
        node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
        kind: str,
    ) -> None:
        qualified_name = ".".join((*self._parents, node.name))
        self.elements.append(
            PythonElement(
                kind=kind,
                name=node.name,
                qualified_name=qualified_name,
                span=_element_span(node),
            )
        )
        self._parents.append(node.name)
        self.generic_visit(node)
        self._parents.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_declaration(node, "class")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_declaration(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_declaration(node, "async-function")


def _elements(text: str) -> tuple[PythonElement, ...]:
    collector = _ElementCollector()
    collector.visit(ast.parse(text))
    return tuple(collector.elements)


def _parse(text: str, *, model_type: type[PythonNormalModel]) -> PythonNormalModel:
    """Tokenize comments and classify only complete recognized directives."""

    comments: list[PythonComment] = []
    directives: list[PythonDirective] = []
    diagnostics: list[SourceDiagnostic] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type != tokenize.COMMENT:
                continue
            span = SourceSpan(
                start_line=token.start[0],
                start_column=token.start[1],
                end_line=token.end[0],
                end_column=token.end[1],
            )
            directive = _directive(token.string, span)
            comments.append(
                PythonComment(text=token.string, span=span, directive=directive)
            )
            if directive is not None:
                directives.append(directive)
    except (IndentationError, SyntaxError, tokenize.TokenError) as exc:
        diagnostics.append(SourceDiagnostic(message=str(exc)))
    elements: tuple[PythonElement, ...] = ()
    if not diagnostics:
        try:
            elements = _elements(text)
        except SyntaxError as exc:
            diagnostics.append(
                SourceDiagnostic(
                    message=str(exc),
                    span=(
                        SourceSpan(
                            start_line=exc.lineno,
                            start_column=max((exc.offset or 1) - 1, 0),
                            end_line=exc.end_lineno or exc.lineno,
                            end_column=max((exc.end_offset or exc.offset or 1) - 1, 0),
                        )
                        if exc.lineno is not None
                        else None
                    ),
                )
            )
    return model_type(
        text=text,
        elements=elements,
        comments=tuple(comments),
        directives=tuple(directives),
        diagnostics=tuple(diagnostics),
    )
