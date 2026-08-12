# $kw: ^skw-surface-adapters --from Skw.Backend --from Normalization.Pipeline --note [DF] native-model adapters for the shared Skillware carrier model ^c20260812-0u
"""Adapters from native surface models to the common Skillware model."""

from .markdown import adapt_markdown_skw
from .python import adapt_python_skw

__all__ = ["adapt_markdown_skw", "adapt_python_skw"]
