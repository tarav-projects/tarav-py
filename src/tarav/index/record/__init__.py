# $kw: --from Index.Line.Record
"""The index entry and its store.

An `Index.Line` is more than a line: it is the object describing the index entry, carrying
both the line content and the description of how it indexes the `Touch.Authority.Surface`.
"""

from __future__ import annotations

from .identity import split_statement
from .model import (
    Equivalence,
    EquivalenceKind,
    Line,
    LineRecord,
    PlacementRef,
    SupportRef,
    new_line_id,
    new_trace_id,
)
from .store import (
    LABEL_SIGIL,
    IndexStore,
    RecordStoreError,
    is_label,
    normalize_label,
)

__all__ = [
    "LABEL_SIGIL",
    "Equivalence",
    "EquivalenceKind",
    "IndexStore",
    "Line",
    "LineRecord",
    "PlacementRef",
    "RecordStoreError",
    "SupportRef",
    "is_label",
    "new_line_id",
    "new_trace_id",
    "normalize_label",
    "split_statement",
]
