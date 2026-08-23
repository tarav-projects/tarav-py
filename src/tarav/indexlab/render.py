# $kw: --from Kernel.Writing --from User.Touched
"""Read-only Kernel.Writing rendering of an IndexLab semantic projection."""

from __future__ import annotations

from .projection import ProjectedBlock, ProjectedLine, SemanticProjection
from .resolver import CONFLICTED, UNTYPED, line_type


BLOCK_SEPARATOR = "****"
#: Kernel.Writing stays compact, so the two non-answers render as marks rather than words.
TYPE_MARKS = {UNTYPED: "--", CONFLICTED: "??"}


class RenderError(ValueError):
    """A requested semantic projection cannot be rendered unambiguously."""


def render_kernel_writing(
    projection: SemanticProjection,
    *,
    block: str | None = None,
) -> str:
    """Render current semantic blocks as compact, citable Kernel.Writing Markdown."""

    blocks = (
        projection.blocks if block is None else (_resolve_block(projection, block),)
    )
    return "\n\n".join(_render_block(projection, item) for item in blocks)


def _resolve_block(
    projection: SemanticProjection,
    selector: str,
) -> ProjectedBlock:
    matches = tuple(
        block
        for block in projection.blocks
        if block.id == selector or block.name == selector
    )
    if not matches:
        raise RenderError(f"block selector {selector!r} does not resolve")
    if len(matches) > 1:
        raise RenderError(
            f"block selector {selector!r} resolves to {len(matches)} active blocks; "
            "use an exact Block.Id"
        )
    return matches[0]


def _render_block(
    projection: SemanticProjection,
    block: ProjectedBlock,
) -> str:
    lines = [BLOCK_SEPARATOR, f"## {block.name}"]
    if block.line_ids:
        lines.append("")
        lines.extend(
            _render_line(projection.line(line_id)) for line_id in block.line_ids
        )
    return "\n".join(lines)


def _render_line(line: ProjectedLine) -> str:
    code = line_type(line)
    return f"- [{TYPE_MARKS.get(code, code)}] {line.text} {line.label}"


__all__ = [
    "BLOCK_SEPARATOR",
    "TYPE_MARKS",
    "RenderError",
    "render_kernel_writing",
]
