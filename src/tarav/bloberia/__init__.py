# $kw: ^bloberia-public --from Agentos.Bloberia --note [DF] the public import surface for depot-scoped opaque-cargo storage ^c20260724-31u
"""Depot-scoped storage for opaque JSON records."""

from .core import (
    BloberiaDepot,
    BloberiaError,
    CorruptBloberiaDepotError,
    InvalidBloberiaInputError,
    PUBLIC_DEPOT_ROOT,
    TYPE_FILES,
)

__all__ = [
    "BloberiaDepot",
    "BloberiaError",
    "CorruptBloberiaDepotError",
    "InvalidBloberiaInputError",
    "PUBLIC_DEPOT_ROOT",
    "TYPE_FILES",
]
