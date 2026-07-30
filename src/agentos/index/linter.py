# $kw: ^index-poi-linter --from POI.System --from POI.Linter --note [CT] Index findings adapt into the shared POI report at the public boundary ^c20260729-49u
from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from agentos.poi import (
    POICatalog,
    POIReport,
    build_poi_report,
    check_registry as _core_check_registry,
    check_selector as check_selector,
    resolve_enabled_checks,
)

from ._linter_models import (
    CheckResult,
    CheckStatus,
    ConceptBlock,
    CoverageItem,
    GateResult,
    LinterCheck,
    LinterConfig,
    LinterFinding,
    LinterState,
    LineSupportStanding,
    RouterEntry,
    Severity,
    SurfaceKind,
    SurfacePath,
    allowed,
    blocked,
    path_is_or_contains,
    parsed_linter_kernel_lines,
)
from ._linter_parser_checks import (
    ANCHOR_LEGACY_SIGIL,
    ANCHOR_UNPREFIXED,
    BLOCK_UNGROUNDED,
    CHECK_ANCHOR_LEGACY_SIGIL,
    CHECK_ANCHOR_UNPREFIXED,
    CHECK_BLOCK_UNGROUNDED,
    CHECK_LINE_TYPES,
    CHECK_LINE_UNLINKED,
    CHECK_REVIEWED_CITE_CLOSURE,
    CHECK_TYPE_STATEMENT_LEGACY_SIGIL,
    LINE_TYPE_GR_MISSING_ANCHOR,
    LINE_TYPE_SYNTAX,
    LINE_TYPE_UNKNOWN,
    LINE_UNLINKED,
    PARSER_CHECKS,
    REVIEWED_CITE_CLOSURE,
    SOURCE_AXIS_PLACEMENT,
    TYPE_STATEMENT_LEGACY_SIGIL,
)
from ._linter_structure import (
    APPENDIX_FILENAME_RE,
    APPENDIX_INVALID_FILENAME,
    APPENDIX_ORPHAN,
    APPENDIX_PAGE_GAP,
    APPENDIX_ROUTE_ANNOTATION_MISSING,
    APPENDIX_ROUTE_ANNOTATION_STALE,
    BLOCK_DUPLICATE_HEADING,
    BLOCK_EMPTY_HEADING,
    BLOCK_NO_HEADINGS,
    BLOCK_PATH_RE,
    BLOCK_SEPARATOR_OUTSIDE_SEMANTICS,
    BLOCK_TOO_LONG,
    BLOCK_UNANCHORED_SECTION,
    BLOCK_UNCLOSED_CODE_FENCE,
    CHECK_APPENDIX_FILENAMES,
    CHECK_APPENDIX_ORPHANS,
    CHECK_APPENDIX_ROUTE_ANNOTATIONS,
    CHECK_BLOCK_SECTIONS,
    CHECK_CONCEPT_DUPLICATES,
    CHECK_CONCEPT_INVENTORY,
    CHECK_CONFIG_SURFACES,
    CHECK_DANGLING_MENTION,
    CHECK_DEPOT_DEPENDENCIES,
    CHECK_DISCOVER_FILES,
    CHECK_INDEX_FILENAMES,
    CHECK_MDBLOCKS_SYNTAX,
    CHECK_ROUTER_COVERAGE,
    CHECK_ROUTER_ENTRIES,
    CHECK_ROUTER_PRESENCE,
    CHECK_ROUTER_TARGETS,
    CONFIG_NO_SURFACES,
    CONCEPT_DUPLICATE,
    CONCEPT_INVALID_HEADING,
    CONCEPT_INVENTORY,
    CONCEPT_INVENTORY_EMPTY,
    DEPOT_COLLISION,
    DEPOT_DANGLING_MENTION,
    DEPOT_DEP_UNRESOLVED,
    FILES_NONE,
    INDEX_FILENAME_RE,
    INDEX_INVALID_FILENAME,
    MDBLOCKS_BLOCKING_CODES,
    MDBLOCKS_CODE_MAP,
    MDBLOCKS_SYNTAX,
    ROUTER_EMPTY,
    ROUTER_ENTRIES_EMPTY,
    ROUTER_INVALID_CONCEPT,
    ROUTER_LEGACY_NAME,
    ROUTER_MISSING,
    ROUTER_MISSING_ENTRY,
    ROUTER_MISSING_FILE,
    ROUTER_UNKNOWN_CONCEPT,
    ROUTER_WRONG_FILE,
    STRUCTURAL_CHECKS,
    SURFACE_INVALID,
    SURFACE_INVALID_BY_KIND,
    SURFACE_MISSING_BY_KIND,
    SURFACE_NOT_MARKDOWN_BY_KIND,
)
from .poi import finding_to_poi


__all__ = [
    "ANCHOR_LEGACY_SIGIL",
    "ANCHOR_UNPREFIXED",
    "APPENDIX_FILENAME_RE",
    "APPENDIX_INVALID_FILENAME",
    "APPENDIX_ORPHAN",
    "APPENDIX_PAGE_GAP",
    "APPENDIX_ROUTE_ANNOTATION_MISSING",
    "APPENDIX_ROUTE_ANNOTATION_STALE",
    "BLOCK_DUPLICATE_HEADING",
    "BLOCK_EMPTY_HEADING",
    "BLOCK_NO_HEADINGS",
    "BLOCK_PATH_RE",
    "BLOCK_SEPARATOR_OUTSIDE_SEMANTICS",
    "BLOCK_TOO_LONG",
    "BLOCK_UNANCHORED_SECTION",
    "BLOCK_UNCLOSED_CODE_FENCE",
    "BLOCK_UNGROUNDED",
    "CHECKS",
    "CHECK_ANCHOR_LEGACY_SIGIL",
    "CHECK_ANCHOR_UNPREFIXED",
    "CHECK_APPENDIX_FILENAMES",
    "CHECK_APPENDIX_ORPHANS",
    "CHECK_APPENDIX_ROUTE_ANNOTATIONS",
    "CHECK_BLOCK_SECTIONS",
    "CHECK_BLOCK_UNGROUNDED",
    "CHECK_CONCEPT_DUPLICATES",
    "CHECK_CONCEPT_INVENTORY",
    "CHECK_CONFIG_SURFACES",
    "CHECK_DANGLING_MENTION",
    "CHECK_DEPOT_DEPENDENCIES",
    "CHECK_DISCOVER_FILES",
    "CHECK_INDEX_FILENAMES",
    "CHECK_LINE_TYPES",
    "CHECK_LINE_UNLINKED",
    "CHECK_MDBLOCKS_SYNTAX",
    "CHECK_REVIEWED_CITE_CLOSURE",
    "CHECK_ROUTER_COVERAGE",
    "CHECK_ROUTER_ENTRIES",
    "CHECK_ROUTER_PRESENCE",
    "CHECK_ROUTER_TARGETS",
    "CHECK_TYPE_STATEMENT_LEGACY_SIGIL",
    "CONFIG_NO_SURFACES",
    "CONCEPT_DUPLICATE",
    "CONCEPT_INVALID_HEADING",
    "CONCEPT_INVENTORY",
    "CONCEPT_INVENTORY_EMPTY",
    "CheckResult",
    "CheckStatus",
    "ConceptBlock",
    "CoverageItem",
    "DEPOT_COLLISION",
    "DEPOT_DANGLING_MENTION",
    "DEPOT_DEP_UNRESOLVED",
    "FILES_NONE",
    "GateResult",
    "INDEX_FILENAME_RE",
    "INDEX_INVALID_FILENAME",
    "LINE_TYPE_GR_MISSING_ANCHOR",
    "LINE_TYPE_SYNTAX",
    "LINE_TYPE_UNKNOWN",
    "LINE_UNLINKED",
    "LinterCheck",
    "LinterConfig",
    "LinterFinding",
    "LinterState",
    "LineSupportStanding",
    "MDBLOCKS_BLOCKING_CODES",
    "MDBLOCKS_CODE_MAP",
    "MDBLOCKS_SYNTAX",
    "REVIEWED_CITE_CLOSURE",
    "ROUTER_EMPTY",
    "ROUTER_ENTRIES_EMPTY",
    "ROUTER_INVALID_CONCEPT",
    "ROUTER_LEGACY_NAME",
    "ROUTER_MISSING",
    "ROUTER_MISSING_ENTRY",
    "ROUTER_MISSING_FILE",
    "ROUTER_UNKNOWN_CONCEPT",
    "ROUTER_WRONG_FILE",
    "RouterEntry",
    "SOURCE_AXIS_PLACEMENT",
    "SURFACE_INVALID",
    "SURFACE_INVALID_BY_KIND",
    "SURFACE_MISSING_BY_KIND",
    "SURFACE_NOT_MARKDOWN_BY_KIND",
    "Severity",
    "SurfaceKind",
    "SurfacePath",
    "TYPE_STATEMENT_LEGACY_SIGIL",
    "allowed",
    "blocked",
    "build_linter_config",
    "build_linter_poi_report",
    "check_registry",
    "check_selector",
    "parsed_linter_kernel_lines",
    "render_linter_json",
    "render_linter_text",
    "resolve_enabled_checks",
    "run_linter",
]


CHECKS: tuple[LinterCheck, ...] = (*STRUCTURAL_CHECKS, *PARSER_CHECKS)


def check_registry(checks: Sequence["LinterCheck"] = ()) -> list[dict[str, Any]]:
    """Selector + metadata for each registered check (defaults to `CHECKS`)."""
    return _core_check_registry(checks or CHECKS)


def build_linter_config(
    *,
    depot_paths: tuple[str, ...],
    index_paths: tuple[str, ...],
    appendix_paths: tuple[str, ...],
    coverage: tuple[str, ...] = (),
    scope_paths: tuple[str, ...] = (),
    warn_unlinked: bool = False,
) -> tuple[LinterConfig, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    resolved_root = Path.cwd().resolve()
    resolved_depots = tuple(
        _resolve_under_root(resolved_root, path) for path in depot_paths
    )
    resolved_coverage = _resolve_coverage(coverage, warn_unlinked=warn_unlinked)
    resolved_scope_paths = tuple(
        _resolve_under_root(resolved_root, path) for path in scope_paths
    )
    derived_index_paths: list[str] = list(index_paths)
    derived_appendix_paths: list[str] = list(appendix_paths)
    for depot_path in resolved_depots:
        if not depot_path.is_dir():
            continue
        for chapter_dir in sorted(
            path for path in depot_path.iterdir() if path.is_dir()
        ):
            if chapter_dir.name == "appendix":
                continue
            if any(
                (match := INDEX_FILENAME_RE.fullmatch(path.name)) is not None
                and match.group("chapter") == chapter_dir.name
                for path in chapter_dir.glob("*.md")
            ):
                derived_index_paths.append(
                    _relativize_under_root(resolved_root, chapter_dir)
                )
        appendix_dir = depot_path / "appendix"
        if appendix_dir.is_dir():
            derived_appendix_paths.append(
                _relativize_under_root(resolved_root, appendix_dir)
            )
    return (
        LinterConfig(
            root=resolved_root,
            depot_paths=resolved_depots,
            index_paths=tuple(
                _resolve_under_root(resolved_root, path) for path in derived_index_paths
            ),
            appendix_paths=tuple(
                _resolve_under_root(resolved_root, path)
                for path in derived_appendix_paths
            ),
            coverage=resolved_coverage,
            scope_paths=resolved_scope_paths,
        ),
        depot_paths,
        tuple(derived_index_paths),
        tuple(derived_appendix_paths),
    )


def run_linter(
    config: LinterConfig,
    raw_depot_paths: tuple[str, ...],
    raw_index_paths: tuple[str, ...],
    raw_appendix_paths: tuple[str, ...],
    *,
    extra_checks: Sequence["LinterCheck"] = (),
    include: Sequence[str] = (),
    exclude: Sequence[str] = (),
) -> LinterState:
    state = LinterState(
        config=config,
        raw_depot_paths=raw_depot_paths,
        raw_index_paths=raw_index_paths,
        raw_appendix_paths=raw_appendix_paths,
    )
    enabled = resolve_enabled_checks(
        (*CHECKS, *extra_checks), include=include, exclude=exclude
    )
    enabled = [
        *(check for check in enabled if check.structural),
        *(check for check in enabled if not check.structural),
    ]
    for check in enabled:
        gate = check.gate(state)
        if not gate.allowed:
            state.record_blocked(check, gate)
            continue
        state.record_check(check, check.run(state))
    return state


def build_linter_poi_report(
    state: LinterState,
    *,
    catalog: POICatalog | None = None,
) -> POIReport:
    view = _scoped_view(state)
    selected_catalog = catalog if catalog is not None else POICatalog.discover()
    return build_poi_report(
        finding_to_poi(
            finding,
            selected_catalog,
            package_id=state.finding_poi_package_ids.get(id(finding), "agentos-pkg"),
        )
        for finding in view["findings"]
    )


def render_linter_json(
    state: LinterState,
    *,
    catalog: POICatalog | None = None,
    poi_report: POIReport | None = None,
) -> str:
    report = poi_report or build_linter_poi_report(state, catalog=catalog)
    return json.dumps(_state_payload(state, report), indent=2)


def render_linter_text(
    state: LinterState,
    *,
    catalog: POICatalog | None = None,
    poi_report: POIReport | None = None,
    show_passed: bool = False,
) -> str:
    view = _scoped_view(state)
    lines = ["Index linter"]
    report = poi_report or build_linter_poi_report(state, catalog=catalog)
    if report.groups:
        lines.append("")
        lines.extend(report.render_text().splitlines())

    if show_passed:
        passed_results = [
            result for result in view["check_results"] if result.status == "passed"
        ]
        if passed_results:
            lines.append("")
            lines.append("Passed checks:")
            for result in passed_results:
                lines.append(f"- [OK] {result.code} - {result.title}")

    blocked_results = [
        result for result in view["check_results"] if result.status == "blocked"
    ]
    if blocked_results:
        lines.append("")
        lines.append("Blocked checks:")
        for result in blocked_results:
            suffix = ""
            if result.blocked_by:
                suffix = f" (blocked by: {', '.join(result.blocked_by)})"
            lines.append(f"- {result.code}: {result.reason or 'blocked'}{suffix}")

    coverage_payload = view["coverage"]
    if coverage_payload:
        lines.append("")
        lines.append("Coverage:")
        for name, meter in coverage_payload.items():
            if name == "line":
                lines.append(f"- line: {meter['linked']}/{meter['total']} linked")
            elif name == "block":
                lines.append(f"- block: {meter['grounded']}/{meter['total']} grounded")

    summary = view["summary"]
    lines.append("")
    lines.append(
        "Summary: "
        f"{summary['error_count']} error(s), "
        f"{summary['warning_count']} warning(s), "
        f"{summary['blocked_count']} blocked check(s), "
        f"{summary['passed_count']} passed check(s)."
    )
    return "\n".join(lines)


def _resolve_under_root(root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    resolved = (
        candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    )
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SystemExit(
            f"error: path is outside the current working directory: {raw_path}"
        ) from exc
    return resolved


def _relativize_under_root(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _state_payload(state: LinterState, poi_report: POIReport) -> dict[str, Any]:
    view = _scoped_view(state)
    config: dict[str, Any] = {
        "depot": list(state.raw_depot_paths),
        "index": list(state.raw_index_paths),
        "appendix": list(state.raw_appendix_paths),
    }
    if state.config.coverage:
        config["coverage"] = sorted(state.config.coverage)
    if state.config.scope_paths:
        config["scope"] = [state.rel_path(path) for path in state.config.scope_paths]
    poi_payload = poi_report.as_dict()
    payload = {
        "root": str(state.config.root),
        "config": config,
        "surfaces": [
            {
                "kind": surface.kind,
                "path": surface.rel_path,
                "valid": surface.valid,
            }
            for surface in state.surfaces
        ],
        "files": {kind: list(paths) for kind, paths in state.files_by_kind.items()},
        "checks": [result.to_payload() for result in view["check_results"]],
        "poi_classes": poi_payload["classes"],
        "pois": poi_payload["instances"],
        "summary": view["summary"],
        "exit_code": 1 if view["summary"]["error_count"] else 0,
    }
    if view["coverage"]:
        payload["coverage"] = view["coverage"]
    return payload


def _resolve_coverage(
    coverage: tuple[str, ...], *, warn_unlinked: bool
) -> frozenset[str]:
    resolved: set[str] = set()
    for name in coverage:
        if name == "all":
            resolved.update(("line", "block"))
            continue
        if name not in {"line", "block"}:
            raise SystemExit(f"error: unknown coverage meter: {name}")
        resolved.add(name)
    if warn_unlinked:
        resolved.add("line")
    return frozenset(resolved)


def _scoped_view(state: LinterState) -> dict[str, Any]:
    findings = [
        finding for finding in state.findings if _finding_in_scope(state, finding)
    ]
    check_results = _scoped_check_results(state, findings)
    summary = _summary_from(check_results, findings)
    coverage = _scoped_coverage(state)
    return {
        "findings": findings,
        "check_results": check_results,
        "summary": summary,
        "coverage": coverage,
    }


def _finding_in_scope(state: LinterState, finding: LinterFinding) -> bool:
    if not state.config.scope_paths:
        return True
    return _rel_path_in_scope(state, finding.path)


def _rel_path_in_scope(state: LinterState, rel_path: str) -> bool:
    path = (state.config.root / rel_path).resolve()
    return any(path_is_or_contains(scope, path) for scope in state.config.scope_paths)


def _scoped_check_results(
    state: LinterState,
    findings: list[LinterFinding],
) -> list[CheckResult]:
    findings_by_check: dict[str, list[LinterFinding]] = {}
    for finding in findings:
        check_code = state.finding_check_codes.get(id(finding))
        if check_code is None:
            continue
        findings_by_check.setdefault(check_code, []).append(finding)

    results: list[CheckResult] = []
    for result in state.check_results:
        if result.status == "blocked":
            results.append(result)
            continue
        check_findings = findings_by_check.get(result.code, [])
        error_count = sum(
            1 for finding in check_findings if finding.severity == "error"
        )
        warning_count = sum(
            1 for finding in check_findings if finding.severity == "warning"
        )
        results.append(
            CheckResult(
                code=result.code,
                title=result.title,
                status="failed" if check_findings else "passed",
                finding_count=len(check_findings),
                error_count=error_count,
                warning_count=warning_count,
            )
        )
    return results


def _summary_from(
    check_results: list[CheckResult],
    findings: list[LinterFinding],
) -> dict[str, int]:
    return {
        "check_count": len(check_results),
        "passed_count": sum(1 for result in check_results if result.status == "passed"),
        "failed_count": sum(1 for result in check_results if result.status == "failed"),
        "blocked_count": sum(
            1 for result in check_results if result.status == "blocked"
        ),
        "finding_count": len(findings),
        "error_count": sum(1 for finding in findings if finding.severity == "error"),
        "warning_count": sum(
            1 for finding in findings if finding.severity == "warning"
        ),
    }


def _scoped_coverage(state: LinterState) -> dict[str, dict[str, int]]:
    payload: dict[str, dict[str, int]] = {}
    if "line" in state.config.coverage:
        items = _coverage_items_in_scope(state, "line")
        linked = sum(1 for item in items if item.covered)
        payload["line"] = {"linked": linked, "total": len(items)}
    if "block" in state.config.coverage:
        items = _coverage_items_in_scope(state, "block")
        grounded = sum(1 for item in items if item.covered)
        payload["block"] = {"grounded": grounded, "total": len(items)}
    return payload


def _coverage_items_in_scope(state: LinterState, name: str) -> list[CoverageItem]:
    return [
        item
        for item in state.coverage_items.get(name, [])
        if not state.config.scope_paths or _rel_path_in_scope(state, item.path)
    ]
