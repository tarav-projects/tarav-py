# $kw: ^skw-python-backend --from Skw.Backend --note [DF] Python host adapter providing tokenized comments and the code carrier floor model ^c20260811-66u
"""Python backend for the shared Skw code-surface engine."""

from __future__ import annotations

import io
import tokenize

from ._code_model import CodeSurfaceModel, SourceComment
from .model import parse_skw_code


class PythonCodeBackend:
    name = "python"
    suffixes = (".py", ".pyi")

    def model(self, text: str) -> CodeSurfaceModel:
        comments = []
        scanner_error = None
        try:
            tokens = tokenize.generate_tokens(io.StringIO(text).readline)
            for token in tokens:
                if token.type != tokenize.COMMENT:
                    continue
                comments.append(
                    SourceComment(
                        text=token.string,
                        start_line=token.start[0],
                        start_column=token.start[1],
                        end_line=token.end[0],
                        end_column=token.end[1],
                    )
                )
        except (IndentationError, SyntaxError, tokenize.TokenError) as exc:
            scanner_error = str(exc)
        return CodeSurfaceModel(
            annotations=parse_skw_code(
                text,
                machinery_lines=frozenset(
                    comment.start_line
                    for comment in comments
                    if comment.start_column == 0
                ),
            ),
            comments=tuple(comments),
            scanner_error=scanner_error,
        )
