# $kw: ^python-normalizer --from Normalization.Pipeline --from Floor.Model --note [DF] tokenizer-backed production of the minimal Python normal model ^c20260812-0u
"""Normalize raw Python into a small native model."""

from __future__ import annotations

import io
import re
import tokenize

from agentos.surfaces.model import SourceDiagnostic, SourceSpan

from .model import PythonComment, PythonDirective, PythonNormalModel


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
    return PythonNormalModel(
        text=text,
        comments=tuple(comments),
        directives=tuple(directives),
        diagnostics=tuple(diagnostics),
    )


__all__ = ["PYTHON_EXTERNAL_DIRECTIVE_PATTERNS", "normalize_python"]
