from __future__ import annotations

import re

from agentos.index.model import BlockHeading, IndexDocument, KernelLine

from ._linter_models import (
    CoverageItem,
    LinterCheck,
    LinterFinding,
    LinterState,
    _ensure_parsed_documents,
    bind_floor_check,
    parsed_linter_kernel_lines,
)
from ._linter_structure import _needs_valid_surface


LINE_TYPE_SYNTAX = "Index.Linter/Line.Type.Syntax"
LINE_TYPE_UNKNOWN = "Index.Linter/Line.Type.UnknownCode"
LINE_TYPE_GR_MISSING_ANCHOR = "Index.Linter/Line.Type.GR.MissingAnchor"
SOURCE_AXIS_PLACEMENT = "Index.Linter/Source.Axis.Placement"
CHECK_LINE_TYPES = "Index.Linter/Line.Types"
ANCHOR_LEGACY_SIGIL = "Index.Linter/Anchor.LegacySigil"
CHECK_ANCHOR_LEGACY_SIGIL = "Index.Linter/Anchor.LegacySigil"
ANCHOR_UNPREFIXED = "Index.Linter/Anchor.Unprefixed"
CHECK_ANCHOR_UNPREFIXED = "Index.Linter/Anchor.Unprefixed"
TYPE_STATEMENT_LEGACY_SIGIL = "Index.Linter/TypeStatement.LegacySigil"
CHECK_TYPE_STATEMENT_LEGACY_SIGIL = "Index.Linter/TypeStatement.LegacySigil"
LINE_UNLINKED = "Index.Linter/Line.Unlinked"
CHECK_LINE_UNLINKED = "Index.Linter/Line.Unlinked"
BLOCK_UNGROUNDED = "Index.Linter/Block.Ungrounded"
CHECK_BLOCK_UNGROUNDED = "Index.Linter/Block.Ungrounded"
REVIEWED_CITE_CLOSURE = "Index.Linter/Reviewed.Cite.Closure"
CHECK_REVIEWED_CITE_CLOSURE = "Index.Linter/Reviewed.Cite.Closure"

# act codes: keep aligned with `Line.Type.Vocabulary` in the agentos-pkg index
_LINE_TYPE_ACT_CODES = ("DF", "DC", "CT", "RJ", "PR", "FR", "EX", "GR")

_TYPED_LINE_CANDIDATE_RE = re.compile(r"^- \[")
_LEGACY_ANCHOR_SIGIL_RE = re.compile(r"@(?P<anchor>[a-z]?\d{8}-\d+[a-z]?)\b")
_UNPREFIXED_ANCHOR_RE = re.compile(r"^\d{8}-\d+[a-z]?$")
_LEGACY_TYPE_STATEMENT_RE = re.compile(
    r"(?P<legacy>"
    r"[A-Z][A-Za-z0-9]*(?:\.[A-Z][A-Za-z0-9]*)+"
    r"(?::[A-Z][A-Za-z0-9]*(?:\.[A-Z][A-Za-z0-9]*)*)+"
    r")"
)


def _check_line_types(
    state: LinterState,
    documents: tuple[IndexDocument, ...],
) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    for document, line in parsed_linter_kernel_lines(state, documents):
        if not _TYPED_LINE_CANDIDATE_RE.match(line.src):
            continue
        rel = state.rel_path(line.path) if line.path else "."
        code = line.parsed.get("act")
        if code is None:
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=LINE_TYPE_SYNTAX,
                    path=rel,
                    line=line.start_line,
                    message="Typed-line bracket does not match '- [XX] ' or '- [AS:XX] '.",
                )
            )
            continue
        if code not in _LINE_TYPE_ACT_CODES:
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=LINE_TYPE_UNKNOWN,
                    path=rel,
                    line=line.start_line,
                    message=f"Unknown Line.Type act code: {code}.",
                    details={"code": code},
                )
            )
        if line.parsed.get("source") and document.surface_kind != "agendix":
            findings.append(
                LinterFinding(
                    severity="error",
                    code=SOURCE_AXIS_PLACEMENT,
                    path=rel,
                    line=line.start_line,
                    message="AS: source-axis marker outside agendix/ — the index proper is user-turn-grounded.",
                )
            )
        if code == "GR" and not any(span.kind == "anchor" for span in line.spans):
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=LINE_TYPE_GR_MISSING_ANCHOR,
                    path=rel,
                    line=line.start_line,
                    message="[GR] grounding line has no trailing anchor token.",
                )
            )
    return findings


def _check_legacy_anchor_sigil(
    state: LinterState,
    documents: tuple[IndexDocument, ...],
) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    for document in documents:
        for node in document.nodes:
            for match in _LEGACY_ANCHOR_SIGIL_RE.finditer(node.src):
                anchor = match.group("anchor")
                findings.append(
                    LinterFinding(
                        severity="warning",
                        code=ANCHOR_LEGACY_SIGIL,
                        path=state.rel_path(node.path) if node.path else ".",
                        line=node.start_line,
                        message="Legacy Anchory anchor sigil; use `^` instead of `@`.",
                        details={
                            "anchor": anchor,
                            "replacement": f"^{anchor}",
                        },
                    )
                )
    return findings


def _check_unprefixed_anchor(
    state: LinterState,
    documents: tuple[IndexDocument, ...],
) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    for _document, line in parsed_linter_kernel_lines(state, documents):
        for span in line.spans:
            if span.kind != "anchor":
                continue
            anchor = str(span.parsed["anchor"])
            if not _UNPREFIXED_ANCHOR_RE.fullmatch(anchor):
                continue
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=ANCHOR_UNPREFIXED,
                    path=state.rel_path(line.path) if line.path else ".",
                    line=line.start_line,
                    message=(
                        "Bare anchor citation; cite the composed key with its "
                        "namespace prefix."
                    ),
                    details={"anchor": anchor},
                )
            )
    return findings


def _check_legacy_type_statement_sigil(
    state: LinterState,
    documents: tuple[IndexDocument, ...],
) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    for document in documents:
        for node in document.nodes:
            for match in _LEGACY_TYPE_STATEMENT_RE.finditer(node.src):
                legacy = match.group(0)
                findings.append(
                    LinterFinding(
                        severity="warning",
                        code=TYPE_STATEMENT_LEGACY_SIGIL,
                        path=state.rel_path(node.path) if node.path else ".",
                        line=node.start_line,
                        message="Legacy type-statement sigil; use `::` instead of `:`.",
                        details={
                            "legacy": legacy,
                            "replacement": legacy.replace(":", "::"),
                        },
                    )
                )
    return findings


def _check_line_unlinked(
    state: LinterState,
    documents: tuple[IndexDocument, ...],
) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    for document, line in parsed_linter_kernel_lines(state, documents):
        has_anchor = any(span.kind == "anchor" for span in line.spans)
        if "line" in state.config.coverage:
            state.coverage_items.setdefault("line", []).append(
                CoverageItem(
                    path=state.rel_path(line.path) if line.path else ".",
                    covered=has_anchor,
                )
            )
        if has_anchor:
            continue
        findings.append(
            LinterFinding(
                severity="warning",
                code=LINE_UNLINKED,
                path=state.rel_path(line.path) if line.path else ".",
                line=line.start_line,
                message=(
                    "Live index line has no Support.Reference; it remains live "
                    "under Index.Presumption while grounding is unresolved."
                ),
                details={
                    "surface_kind": document.surface_kind,
                    "standing": "index-presumption",
                },
            )
        )
    return findings


def _check_block_ungrounded(
    state: LinterState,
    documents: tuple[IndexDocument, ...],
) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    for document in documents:
        lines_by_block: dict[str, list[KernelLine]] = {}
        for node in document.nodes:
            if isinstance(node, KernelLine):
                block = str(node.parsed.get("block_path", ""))
                lines_by_block.setdefault(block, []).append(node)
        for block in (
            node for node in document.nodes if isinstance(node, BlockHeading)
        ):
            block_path = str(block.parsed.get("path", "")).strip()
            if not block.parsed.get("valid") or block.parsed.get("segments") != []:
                continue
            rel_path = state.rel_path(block.path) if block.path else "."
            lines = lines_by_block.get(block_path, [])
            ungrounded_lines = sum(
                1
                for line in lines
                if (
                    (standing := state.line_support_standing(line)) is None
                    or not standing.grounded
                )
            )
            grounded = ungrounded_lines == 0
            if "block" in state.config.coverage:
                state.coverage_items.setdefault("block", []).append(
                    CoverageItem(path=rel_path, covered=grounded)
                )
            if grounded or "block" not in state.config.coverage:
                continue
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=BLOCK_UNGROUNDED,
                    path=rel_path,
                    line=block.start_line,
                    message=(
                        "Index concept block has kernel lines without a resolvable "
                        "nonempty support set."
                    ),
                    details={
                        "block_path": block_path,
                        "ungrounded_lines": ungrounded_lines,
                    },
                )
            )
    return findings


def _agendix_block_paths(state: LinterState) -> set[str]:
    """The `Block.Path`s of every real agendix candidate block in the depot.

    A reviewed cite violates the closure only when it addresses one of these — a
    specific agendix block, i.e. an actual cite of unreviewed content. This
    resolves against real blocks, so a definition that merely *names* the
    agendix (a placeholder `Concept.X/Agendix/...`, or a bare `agendix/…md` file
    mention) points at no real block and does not violate."""
    blocks: set[str] = set()
    for document in state.parsed_documents:
        if document.surface_kind != "agendix":
            continue
        for node in document.nodes:
            if isinstance(node, BlockHeading):
                path = str(node.parsed.get("path", "")).strip()
                if path:
                    blocks.add(path)
    return blocks


def _check_reviewed_cite_closure(
    state: LinterState,
    documents: tuple[IndexDocument, ...],
) -> list[LinterFinding]:
    """`Reviewed.Cite.Closure`: a reviewed surface may not cite the agendix.

    Surface-level v1: the agendix is the sole unreviewed surface, so a reviewed
    line (`chapter`/`appendix`) that addresses a real agendix candidate block by
    its `Block.Path` is the forbidden reviewed->unreviewed edge. Directional
    (agendix->reviewed stays legal) and an error — not blessable: the fix is to
    promote the target into the reviewed index, or drop the cite. Naming the
    agendix surface (a bare `agendix/…md` file mention, as its definition does)
    is not a content cite and does not violate.
    """
    findings: list[LinterFinding] = []
    _ensure_parsed_documents(state)
    agendix_blocks = _agendix_block_paths(state)
    if not agendix_blocks:
        return findings
    for document, line in parsed_linter_kernel_lines(state, documents):
        for span in line.spans:
            if span.kind != "file_mention":
                continue
            value = str(span.parsed.get("value", ""))
            if value not in agendix_blocks:
                continue  # not a real agendix block cite (naming / placeholder)
            findings.append(
                LinterFinding(
                    severity="error",
                    code=REVIEWED_CITE_CLOSURE,
                    path=state.rel_path(line.path) if line.path else ".",
                    line=line.start_line,
                    message=(
                        f"Reviewed surface cites an agendix target `{value}` — "
                        "Reviewed.Cite.Closure forbids a reviewed line citing the "
                        "unreviewed agendix; promote the target into the reviewed "
                        "index, or drop the cite."
                    ),
                    details={"target": value, "surface_kind": document.surface_kind},
                )
            )
    return findings


PARSER_CHECKS: tuple[LinterCheck, ...] = (
    bind_floor_check(
        code=CHECK_LINE_TYPES,
        title="Line.Type syntax and source axis",
        gate=_needs_valid_surface,
        run=_check_line_types,
        surface_kinds=frozenset({"chapter", "appendix", "agendix"}),
    ),
    bind_floor_check(
        code=CHECK_ANCHOR_LEGACY_SIGIL,
        title="Legacy anchor sigils",
        gate=_needs_valid_surface,
        run=_check_legacy_anchor_sigil,
        surface_kinds=frozenset({"chapter", "appendix", "agendix"}),
    ),
    bind_floor_check(
        code=CHECK_ANCHOR_UNPREFIXED,
        title="Unprefixed anchor citations",
        gate=_needs_valid_surface,
        run=_check_unprefixed_anchor,
        surface_kinds=frozenset({"chapter", "appendix", "agendix"}),
    ),
    bind_floor_check(
        code=CHECK_TYPE_STATEMENT_LEGACY_SIGIL,
        title="Legacy type-statement sigils",
        gate=_needs_valid_surface,
        run=_check_legacy_type_statement_sigil,
        surface_kinds=frozenset({"router", "chapter", "appendix", "agendix"}),
    ),
    bind_floor_check(
        code=CHECK_LINE_UNLINKED,
        title="Live lines missing support references",
        gate=_needs_valid_surface,
        run=_check_line_unlinked,
        surface_kinds=frozenset({"chapter", "appendix", "agendix"}),
    ),
    bind_floor_check(
        code=CHECK_BLOCK_UNGROUNDED,
        title="Ungrounded concept blocks",
        gate=_needs_valid_surface,
        run=_check_block_ungrounded,
        surface_kinds=frozenset({"chapter"}),
    ),
    bind_floor_check(
        code=CHECK_REVIEWED_CITE_CLOSURE,
        title="Reviewed surfaces do not cite the agendix",
        gate=_needs_valid_surface,
        run=_check_reviewed_cite_closure,
        surface_kinds=frozenset({"chapter", "appendix"}),
    ),
)
