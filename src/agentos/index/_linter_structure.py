from __future__ import annotations

import re
from pathlib import Path

from agentos._core.scan import DEFAULT_SCAN_EXCLUDES
from agentos.index.model import (
    BlockHeading,
    Diagnostic,
    RouterEntry as ModelRouterEntry,
)
from agentos.mdblocks.core import (
    MarkdownScanConfig,
    lint_markdown_blocks,
    scan_markdown_blocks,
)

from ._linter_models import (
    CheckStatus,
    ConceptBlock,
    GateResult,
    LinterCheck,
    LinterCheckBinding,
    LinterFinding,
    LinterState,
    RouterEntry,
    SurfaceKind,
    SurfacePath,
    _ensure_parsed_documents,
    _surface_depot_root,
    allowed,
    blocked,
    path_is_or_contains,
)


_CONCEPT_SEGMENT = r"[A-Z][A-Za-z0-9]*"
_DOTTED_CONCEPT = rf"{_CONCEPT_SEGMENT}(?:\.{_CONCEPT_SEGMENT})+"
_CONCEPT_PARAM = r"(?:[A-Za-z][\w\-.]*|<[A-Z][A-Za-z0-9]*>)"
_TYPE_SIGIL = r"::?"
_CONCEPT_REF = rf"{_DOTTED_CONCEPT}(?:{_TYPE_SIGIL}{_CONCEPT_PARAM})*"
_BLOCK_PATH_SEGMENT = rf"(?:{_CONCEPT_REF}|{_CONCEPT_SEGMENT})"
BLOCK_PATH_RE = re.compile(rf"^{_CONCEPT_REF}(?:/{_BLOCK_PATH_SEGMENT})*$")
APPENDIX_FILENAME_RE = re.compile(
    rf"^(?P<concept>{_CONCEPT_REF})-appendix(?:-(?P<page>[2-9][0-9]*))?\.md$"
)
INDEX_FILENAME_RE = re.compile(
    r"^(?P<number>[1-9][0-9]{2})-(?P<chapter>[a-z0-9][a-z0-9-]*)\.md$"
)

CONFIG_NO_SURFACES = "Index.Linter/Config.NoSurfaces"
SURFACE_INVALID = "Index.Linter/Surface.Invalid"
SURFACE_MISSING_BY_KIND: dict[SurfaceKind, str] = {
    "index": "Index.Linter/Surface.IndexMissing",
    "appendix": "Index.Linter/Surface.AppendixMissing",
    "agendix": "Index.Linter/Surface.AgendixMissing",
}
SURFACE_NOT_MARKDOWN_BY_KIND: dict[SurfaceKind, str] = {
    "index": "Index.Linter/Surface.IndexNotMarkdown",
    "appendix": "Index.Linter/Surface.AppendixNotMarkdown",
    "agendix": "Index.Linter/Surface.AgendixNotMarkdown",
}
SURFACE_INVALID_BY_KIND: dict[SurfaceKind, str] = {
    "index": "Index.Linter/Surface.IndexInvalid",
    "appendix": "Index.Linter/Surface.AppendixInvalid",
    "agendix": "Index.Linter/Surface.AgendixInvalid",
}
FILES_NONE = "Index.Linter/Files.None"
MDBLOCKS_SYNTAX = "Index.Linter/Mdblocks.Syntax"
BLOCK_NO_HEADINGS = "Index.Linter/Block.NoHeadings"
BLOCK_UNCLOSED_CODE_FENCE = "Index.Linter/Block.UnclosedCodeFence"
BLOCK_SEPARATOR_OUTSIDE_SEMANTICS = "Index.Linter/Block.SeparatorOutsideSemantics"
BLOCK_EMPTY_HEADING = "Index.Linter/Block.EmptyHeading"
BLOCK_TOO_LONG = "Index.Linter/Block.TooLong"
BLOCK_DUPLICATE_HEADING = "Index.Linter/Block.DuplicateHeading"
BLOCK_UNANCHORED_SECTION = "Index.Linter/Block.UnanchoredSection"
ROUTER_MISSING = "Index.Linter/Router.Missing"
ROUTER_LEGACY_NAME = "Index.Linter/Router.LegacyName"
ROUTER_EMPTY = "Index.Linter/Router.Empty"
INDEX_INVALID_FILENAME = "Index.Linter/Index.InvalidFilename"
CONCEPT_INVENTORY = "Index.Linter/Concept.Inventory"
CONCEPT_INVALID_HEADING = "Index.Linter/Concept.InvalidHeading"
CONCEPT_INVENTORY_EMPTY = "Index.Linter/Concept.InventoryEmpty"
CONCEPT_DUPLICATE = "Index.Linter/Concept.Duplicate"
APPENDIX_INVALID_FILENAME = "Index.Linter/Appendix.InvalidFilename"
APPENDIX_ORPHAN = "Index.Linter/Appendix.Orphan"
APPENDIX_ROUTE_ANNOTATION_MISSING = "Index.Linter/Appendix.RouteAnnotationMissing"
APPENDIX_ROUTE_ANNOTATION_STALE = "Index.Linter/Appendix.RouteAnnotationStale"
APPENDIX_PAGE_GAP = "Index.Linter/Appendix.PageGap"
ROUTER_INVALID_CONCEPT = "Index.Linter/Router.InvalidConcept"
ROUTER_ENTRIES_EMPTY = "Index.Linter/Router.EntriesEmpty"
ROUTER_MISSING_ENTRY = "Index.Linter/Router.MissingEntry"
ROUTER_MISSING_FILE = "Index.Linter/Router.MissingFile"
ROUTER_UNKNOWN_CONCEPT = "Index.Linter/Router.UnknownConcept"
ROUTER_WRONG_FILE = "Index.Linter/Router.WrongFile"

CHECK_CONFIG_SURFACES = "Index.Linter/Check.ConfigSurfaces"
CHECK_DISCOVER_FILES = "Index.Linter/Check.DiscoverFiles"
CHECK_MDBLOCKS_SYNTAX = "Index.Linter/Check.MdblocksSyntax"
CHECK_BLOCK_SECTIONS = "Index.Linter/Check.BlockSections"
CHECK_ROUTER_PRESENCE = "Index.Linter/Check.RouterPresence"
CHECK_INDEX_FILENAMES = "Index.Linter/Check.IndexFilenames"
CHECK_CONCEPT_INVENTORY = "Index.Linter/Check.ConceptInventory"
CHECK_CONCEPT_DUPLICATES = "Index.Linter/Check.ConceptDuplicates"
CHECK_APPENDIX_FILENAMES = "Index.Linter/Check.AppendixFilenames"
CHECK_APPENDIX_ORPHANS = "Index.Linter/Check.AppendixOrphans"
CHECK_ROUTER_ENTRIES = "Index.Linter/Check.RouterEntries"
CHECK_ROUTER_COVERAGE = "Index.Linter/Check.RouterCoverage"
CHECK_ROUTER_TARGETS = "Index.Linter/Check.RouterTargets"
CHECK_APPENDIX_ROUTE_ANNOTATIONS = "Index.Linter/Check.AppendixRouteAnnotations"

CHECK_DEPOT_DEPENDENCIES = "Index.Linter/Check.DepotDependencies"
DEPOT_DEP_UNRESOLVED = "Index.Linter/DepotDependency.Unresolved"
DEPOT_COLLISION = "Index.Linter/DepotDependency.Collision"
CHECK_DANGLING_MENTION = "Index.Linter/Check.DanglingMention"
DEPOT_DANGLING_MENTION = "Index.Linter/DepotDependency.DanglingMention"

MDBLOCKS_CODE_MAP = {
    "no_headings": BLOCK_NO_HEADINGS,
    "unclosed_code_fence": BLOCK_UNCLOSED_CODE_FENCE,
    "separator_outside_block_semantics": BLOCK_SEPARATOR_OUTSIDE_SEMANTICS,
    "empty_heading_title": BLOCK_EMPTY_HEADING,
    "block_too_long": BLOCK_TOO_LONG,
    "duplicate_heading_title_same_level": BLOCK_DUPLICATE_HEADING,
}
MDBLOCKS_BLOCKING_CODES = (
    MDBLOCKS_SYNTAX,
    BLOCK_UNCLOSED_CODE_FENCE,
    BLOCK_SEPARATOR_OUTSIDE_SEMANTICS,
    BLOCK_EMPTY_HEADING,
    BLOCK_TOO_LONG,
)


def _always(_state: LinterState) -> GateResult:
    return allowed()


def _needs_valid_surface(state: LinterState) -> GateResult:
    if state.has_error(CONFIG_NO_SURFACES):
        return blocked("no surfaces were configured", CONFIG_NO_SURFACES)
    if not any(surface.valid for surface in state.surfaces):
        return blocked("no configured surfaces are valid", SURFACE_INVALID)
    return allowed()


def _needs_discovered_files(state: LinterState) -> GateResult:
    if state.has_error(CONFIG_NO_SURFACES):
        return blocked("no surfaces were configured", CONFIG_NO_SURFACES)
    if not any(state.files_by_kind.values()):
        return blocked("no markdown files were discovered", FILES_NONE)
    return allowed()


def _needs_index_surface(state: LinterState) -> GateResult:
    if not state.has_valid_surface("index"):
        return blocked(
            "no valid index surface is configured", SURFACE_MISSING_BY_KIND["index"]
        )
    return allowed()


def _check_depot_dependencies(state: LinterState) -> list[LinterFinding]:
    """`Index.Depot.Dependency` findings: unresolved declared deps + collisions.

    Only the precise, adoption-gated pieces are wired live: a depot that
    declares no dependencies produces nothing here (guards depots that have not
    adopted the system from noise). The directed dangling-mention check stays
    available (`drift.index_dangling_mentions`) but not CLI-wired, pending the
    resolver-gap work documented on Impl.Req 700/701.
    """
    from agentos.index.depot_deps import (
        declared_dependency_names,
        resolve_dependency_depots,
    )
    from agentos.index.drift import index_depot_collisions

    findings: list[LinterFinding] = []
    for depot in state.config.depot_paths:
        if not declared_dependency_names(depot):
            continue
        rel = state.rel_path(depot)
        _, unresolved = resolve_dependency_depots(depot)
        for name in unresolved:
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=DEPOT_DEP_UNRESOLVED,
                    path=rel,
                    message=(
                        f"declared dependency depot `{name}` does not resolve in the "
                        "global Wayfinder registry."
                    ),
                    details={"depot": name},
                )
            )
        for collision in index_depot_collisions(depot):
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=DEPOT_COLLISION,
                    path=rel,
                    message=collision.detail,
                    details={"concept": collision.key, "poi_hash": collision.poi_hash},
                )
            )
    return findings


def _check_index_dangling_mentions(state: LinterState) -> list[LinterFinding]:
    """Advisory dangling-mention `Drift.POI`s per depot — default-off (opt-in).

    Registered but off by default: correct-but-noisy on the real index until the
    resolver-gap rules (canonical/plural short-forms, `::`-scoped names, example
    placeholders, non-index skill-surface concepts) land (Impl.Req 700/701).
    Enable per run with `--check dangling-mention`.
    """
    from agentos.index.drift import index_dangling_mentions

    findings: list[LinterFinding] = []
    for depot in state.config.depot_paths:
        rel = state.rel_path(depot)
        for mention in index_dangling_mentions(depot):
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=DEPOT_DANGLING_MENTION,
                    path=rel,
                    message=mention.detail,
                    details={"concept": mention.key, "poi_hash": mention.poi_hash},
                )
            )
    return findings


def _needs_concept_inventory(state: LinterState) -> GateResult:
    for code in MDBLOCKS_BLOCKING_CODES:
        if state.has_error(code):
            return blocked("markdown block syntax has errors", code)
    if not state.concepts:
        return blocked("concept inventory is unavailable", CONCEPT_INVENTORY)
    return allowed()


def _needs_router_inventory(state: LinterState) -> GateResult:
    if not state.routers:
        return blocked("router inventory is unavailable", ROUTER_MISSING)
    return _needs_concept_inventory(state)


def _check_status(state: LinterState, code: str) -> CheckStatus | None:
    for result in state.check_results:
        if result.code == code:
            return result.status
    return None


def _needs_appendix_route_annotation_inputs(state: LinterState) -> GateResult:
    router_gate = _needs_router_inventory(state)
    if not router_gate.allowed:
        return router_gate
    appendix_status = _check_status(state, CHECK_APPENDIX_FILENAMES)
    if appendix_status is None:
        return blocked(
            "appendix filename inventory has not run", CHECK_APPENDIX_FILENAMES
        )
    if appendix_status == "blocked":
        return blocked(
            "appendix filename inventory is unavailable", CHECK_APPENDIX_FILENAMES
        )
    if _check_status(state, CHECK_ROUTER_ENTRIES) == "blocked":
        return blocked("router entry inventory is unavailable", CHECK_ROUTER_ENTRIES)
    return allowed()


def _check_config_surfaces(state: LinterState) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    if not (
        state.config.index_paths
        or state.config.appendix_paths
        or state.config.agendix_paths
    ):
        if state.raw_depot_paths:
            # A valid index depot that simply has no chapter surfaces yet — a
            # `000-INDEX.md` router with no `NNN-<chapter>.md` files — is
            # empty-but-valid (an unpopulated `Agentos.Index.Notes` scaffold),
            # not a misconfiguration. Nothing to lint, so raise nothing; a
            # genuinely wrong depot path has no router and still errors.
            depots = state.config.depot_paths
            if depots and all((depot / "000-INDEX.md").is_file() for depot in depots):
                return findings
            findings.append(
                LinterFinding(
                    severity="error",
                    code=CONFIG_NO_SURFACES,
                    path=state.raw_depot_paths[0],
                    message=(
                        "Configured --depot paths produced no lint surfaces. "
                        "Check that each depot path exists, is a directory, and contains chapter folders."
                    ),
                )
            )
            return findings
        findings.append(
            LinterFinding(
                severity="error",
                code=CONFIG_NO_SURFACES,
                path=".",
                message="Configure at least one --depot, --index, or --appendix path.",
            )
        )
        return findings

    for kind, raw_paths, paths in (
        ("index", state.raw_index_paths, state.config.index_paths),
        ("appendix", state.raw_appendix_paths, state.config.appendix_paths),
        (
            "agendix",
            tuple(state.rel_path(path) for path in state.config.agendix_paths),
            state.config.agendix_paths,
        ),
    ):
        for raw_path, path in zip(raw_paths, paths, strict=True):
            rel_path = state.rel_path(path)
            valid = path.exists() and (path.is_dir() or path.suffix.lower() == ".md")
            state.surfaces.append(
                SurfacePath(
                    kind=kind,  # type: ignore[arg-type]
                    raw_path=raw_path,
                    path=path,
                    rel_path=rel_path,
                    valid=valid,
                )
            )
            if valid:
                continue
            if not path.exists():
                findings.append(
                    LinterFinding(
                        severity="error",
                        code=SURFACE_MISSING_BY_KIND[kind],
                        path=rel_path,
                        message=f"Configured {kind} path does not exist.",
                    )
                )
            elif path.is_file() and path.suffix.lower() != ".md":
                findings.append(
                    LinterFinding(
                        severity="error",
                        code=SURFACE_NOT_MARKDOWN_BY_KIND[kind],
                        path=rel_path,
                        message=f"Configured {kind} file is not a markdown file.",
                    )
                )
            elif not path.is_dir():
                findings.append(
                    LinterFinding(
                        severity="error",
                        code=SURFACE_INVALID_BY_KIND[kind],
                        path=rel_path,
                        message=f"Configured {kind} path is not a markdown file or directory.",
                    )
                )
    return findings


def _check_discover_files(state: LinterState) -> list[LinterFinding]:
    for surface in state.surfaces:
        if not surface.valid:
            continue
        files = _surface_markdown_files(state, surface)
        state.files_by_kind[surface.kind].extend(state.rel_path(path) for path in files)
    scope_findings = _check_scope_paths(state)
    if scope_findings:
        return scope_findings
    if any(state.files_by_kind.values()):
        return []
    return [
        LinterFinding(
            severity="warning",
            code=FILES_NONE,
            path=".",
            message="No markdown files were discovered in configured surfaces.",
        )
    ]


def _check_scope_paths(state: LinterState) -> list[LinterFinding]:
    if not state.config.scope_paths:
        return []
    configured_paths = [surface.path for surface in state.surfaces if surface.valid] + [
        (state.config.root / rel_path).resolve()
        for paths in state.files_by_kind.values()
        for rel_path in paths
    ]
    findings: list[LinterFinding] = []
    for scope in state.config.scope_paths:
        if any(path_is_or_contains(scope, path) for path in configured_paths):
            continue
        findings.append(
            LinterFinding(
                severity="error",
                code=SURFACE_INVALID,
                path=state.rel_path(scope),
                message="Configured --scope path matches no configured linter file.",
            )
        )
    return findings


def _check_mdblocks_syntax(state: LinterState) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    for kind in ("index", "appendix", "agendix"):
        surfaces = [
            surface
            for surface in state.surfaces
            if surface.kind == kind and surface.valid
        ]
        if not surfaces:
            continue
        config = MarkdownScanConfig(
            root=state.config.root,
            targets=tuple(surface.path for surface in surfaces),
            excludes=DEFAULT_SCAN_EXCLUDES,
            min_level=2,
            max_level=6,
            start_line=None,
            end_line=None,
            recursive=True,
            include_content=False,
        )
        state.mdblock_files_by_kind[kind] = scan_markdown_blocks(config)
        lint_payload = lint_markdown_blocks(config)
        for issue in lint_payload["issues"]:
            if issue["code"] == "preamble_text_before_first_block":
                continue
            source_code = str(issue["code"])
            findings.append(
                LinterFinding(
                    severity=issue["severity"],
                    code=MDBLOCKS_CODE_MAP.get(source_code, MDBLOCKS_SYNTAX),
                    path=issue["path"],
                    line=issue.get("line"),
                    message=f"{source_code}: {issue['message']}",
                    details={"source_code": source_code, **issue.get("details", {})},
                )
            )
    return findings


def _check_unanchored_sections(state: LinterState) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    _ensure_parsed_documents(state)
    for document in state.parsed_documents:
        if document.surface_kind == "router":
            continue
        for node in document.nodes:
            if (
                not isinstance(node, Diagnostic)
                or node.reason != "heading_without_separator"
            ):
                continue
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=BLOCK_UNANCHORED_SECTION,
                    path=state.rel_path(node.path) if node.path else ".",
                    line=node.start_line,
                    message="Section heading is not part of a separator-anchored block.",
                    details={"heading": node.parsed.get("heading", node.src)},
                )
            )
    return findings


def _check_router_presence(state: LinterState) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    depot_roots: dict[str, Path] = {}
    for surface in state.surfaces:
        if not surface.valid:
            continue
        depot_root = _surface_depot_root(surface)
        depot_roots.setdefault(state.rel_path(depot_root), depot_root)

    missing_router_roots: list[str] = []
    for rel_root, depot_root in sorted(depot_roots.items()):
        router_file = depot_root / "000-INDEX.md"
        legacy_files = sorted(
            path
            for legacy_name in ("000-index.md", "001-index.md")
            for path in depot_root.rglob(legacy_name)
        )
        for legacy_file in legacy_files:
            findings.append(
                LinterFinding(
                    severity="error",
                    code=ROUTER_LEGACY_NAME,
                    path=state.rel_path(legacy_file),
                    message="Legacy router filename is not allowed; use `000-INDEX.md` at the depot root.",
                )
            )
        if not router_file.exists():
            missing_router_roots.append(rel_root)
            continue
        rel_path = state.rel_path(router_file)
        state.routers.append(rel_path)
        if router_file.stat().st_size == 0:
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=ROUTER_EMPTY,
                    path=rel_path,
                    message="Router file exists but is empty.",
                )
            )
    if not state.routers and missing_router_roots:
        findings.append(
            LinterFinding(
                severity="error",
                code=ROUTER_MISSING,
                path=missing_router_roots[0],
                message="Configured surfaces include no depot-root router file (`000-INDEX.md`).",
                details={"checked_paths": missing_router_roots},
            )
        )
    return findings


def _check_index_filenames(state: LinterState) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    for rel_path in state.files_by_kind["index"]:
        path = Path(rel_path)
        if path.name == "000-INDEX.md":
            continue
        match = INDEX_FILENAME_RE.fullmatch(path.name)
        if match and match.group("chapter") == path.parent.name:
            continue
        findings.append(
            LinterFinding(
                severity="warning",
                code=INDEX_INVALID_FILENAME,
                path=rel_path,
                message="Index markdown file does not match `NNN-<chapter>.md` naming for its directory.",
            )
        )
    return findings


def _check_concept_inventory(state: LinterState) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    _ensure_parsed_documents(state)
    for document in state.parsed_documents:
        if document.surface_kind != "chapter":
            continue
        for block in (
            node for node in document.nodes if isinstance(node, BlockHeading)
        ):
            title = str(block.parsed["path"]).strip()
            concept_block = ConceptBlock(
                concept=title,
                path=state.rel_path(block.path) if block.path else ".",
                line=block.start_line,
            )
            state.concepts.setdefault(title, []).append(concept_block)
            if not block.parsed.get("valid"):
                findings.append(
                    LinterFinding(
                        severity="warning",
                        code=CONCEPT_INVALID_HEADING,
                        path=concept_block.path,
                        line=concept_block.line,
                        message="Index block heading does not match the current block-path pattern.",
                        details={"heading": title},
                    )
                )
    if not state.concepts and state.has_valid_surface("index"):
        findings.append(
            LinterFinding(
                severity="warning",
                code=CONCEPT_INVENTORY_EMPTY,
                path=".",
                message="No separator-anchored concept blocks were discovered in configured index surfaces.",
            )
        )
    return findings


def _check_duplicate_concepts(state: LinterState) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    for concept, blocks in sorted(state.concepts.items()):
        if len(blocks) < 2:
            continue
        first = blocks[0]
        for duplicate in blocks[1:]:
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=CONCEPT_DUPLICATE,
                    path=duplicate.path,
                    line=duplicate.line,
                    message="Concept block duplicates an earlier index concept heading.",
                    details={
                        "concept": concept,
                        "first_path": first.path,
                        "first_line": first.line,
                    },
                )
            )
    return findings


def _check_appendix_filenames(state: LinterState) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    for rel_path in state.files_by_kind["appendix"]:
        filename = Path(rel_path).name
        match = APPENDIX_FILENAME_RE.fullmatch(filename)
        if match is None:
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=APPENDIX_INVALID_FILENAME,
                    path=rel_path,
                    message="Appendix filename does not match `Concept.Name-appendix.md` or page form.",
                )
            )
            continue
        concept = match.group("concept")
        state.appendix_concepts.setdefault(concept, []).append(rel_path)
        page = int(match.group("page") or "1")
        state.appendix_pages.setdefault(concept, {}).setdefault(page, []).append(
            rel_path
        )
    return findings


def _check_orphan_appendix(state: LinterState) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    for concept, paths in sorted(state.appendix_concepts.items()):
        if concept in state.concepts:
            continue
        for rel_path in paths:
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=APPENDIX_ORPHAN,
                    path=rel_path,
                    message="Appendix file has no matching configured index concept block.",
                    details={"concept": concept},
                )
            )
    return findings


def _check_router_entries(state: LinterState) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    _ensure_parsed_documents(state)
    for document in state.parsed_documents:
        if document.surface_kind != "router":
            continue
        router_rel_path = state.rel_path(document.path) if document.path else "."
        for node in (
            node for node in document.nodes if isinstance(node, ModelRouterEntry)
        ):
            route_file = str(node.parsed["file"])
            for route_concept in node.parsed["concepts"]:
                concept = str(route_concept["concept"])
                if not concept:
                    continue
                state.router_entries.setdefault(concept, []).append(
                    RouterEntry(
                        concept=concept,
                        raw_concept=str(route_concept["raw"]),
                        appendix_annotation_count=route_concept["plus_n"],
                        route_file=route_file,
                        router_path=router_rel_path,
                        line=node.start_line,
                    )
                )
                if not BLOCK_PATH_RE.fullmatch(concept):
                    findings.append(
                        LinterFinding(
                            severity="warning",
                            code=ROUTER_INVALID_CONCEPT,
                            path=router_rel_path,
                            line=node.start_line,
                            message="Router entry concept does not match the current block-path pattern.",
                            details={"concept": concept, "route_file": route_file},
                        )
                    )
    if not state.router_entries and state.routers:
        findings.append(
            LinterFinding(
                severity="warning",
                code=ROUTER_ENTRIES_EMPTY,
                path=".",
                message="No concept routing entries were parsed from router files.",
            )
        )
    return findings


def _check_appendix_route_annotations(state: LinterState) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    for concept, pages in sorted(state.appendix_pages.items()):
        sorted_pages = sorted(pages)
        missing_pages = _missing_appendix_pages(sorted_pages)
        if missing_pages:
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=APPENDIX_PAGE_GAP,
                    path=pages[sorted_pages[0]][0],
                    message="Appendix page files are not contiguous.",
                    details={
                        "concept": concept,
                        "pages": sorted_pages,
                        "missing_pages": missing_pages,
                    },
                )
            )
            continue

        entries = state.router_entries.get(concept, [])
        if not entries:
            continue
        expected_count = sorted_pages[-1]
        for entry in entries:
            if entry.appendix_annotation_count is None:
                findings.append(
                    LinterFinding(
                        severity="warning",
                        code=APPENDIX_ROUTE_ANNOTATION_MISSING,
                        path=entry.router_path,
                        line=entry.line,
                        message="Router entry has appendix pages but no `[+N]` annotation.",
                        details={
                            "concept": concept,
                            "expected_annotation": f"[+{expected_count}]",
                            "appendix_pages": expected_count,
                            "route_file": entry.route_file,
                        },
                    )
                )
                continue
            if entry.appendix_annotation_count == expected_count:
                continue
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=APPENDIX_ROUTE_ANNOTATION_STALE,
                    path=entry.router_path,
                    line=entry.line,
                    message="Router appendix annotation does not match discovered appendix pages.",
                    details={
                        "concept": concept,
                        "actual_annotation": f"[+{entry.appendix_annotation_count}]",
                        "expected_annotation": f"[+{expected_count}]",
                        "appendix_pages": expected_count,
                        "route_file": entry.route_file,
                    },
                )
            )
    return findings


def _check_router_covers_blocks(state: LinterState) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    for concept, blocks in sorted(state.concepts.items()):
        if concept in state.router_entries:
            continue
        for block in blocks:
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=ROUTER_MISSING_ENTRY,
                    path=block.path,
                    line=block.line,
                    message="Concept block is not listed in a configured router.",
                    details={"concept": concept},
                )
            )
    return findings


def _check_router_targets(state: LinterState) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    concept_locations = {
        concept: {Path(block.path).name for block in blocks}
        for concept, blocks in state.concepts.items()
    }
    for concept, entries in sorted(state.router_entries.items()):
        if concept not in state.concepts:
            for entry in entries:
                route_path = (
                    state.config.root / entry.router_path
                ).parent / entry.route_file
                if not route_path.exists():
                    findings.append(
                        LinterFinding(
                            severity="warning",
                            code=ROUTER_MISSING_FILE,
                            path=entry.router_path,
                            line=entry.line,
                            message="Router entry points to a file that does not exist.",
                            details={
                                "concept": concept,
                                "route_file": entry.route_file,
                            },
                        )
                    )
                findings.append(
                    LinterFinding(
                        severity="warning",
                        code=ROUTER_UNKNOWN_CONCEPT,
                        path=entry.router_path,
                        line=entry.line,
                        message="Router entry points to a concept block that was not discovered.",
                        details={"concept": concept, "route_file": entry.route_file},
                    )
                )
            continue
        for entry in entries:
            route_path = (
                state.config.root / entry.router_path
            ).parent / entry.route_file
            if not route_path.exists():
                findings.append(
                    LinterFinding(
                        severity="warning",
                        code=ROUTER_MISSING_FILE,
                        path=entry.router_path,
                        line=entry.line,
                        message="Router entry points to a file that does not exist.",
                        details={"concept": concept, "route_file": entry.route_file},
                    )
                )
                continue
            if Path(entry.route_file).name in concept_locations[concept]:
                continue
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=ROUTER_WRONG_FILE,
                    path=entry.router_path,
                    line=entry.line,
                    message="Router entry file does not match the discovered concept block file.",
                    details={
                        "concept": concept,
                        "route_file": entry.route_file,
                        "actual_files": sorted(concept_locations[concept]),
                    },
                )
            )
    return findings


def _missing_appendix_pages(pages: list[int]) -> list[int]:
    if not pages:
        return []
    return [page for page in range(1, pages[-1] + 1) if page not in pages]


def _is_excluded(state: LinterState, path: Path) -> bool:
    if path.name == "AGENTS.md":
        return True
    parts = set(path.relative_to(state.config.root).parts)
    return any(pattern in parts for pattern in DEFAULT_SCAN_EXCLUDES)


def _surface_markdown_files(state: LinterState, surface: SurfacePath) -> list[Path]:
    if surface.path.is_file():
        return [] if _is_excluded(state, surface.path) else [surface.path]
    return sorted(
        path for path in surface.path.rglob("*.md") if not _is_excluded(state, path)
    )


STRUCTURAL_CHECKS: tuple[LinterCheck, ...] = (
    LinterCheck(
        code=CHECK_CONFIG_SURFACES,
        title="Configured surfaces",
        gate=_always,
        run=_check_config_surfaces,
        binding=LinterCheckBinding(structural=True),
    ),
    LinterCheck(
        code=CHECK_DISCOVER_FILES,
        title="Discover markdown files",
        gate=_needs_valid_surface,
        run=_check_discover_files,
        binding=LinterCheckBinding(structural=True),
    ),
    LinterCheck(
        code=CHECK_MDBLOCKS_SYNTAX,
        title="Markdown block syntax",
        gate=_needs_discovered_files,
        run=_check_mdblocks_syntax,
        binding=LinterCheckBinding(structural=True),
    ),
    LinterCheck(
        code=CHECK_BLOCK_SECTIONS,
        title="Separator-anchored sections",
        gate=_needs_discovered_files,
        run=_check_unanchored_sections,
    ),
    LinterCheck(
        code=CHECK_ROUTER_PRESENCE,
        title="Router presence",
        gate=_needs_index_surface,
        run=_check_router_presence,
        binding=LinterCheckBinding(structural=True),
    ),
    LinterCheck(
        code=CHECK_DEPOT_DEPENDENCIES,
        title="Depot dependencies",
        gate=_needs_index_surface,
        run=_check_depot_dependencies,
    ),
    LinterCheck(
        code=CHECK_DANGLING_MENTION,
        title="Dangling mentions",
        gate=_needs_index_surface,
        run=_check_index_dangling_mentions,
        binding=LinterCheckBinding(default_on=False),
    ),
    LinterCheck(
        code=CHECK_INDEX_FILENAMES,
        title="Index filenames",
        gate=_needs_index_surface,
        run=_check_index_filenames,
    ),
    LinterCheck(
        code=CHECK_CONCEPT_INVENTORY,
        title="Concept inventory",
        gate=_needs_index_surface,
        run=_check_concept_inventory,
        binding=LinterCheckBinding(structural=True),
    ),
    LinterCheck(
        code=CHECK_CONCEPT_DUPLICATES,
        title="Duplicate concepts",
        gate=_needs_concept_inventory,
        run=_check_duplicate_concepts,
    ),
    LinterCheck(
        code=CHECK_APPENDIX_FILENAMES,
        title="Appendix filenames",
        gate=_needs_valid_surface,
        run=_check_appendix_filenames,
    ),
    LinterCheck(
        code=CHECK_APPENDIX_ORPHANS,
        title="Orphan appendix files",
        gate=_needs_concept_inventory,
        run=_check_orphan_appendix,
    ),
    LinterCheck(
        code=CHECK_ROUTER_ENTRIES,
        title="Router entries",
        gate=_needs_router_inventory,
        run=_check_router_entries,
    ),
    LinterCheck(
        code=CHECK_APPENDIX_ROUTE_ANNOTATIONS,
        title="Appendix route annotations",
        gate=_needs_appendix_route_annotation_inputs,
        run=_check_appendix_route_annotations,
    ),
    LinterCheck(
        code=CHECK_ROUTER_COVERAGE,
        title="Router covers concept blocks",
        gate=_needs_router_inventory,
        run=_check_router_covers_blocks,
    ),
    LinterCheck(
        code=CHECK_ROUTER_TARGETS,
        title="Router targets real blocks",
        gate=_needs_router_inventory,
        run=_check_router_targets,
    ),
)
