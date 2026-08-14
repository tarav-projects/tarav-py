# $kw: ^skw-python-backend --from Skw.Backend --note [DF] Python host adapter providing tokenized comments and the code carrier floor model ^c20260811-66u
"""Python backend for the shared Skw code-surface engine."""

from __future__ import annotations

from tarav.surfaces.python import normalize_python

from ._code_model import CodeSurfaceModel
from .adapters.python import adapt_python_skw
from .model import parse_skw_model


class PythonCodeBackend:
    name = "python"
    suffixes = (".py", ".pyi")

    def model(self, text: str) -> CodeSurfaceModel:
        native = normalize_python(text)
        surface = adapt_python_skw(native)
        return CodeSurfaceModel(surface=surface, annotations=parse_skw_model(surface))
