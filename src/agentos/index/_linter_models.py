from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from agentos.index.model import IndexDocument, KernelLine, parse_index_file


Severity = Literal["error", "warning"]
CheckStatus = Literal["passed", "failed", "blocked"]
SurfaceKind = Literal["index", "appendix"]


@dataclass(frozen=True)
class LinterConfig:
    root: Path
    depot_paths: tuple[Path, ...]
    index_paths: tuple[Path, ...]
    appendix_paths: tuple[Path, ...]
    coverage: frozenset[str] = frozenset()
    scope_paths: tuple[Path, ...] = ()


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
    # check-selection metadata (Impl.Req 702):
    # - default_on: whether the check runs when the caller names no selection
    # - structural: produces LinterState later checks consume; always runs,
    #   never disableable (exclude has no effect on it)
    default_on: bool = True
    structural: bool = False


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
class CoverageItem:
    path: str
    covered: bool


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
    parsed_documents: list[IndexDocument] = field(default_factory=list)
    findings: list[LinterFinding] = field(default_factory=list)
    finding_check_codes: dict[int, str] = field(default_factory=dict)
    check_results: list[CheckResult] = field(default_factory=list)
    coverage_items: dict[str, list[CoverageItem]] = field(default_factory=dict)

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

    def parsed_kernel_lines(self) -> list[tuple[IndexDocument, KernelLine]]:
        return [
            (document, node)
            for document in self.parsed_documents
            for node in document.nodes
            if isinstance(node, KernelLine)
        ]

    def record_check(self, check: LinterCheck, findings: list[LinterFinding]) -> None:
        self.findings.extend(findings)
        for finding in findings:
            self.finding_check_codes[id(finding)] = check.code
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
            "passed_count": sum(
                1 for result in self.check_results if result.status == "passed"
            ),
            "failed_count": sum(
                1 for result in self.check_results if result.status == "failed"
            ),
            "blocked_count": sum(
                1 for result in self.check_results if result.status == "blocked"
            ),
            "finding_count": len(self.findings),
            "error_count": sum(
                1 for finding in self.findings if finding.severity == "error"
            ),
            "warning_count": sum(
                1 for finding in self.findings if finding.severity == "warning"
            ),
        }


def allowed() -> GateResult:
    return GateResult(allowed=True)


def blocked(reason: str, *blocked_by: str) -> GateResult:
    return GateResult(allowed=False, reason=reason, blocked_by=tuple(blocked_by))


def path_is_or_contains(scope: Path, path: Path) -> bool:
    if path == scope:
        return True
    try:
        path.relative_to(scope)
        return True
    except ValueError:
        return False


def _surface_depot_root(surface: SurfacePath) -> Path:
    path = surface.path
    if path.is_dir():
        return path.parent
    if path.name == "000-INDEX.md":
        return path.parent
    return path.parent.parent


def parsed_linter_kernel_lines(
    state: LinterState,
) -> list[tuple[IndexDocument, KernelLine]]:
    """Public parser-backed kernel-line feed for core and external linter checks."""
    _ensure_parsed_documents(state)
    return state.parsed_kernel_lines()


def _ensure_parsed_documents(state: LinterState) -> None:
    parsed_paths = {document.path for document in state.parsed_documents}
    for path, surface_kind in _parser_surface_files(state):
        if path in parsed_paths:
            continue
        try:
            state.parsed_documents.append(
                parse_index_file(path, surface_kind=surface_kind)
            )
            parsed_paths.add(path)
        except OSError:
            continue


def _parser_surface_files(state: LinterState) -> list[tuple[Path, str]]:
    seen: set[Path] = set()
    typed_files: list[tuple[Path, str]] = []
    for depot in state.config.depot_paths:
        router = depot / "000-INDEX.md"
        if router.is_file() and router not in seen:
            seen.add(router)
            typed_files.append((router, "router"))
    for router_rel_path in state.routers:
        router = state.config.root / router_rel_path
        if router.is_file() and router not in seen:
            seen.add(router)
            typed_files.append((router, "router"))
    for paths, surface_kind in (
        (state.config.index_paths, "chapter"),
        (state.config.appendix_paths, "appendix"),
    ):
        for surface in paths:
            if surface.is_file():
                candidates = [surface]
            elif surface.is_dir():
                candidates = sorted(surface.glob("*.md"))
            else:
                continue
            for path in candidates:
                if path.name != "AGENTS.md" and path not in seen:
                    seen.add(path)
                    typed_files.append((path, surface_kind))
    agendix_dirs = {
        appendix.parent / "agendix" for appendix in state.config.appendix_paths
    }
    agendix_dirs.update(depot / "agendix" for depot in state.config.depot_paths)
    for agendix_dir in sorted(agendix_dirs):
        if not agendix_dir.is_dir():
            continue
        for path in sorted(agendix_dir.glob("*.md")):
            if path.name != "AGENTS.md" and path not in seen:
                seen.add(path)
                typed_files.append((path, "agendix"))
    return typed_files
