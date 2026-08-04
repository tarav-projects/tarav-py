# $kw: --from Index.Line --from Touched.Support.Network --note [IMPL] canonical line identity excludes trailing support links and block attachment --supp ^c20260802-103u
from __future__ import annotations

from hashlib import sha256

from .parser import ANCHOR_RE, TYPE_BRACKET_RE


INDEX_LINE_CONTENT_SCHEMA = "agentos.index-line-content.v1"


def index_line_content_parts(source: str) -> tuple[str | None, str]:
    """Return the deterministic Line.Type and body, excluding support links."""

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


def canonical_index_line_content(source: str) -> str:
    """Version-local canonical tuple used to identify one Index line."""

    line_type, body = index_line_content_parts(source)
    return f"{line_type or ''}\0{body}"


def index_line_content_hash(source: str) -> str:
    canonical = canonical_index_line_content(source)
    digest = sha256(
        f"{INDEX_LINE_CONTENT_SCHEMA}\0{canonical}".encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"
