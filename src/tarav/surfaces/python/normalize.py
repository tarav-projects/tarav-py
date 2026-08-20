# $kw: ^python-normalizer --from Normalization.Pipeline --from Floor.Model --note [DF] tokenizer-backed production of the minimal Python normal model ^c20260812-0u
"""Normalize raw Python into a small native model."""

from __future__ import annotations

import ast
import io
import re
import tokenize

from tarav.surfaces.model import SourceDiagnostic, SourceSpan

from .model import PythonComment, PythonDirective, PythonElement, PythonNormalModel


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


def _element_span(node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> SourceSpan:
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


def normalize_python(text: str) -> PythonNormalModel:
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
    return PythonNormalModel(
        text=text,
        elements=elements,
        comments=tuple(comments),
        directives=tuple(directives),
        diagnostics=tuple(diagnostics),
    )


__all__ = ["PYTHON_EXTERNAL_DIRECTIVE_PATTERNS", "normalize_python"]
