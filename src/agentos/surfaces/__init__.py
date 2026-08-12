# $kw: ^native-surfaces --from Floor.Model --from Normalization.Pipeline --note [DF] native source normalization independent from downstream consumers ^c20260812-0u
"""Small native source models and normalizers."""

from .model import SourceDiagnostic, SourceSpan

__all__ = ["SourceDiagnostic", "SourceSpan"]
