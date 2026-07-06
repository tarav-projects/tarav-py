from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from agentos._core.scan import DEFAULT_SCAN_EXCLUDES
from agentos.mdblocks.core import (
    MarkdownScanConfig,
    lint_markdown_blocks,
    scan_markdown_blocks,
)


Severity = Literal["error", "warning"]
CheckStatus = Literal["passed", "failed", "blocked"]
SurfaceKind = Literal["index", "appendix"]

_CONCEPT_SEGMENT = r"[A-Z][A-Za-z0-9]*"
_DOTTED_CONCEPT = rf"{_CONCEPT_SEGMENT}(?:\.{_CONCEPT_SEGMENT})+"
_CONCEPT_PARAM = r"(?:[A-Za-z][\w\-.]*|<[A-Z][A-Za-z0-9]*>)"
_CONCEPT_REF = rf"{_DOTTED_CONCEPT}(?::{_CONCEPT_PARAM})*"
_BLOCK_PATH_SEGMENT = rf"(?:{_CONCEPT_REF}|{_CONCEPT_SEGMENT})"
BLOCK_PATH_RE = re.compile(rf"^{_CONCEPT_REF}(?:/{_BLOCK_PATH_SEGMENT})*$")
APPENDIX_FILENAME_RE = re.compile(rf"^(?P<concept>{_CONCEPT_REF})-appendix(?:-(?P<page>[2-9][0-9]*))?\.md$")
ROUTER_ENTRY_RE = re.compile(r"^-\s+`(?P<file>[^`]+\.md)`\s+[—-]\s+(?P<concepts>.+)$")
APPENDIX_ROUTE_ANNOTATION_RE = re.compile(r"\[\+(?P<count>[1-9][0-9]*)\]$")
INDEX_FILENAME_RE = re.compile(r"^(?P<number>[1-9][0-9]{2})-(?P<chapter>[a-z0-9][a-z0-9-]*)\.md$")
SECTION_HEADING_RE = re.compile(r"^(#{2,6})[ \t]+(.+?)\s*$")

CONFIG_NO_SURFACES = "Index.Linter/Config.NoSurfaces"
SURFACE_INVALID = "Index.Linter/Surface.Invalid"
SURFACE_MISSING_BY_KIND: dict[SurfaceKind, str] = {
    "index": "Index.Linter/Surface.IndexMissing",
    "appendix": "Index.Linter/Surface.AppendixMissing",
}
SURFACE_NOT_MARKDOWN_BY_KIND: dict[SurfaceKind, str] = {
    "index": "Index.Linter/Surface.IndexNotMarkdown",
    "appendix": "Index.Linter/Surface.AppendixNotMarkdown",
}
SURFACE_INVALID_BY_KIND: dict[SurfaceKind, str] = {
    "index": "Index.Linter/Surface.IndexInvalid",
    "appendix": "Index.Linter/Surface.AppendixInvalid",
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


@dataclass(frozen=True)
class LinterConfig:
    root: Path
    depot_paths: tuple[Path, ...]
    index_paths: tuple[Path, ...]
    appendix_paths: tuple[Path, ...]


@dataclass(frozen=True)
class LinterFinding:
    severity: Severity
    code: str
    message: str
    path: str
    line: int | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "path": self.path,
        }
        if self.line is not None:
            payload["line"] = self.line
            payload["path_line"] = f"{self.path}:{self.line}"
            payload["link"] = f"{self.path}#L{self.line}"
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    reason: str | None = None
    blocked_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class LinterCheck:
    code: str
    title: str
    gate: Callable[["LinterState"], GateResult]
    run: Callable[["LinterState"], list[LinterFinding]]


@dataclass
class CheckResult:
    code: str
    title: str
    status: CheckStatus
    finding_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    reason: str | None = None
    blocked_by: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "title": self.title,
            "status": self.status,
            "finding_count": self.finding_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
        }
        if self.reason:
            payload["reason"] = self.reason
        if self.blocked_by:
            payload["blocked_by"] = list(self.blocked_by)
        return payload


@dataclass(frozen=True)
class SurfacePath:
    kind: SurfaceKind
    raw_path: str
    path: Path
    rel_path: str
    valid: bool


@dataclass(frozen=True)
class ConceptBlock:
    concept: str
    path: str
    line: int


@dataclass(frozen=True)
class RouterEntry:
    concept: str
    raw_concept: str
    appendix_annotation_count: int | None
    route_file: str
    router_path: str
    line: int


@dataclass
class LinterState:
    config: LinterConfig
    raw_depot_paths: tuple[str, ...]
    raw_index_paths: tuple[str, ...]
    raw_appendix_paths: tuple[str, ...]
    surfaces: list[SurfacePath] = field(default_factory=list)
    files_by_kind: dict[SurfaceKind, list[str]] = field(
        default_factory=lambda: {"index": [], "appendix": []}
    )
    mdblock_files_by_kind: dict[SurfaceKind, list[dict[str, Any]]] = field(
        default_factory=lambda: {"index": [], "appendix": []}
    )
    concepts: dict[str, list[ConceptBlock]] = field(default_factory=dict)
    appendix_concepts: dict[str, list[str]] = field(default_factory=dict)
    appendix_pages: dict[str, dict[int, list[str]]] = field(default_factory=dict)
    routers: list[str] = field(default_factory=list)
    router_entries: dict[str, list[RouterEntry]] = field(default_factory=dict)
    findings: list[LinterFinding] = field(default_factory=list)
    check_results: list[CheckResult] = field(default_factory=list)

    def rel_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.config.root).as_posix()
        except ValueError:
            return str(path)

    def has_error(self, *codes: str) -> bool:
        wanted = set(codes)
        return any(
            finding.severity == "error" and finding.code in wanted
            for finding in self.findings
        )

    def has_valid_surface(self, kind: SurfaceKind) -> bool:
        return any(surface.kind == kind and surface.valid for surface in self.surfaces)

    def record_check(self, check: LinterCheck, findings: list[LinterFinding]) -> None:
        self.findings.extend(findings)
        error_count = sum(1 for finding in findings if finding.severity == "error")
        warning_count = sum(1 for finding in findings if finding.severity == "warning")
        self.check_results.append(
            CheckResult(
                code=check.code,
                title=check.title,
                status="failed" if findings else "passed",
                finding_count=len(findings),
                error_count=error_count,
                warning_count=warning_count,
            )
        )

    def record_blocked(self, check: LinterCheck, gate: GateResult) -> None:
        self.check_results.append(
            CheckResult(
                code=check.code,
                title=check.title,
                status="blocked",
                reason=gate.reason,
                blocked_by=gate.blocked_by,
            )
        )

    def summary(self) -> dict[str, int]:
        return {
            "check_count": len(self.check_results),
            "passed_count": sum(1 for result in self.check_results if result.status == "passed"),
            "failed_count": sum(1 for result in self.check_results if result.status == "failed"),
            "blocked_count": sum(
                1 for result in self.check_results if result.status == "blocked"
            ),
            "finding_count": len(self.findings),
            "error_count": sum(1 for finding in self.findings if finding.severity == "error"),
            "warning_count": sum(
                1 for finding in self.findings if finding.severity == "warning"
            ),
        }


def allowed() -> GateResult:
    return GateResult(allowed=True)


def blocked(reason: str, *blocked_by: str) -> GateResult:
    return GateResult(allowed=False, reason=reason, blocked_by=tuple(blocked_by))


def build_linter_config(
    *,
    depot_paths: tuple[str, ...],
    index_paths: tuple[str, ...],
    appendix_paths: tuple[str, ...],
) -> tuple[LinterConfig, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    resolved_root = Path.cwd().resolve()
    resolved_depots = tuple(
        _resolve_under_root(resolved_root, path) for path in depot_paths
    )
    derived_index_paths: list[str] = list(index_paths)
    derived_appendix_paths: list[str] = list(appendix_paths)
    for depot_path in resolved_depots:
        if not depot_path.is_dir():
            continue
        for chapter_dir in sorted(path for path in depot_path.iterdir() if path.is_dir()):
            if chapter_dir.name == "appendix":
                continue
            if any(
                (match := INDEX_FILENAME_RE.fullmatch(path.name)) is not None
                and match.group("chapter") == chapter_dir.name
                for path in chapter_dir.glob("*.md")
            ):
                derived_index_paths.append(_relativize_under_root(resolved_root, chapter_dir))
        appendix_dir = depot_path / "appendix"
        if appendix_dir.is_dir():
            derived_appendix_paths.append(_relativize_under_root(resolved_root, appendix_dir))
    return (
        LinterConfig(
            root=resolved_root,
            depot_paths=resolved_depots,
            index_paths=tuple(
                _resolve_under_root(resolved_root, path) for path in derived_index_paths
            ),
            appendix_paths=tuple(
                _resolve_under_root(resolved_root, path) for path in derived_appendix_paths
            ),
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
) -> LinterState:
    state = LinterState(
        config=config,
        raw_depot_paths=raw_depot_paths,
        raw_index_paths=raw_index_paths,
        raw_appendix_paths=raw_appendix_paths,
    )
    for check in CHECKS:
        gate = check.gate(state)
        if not gate.allowed:
            state.record_blocked(check, gate)
            continue
        state.record_check(check, check.run(state))
    return state


def render_linter_json(state: LinterState) -> str:
    return json.dumps(_state_payload(state), indent=2)


def render_linter_text(state: LinterState) -> str:
    lines = ["Index linter"]
    if state.findings:
        lines.append("")
        lines.append("Findings:")
        for finding in state.findings:
            location = finding.path
            if finding.line is not None:
                location = f"{location}:{finding.line}"
            lines.append(
                f"- [{finding.severity.upper()}] {finding.code} @ {location} - {finding.message}"
            )

    blocked_results = [result for result in state.check_results if result.status == "blocked"]
    if blocked_results:
        lines.append("")
        lines.append("Blocked checks:")
        for result in blocked_results:
            suffix = ""
            if result.blocked_by:
                suffix = f" (blocked by: {', '.join(result.blocked_by)})"
            lines.append(f"- {result.code}: {result.reason or 'blocked'}{suffix}")

    summary = state.summary()
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
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SystemExit(f"error: path is outside the current working directory: {raw_path}") from exc
    return resolved


def _relativize_under_root(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _state_payload(state: LinterState) -> dict[str, Any]:
    return {
        "root": str(state.config.root),
        "config": {
            "depot": list(state.raw_depot_paths),
            "index": list(state.raw_index_paths),
            "appendix": list(state.raw_appendix_paths),
        },
        "surfaces": [
            {
                "kind": surface.kind,
                "path": surface.rel_path,
                "valid": surface.valid,
            }
            for surface in state.surfaces
        ],
        "files": {
            kind: list(paths)
            for kind, paths in state.files_by_kind.items()
        },
        "checks": [result.to_payload() for result in state.check_results],
        "findings": [finding.to_payload() for finding in state.findings],
        "summary": state.summary(),
        "exit_code": 1 if state.summary()["error_count"] else 0,
    }


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
        return blocked("no valid index surface is configured", SURFACE_MISSING_BY_KIND["index"])
    return allowed()


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
        return blocked("appendix filename inventory has not run", CHECK_APPENDIX_FILENAMES)
    if appendix_status == "blocked":
        return blocked("appendix filename inventory is unavailable", CHECK_APPENDIX_FILENAMES)
    if _check_status(state, CHECK_ROUTER_ENTRIES) == "blocked":
        return blocked("router entry inventory is unavailable", CHECK_ROUTER_ENTRIES)
    return allowed()


def _check_config_surfaces(state: LinterState) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    if not state.config.index_paths and not state.config.appendix_paths:
        if state.raw_depot_paths:
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


def _check_mdblocks_syntax(state: LinterState) -> list[LinterFinding]:
    findings: list[LinterFinding] = []
    for kind in ("index", "appendix"):
        surfaces = [surface for surface in state.surfaces if surface.kind == kind and surface.valid]
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
    for kind in ("index", "appendix"):
        for file_data in state.mdblock_files_by_kind[kind]:
            if Path(str(file_data["path"])).name == "000-INDEX.md":
                continue
            block_ranges = [
                (int(block["start_line"]), int(block["end_line"]))
                for block in file_data["blocks"]
            ]
            file_path = state.config.root / str(file_data["path"])
            for line_no, title in _iter_section_headings(file_path):
                if _line_in_ranges(line_no, block_ranges):
                    continue
                findings.append(
                    LinterFinding(
                        severity="warning",
                        code=BLOCK_UNANCHORED_SECTION,
                        path=str(file_data["path"]),
                        line=line_no,
                        message="Section heading is not part of a separator-anchored block.",
                        details={"heading": title},
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
    for file_data in state.mdblock_files_by_kind["index"]:
        for block in file_data["blocks"]:
            title = str(block["title"]).strip()
            concept_block = ConceptBlock(
                concept=title,
                path=str(block["path"]),
                line=int(block["start_line"]),
            )
            state.concepts.setdefault(title, []).append(concept_block)
            if not BLOCK_PATH_RE.fullmatch(title):
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
        state.appendix_pages.setdefault(concept, {}).setdefault(page, []).append(rel_path)
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
    for router_rel_path in state.routers:
        router_path = state.config.root / router_rel_path
        for line_number, line in enumerate(router_path.read_text(encoding="utf-8").splitlines(), start=1):
            match = ROUTER_ENTRY_RE.match(line.strip())
            if match is None:
                continue
            route_file = match.group("file")
            for raw_concept in match.group("concepts").split(","):
                route_concept = _parse_router_concept(raw_concept)
                concept = route_concept.concept
                if not concept:
                    continue
                state.router_entries.setdefault(concept, []).append(
                    RouterEntry(
                        concept=concept,
                        raw_concept=route_concept.raw_concept,
                        appendix_annotation_count=route_concept.appendix_annotation_count,
                        route_file=route_file,
                        router_path=router_rel_path,
                        line=line_number,
                    )
                )
                if not BLOCK_PATH_RE.fullmatch(concept):
                    findings.append(
                        LinterFinding(
                            severity="warning",
                            code=ROUTER_INVALID_CONCEPT,
                            path=router_rel_path,
                            line=line_number,
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
                route_path = (state.config.root / entry.router_path).parent / entry.route_file
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
            route_path = (state.config.root / entry.router_path).parent / entry.route_file
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


@dataclass(frozen=True)
class ParsedRouterConcept:
    concept: str
    raw_concept: str
    appendix_annotation_count: int | None


def _parse_router_concept(raw_concept: str) -> ParsedRouterConcept:
    concept = raw_concept.strip().strip("`")
    concept = concept.split(" — ", 1)[0].strip()
    annotation_count = None
    annotation_match = APPENDIX_ROUTE_ANNOTATION_RE.search(concept)
    if annotation_match is not None:
        annotation_count = int(annotation_match.group("count"))
        concept = concept[: annotation_match.start()].strip()
    return ParsedRouterConcept(
        concept=concept,
        raw_concept=raw_concept.strip(),
        appendix_annotation_count=annotation_count,
    )


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
        path
        for path in surface.path.rglob("*.md")
        if not _is_excluded(state, path)
    )


def _surface_depot_root(surface: SurfacePath) -> Path:
    path = surface.path
    if path.is_dir():
        return path.parent
    if path.name == "000-INDEX.md":
        return path.parent
    return path.parent.parent


def _iter_section_headings(path: Path) -> list[tuple[int, str]]:
    headings: list[tuple[int, str]] = []
    in_fence = False
    fence_char = ""
    fence_len = 0

    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped_left = line.lstrip()
        run_char, run_len = _fence_run(stripped_left)
        if not in_fence and run_len >= 3:
            in_fence = True
            fence_char = run_char
            fence_len = run_len
            continue
        if in_fence:
            if (
                run_char == fence_char
                and run_len >= fence_len
                and stripped_left[run_len:].strip() == ""
            ):
                in_fence = False
                fence_char = ""
                fence_len = 0
            continue

        match = SECTION_HEADING_RE.match(line)
        if match is None:
            continue
        title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2)).strip()
        headings.append((line_no, title))
    return headings


def _fence_run(stripped_line: str) -> tuple[str, int]:
    if not stripped_line:
        return ("", 0)
    char = stripped_line[0]
    if char not in ("`", "~"):
        return ("", 0)
    count = 0
    for candidate in stripped_line:
        if candidate == char:
            count += 1
        else:
            break
    return (char, count)


def _line_in_ranges(line_no: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= line_no <= end for start, end in ranges)


CHECKS: tuple[LinterCheck, ...] = (
    LinterCheck(
        code=CHECK_CONFIG_SURFACES,
        title="Configured surfaces",
        gate=_always,
        run=_check_config_surfaces,
    ),
    LinterCheck(
        code=CHECK_DISCOVER_FILES,
        title="Discover markdown files",
        gate=_needs_valid_surface,
        run=_check_discover_files,
    ),
    LinterCheck(
        code=CHECK_MDBLOCKS_SYNTAX,
        title="Markdown block syntax",
        gate=_needs_discovered_files,
        run=_check_mdblocks_syntax,
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
