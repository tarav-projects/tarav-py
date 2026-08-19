# $kw: --from Index.Line.Anchor --note [IMPL] canonical attachment identity is the current Line.Type + body + Anchor.Id triplet --supp ^c20260809-170u
from __future__ import annotations

from hashlib import sha256
import json

from .parser import ANCHOR_RE, TYPE_BRACKET_RE


INDEX_LINE_BODY_SCHEMA = "agentos.index-line-body.v1"
INDEX_LINE_STATEMENT_SCHEMA = "agentos.index-line-statement.v1"
INDEX_LINE_ANCHOR_TRIPLET_SCHEMA = "agentos.index-line-anchor-triplet.v1"


def index_line_statement_parts(source: str) -> tuple[str | None, str]:
    """Return Line.Type and normalized body, excluding trailing anchors."""

    tokens = source.rstrip().split()
    while tokens and ANCHOR_RE.fullmatch(tokens[-1]):
        tokens.pop()
    unlinked = " ".join(tokens)
    typed = TYPE_BRACKET_RE.match(unlinked)
    if typed is not None:
        line_type = typed.group("act")
        body = unlinked[typed.end() :]
    else:
        line_type = None
        body = unlinked[2:] if unlinked.startswith("- ") else unlinked
    return line_type, " ".join(body.split())


def canonical_index_line_body(source: str) -> str:
    """Canonical Index line wording, excluding Line.Type and anchors."""

    return index_line_statement_parts(source)[1]


def canonical_index_line_statement(source: str) -> str:
    """Length-safe `(Line.Type, body)` key for pre-anchor comparisons."""

    line_type, body = index_line_statement_parts(source)
    return json.dumps(
        [line_type or "", body], ensure_ascii=False, separators=(",", ":")
    )


def index_line_body_hash(source: str) -> str:
    digest = sha256(
        f"{INDEX_LINE_BODY_SCHEMA}\0{canonical_index_line_body(source)}".encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def index_line_statement_hash(source: str) -> str:
    """Hash the canonical ``Line.Type + body`` projection."""

    digest = sha256(
        f"{INDEX_LINE_STATEMENT_SCHEMA}\0{canonical_index_line_statement(source)}".encode(
            "utf-8"
        )
    ).hexdigest()
    return f"sha256:{digest}"


def canonical_index_line_anchor_triplet(source: str, anchor: str) -> str:
    """Canonical Line.Type + body + Anchor.Id attachment assertion."""

    normalized_anchor = anchor.removeprefix("^")
    if not normalized_anchor or ANCHOR_RE.fullmatch(f"^{normalized_anchor}") is None:
        raise ValueError(f"invalid Index.Line.Anchor id: {anchor!r}")
    line_type, body = index_line_statement_parts(source)
    return json.dumps(
        [line_type or "", body, normalized_anchor],
        ensure_ascii=False,
        separators=(",", ":"),
    )


LINE_MANIFEST_SCHEMA = "agentos.index-line-manifest.v3"
"""Schema id of the index line manifest.

It lives in the model kernel because both the index application that builds a
manifest and the chatlas reader that materializes one must agree on it, and the
kernel is the only zone both may import.
"""


def index_line_anchor_triplet_hash(source: str, anchor: str) -> str:
    canonical = canonical_index_line_anchor_triplet(source, anchor)
    digest = sha256(
        f"{INDEX_LINE_ANCHOR_TRIPLET_SCHEMA}\0{canonical}".encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"
