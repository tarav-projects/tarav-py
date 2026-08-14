# $kw: ^python-normal-model --from Floor.Model --note [DF] minimal normalized Python facts required by current surface consumers ^c20260812-0u
"""Normalized Python source facts."""

from __future__ import annotations

from dataclasses import dataclass

from tarav.surfaces.model import SourceDiagnostic, SourceSpan


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


@dataclass(frozen=True)
class PythonNormalModel:
    """The Python facts currently required by downstream consumers."""

    text: str
    comments: tuple[PythonComment, ...]
    directives: tuple[PythonDirective, ...]
    diagnostics: tuple[SourceDiagnostic, ...]


__all__ = ["PythonComment", "PythonDirective", "PythonNormalModel"]
