# $kw: --from Index.Line --note [DC] what survives here is the grammar and identity of one Index line's written form; the Index itself is a collection of Index.Records and this package no longer models it
"""The written form of an `Index.Line`: its label grammar and its identity hashes.

An Index line still has a syntax — a `Line.Type` code, a body, and a trailing anchor —
wherever one is written or cited, and Chatlas dossiers assert identity over exactly that
triplet. That grammar is what lives here.

It does not provide an Index or a record store. It only preserves the written-form
grammar still consumed by retained Chatlas and POI surfaces.
"""

from .identity import (
    ANCHOR_RE,
    INDEX_LINE_ANCHOR_TRIPLET_SCHEMA,
    INDEX_LINE_BODY_SCHEMA,
    INDEX_LINE_STATEMENT_SCHEMA,
    TYPE_BRACKET_RE,
    canonical_index_line_anchor_triplet,
    canonical_index_line_body,
    canonical_index_line_statement,
    index_line_anchor_triplet_hash,
    index_line_body_hash,
    index_line_statement_hash,
    index_line_statement_parts,
    normalize_anchor,
)
from .label import (
    CITATION_BODY,
    CITATION_RE,
    is_citation,
    parse_citation,
    split_trailing_address,
    strip_trailing_addresses,
)

__all__ = [
    "ANCHOR_RE",
    "CITATION_BODY",
    "CITATION_RE",
    "INDEX_LINE_ANCHOR_TRIPLET_SCHEMA",
    "INDEX_LINE_BODY_SCHEMA",
    "INDEX_LINE_STATEMENT_SCHEMA",
    "TYPE_BRACKET_RE",
    "canonical_index_line_anchor_triplet",
    "canonical_index_line_body",
    "canonical_index_line_statement",
    "index_line_anchor_triplet_hash",
    "index_line_body_hash",
    "index_line_statement_hash",
    "index_line_statement_parts",
    "is_citation",
    "normalize_anchor",
    "parse_citation",
    "split_trailing_address",
    "strip_trailing_addresses",
]
