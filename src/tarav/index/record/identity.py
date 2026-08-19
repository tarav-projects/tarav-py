# $kw: --from Touched.Index.Record --note [CT] canonical statement parsing is unchanged, so the existing Chatlas2 supplies it
"""The tarav1 parsing boundary.

Splitting a kernel line into its canonical `(Line.Type, body)` projection already exists in
tarav1 and is unchanged by the new model, so it is re-exported rather than rewritten. This
module exists to name that dependency in one place — the surfaces reader calls it, and nothing
else in the index needs to know where it came from.

It used to carry hashing and rendering helpers too. Nothing consumed them: identity is a
random id that survives rewording, so content hashes decide nothing, and agents write kernel
lines by editing markdown rather than through a renderer.
"""

from __future__ import annotations

from tarav.index_model.identity import index_line_statement_parts


def split_statement(source: str) -> tuple[str | None, str]:
    """Split a kernel line into ``(line_type, body)``, dropping trailing anchors."""

    return index_line_statement_parts(source)


__all__ = ["split_statement"]
