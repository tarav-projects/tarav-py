"""Read-only inspection of retained Breadcrumbs on one Product.Surface."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import re

from tarav.harness import TaravPOIInstance
from tarav.surfaces.markdown import normalize_markdown
from tarav.surfaces.python import normalize_python

from .store import BreadcrumbError, BreadcrumbResolution, BreadcrumbStore
from .surfaces import BreadcrumbSurface, infer_surface_language
from .workflows import BreadcrumbAnnotationWorkflow


_BREADCRUMB_CORE = r"tarav\.breadcrumb\s+([0-9a-f]{64})"
_MARKDOWN_BREADCRUMB = re.compile(rf"^\s*<!--\s*{_BREADCRUMB_CORE}\s*-->\s*$")
_PYTHON_BREADCRUMB = re.compile(rf"#\s*{_BREADCRUMB_CORE}\s*$")


@dataclass(frozen=True, slots=True)
class SurfaceBreadcrumbLabel:
    breadcrumb_id: str
    line: int
    label: str


@dataclass(frozen=True, slots=True)
class BreadcrumbAuditFinding(TaravPOIInstance):
    code: str
    message: str
    breadcrumb_id: str | None = None
    line: int | None = None

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "class": "Tarav.POI.Instance",
            "code": self.code,
            "message": self.message,
        }
        if self.breadcrumb_id is not None:
            payload["breadcrumb_id"] = self.breadcrumb_id
        if self.line is not None:
            payload["line"] = self.line
        return payload


@dataclass(frozen=True, slots=True)
class AuditedBreadcrumb:
    breadcrumb_id: str
    line: int
    label: str
    resolution: BreadcrumbResolution | None
    observations: tuple[Mapping[str, object], ...] = ()
    attachments: tuple[Mapping[str, object], ...] = ()

    def to_json(self) -> dict[str, object]:
        position: dict[str, object] | None = None
        status = "missing"
        if self.resolution is not None:
            status = self.resolution.status
            if self.resolution.position is not None:
                position = {
                    "file": str(self.resolution.position.path),
                    "line": self.resolution.position.line,
                    "text": self.resolution.position.text,
                }
        return {
            "id": self.breadcrumb_id,
            "line": self.line,
            "label": self.label,
            "status": status,
            "position": position,
            "observations": [dict(item) for item in self.observations],
            "attachments": [dict(item) for item in self.attachments],
        }


@dataclass(frozen=True, slots=True)
class BreadcrumbAuditContext:
    surface: BreadcrumbSurface
    breadcrumbs: tuple[AuditedBreadcrumb, ...]


@dataclass(frozen=True, slots=True)
class BreadcrumbAuditResult:
    context: BreadcrumbAuditContext
    workflow: str
    findings: tuple[BreadcrumbAuditFinding, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.findings

    def to_json(self) -> dict[str, object]:
        return {
            "status": "ok" if self.ok else "pois",
            "workflow": self.workflow,
            "surface": str(self.context.surface.path),
            "language": self.context.surface.language,
            "breadcrumbs": [item.to_json() for item in self.context.breadcrumbs],
            "findings": [item.to_json() for item in self.findings],
        }


def audit_annotations(
    surface: str | Path,
    *,
    store: BreadcrumbStore,
    workflow: BreadcrumbAnnotationWorkflow,
    request: object,
    language: str | None = None,
) -> BreadcrumbAuditResult:
    path = Path(surface).expanduser().resolve()
    if not path.is_file():
        raise BreadcrumbError(f"Surface is not a file: {path}")
    document = BreadcrumbSurface(
        path,
        language or infer_surface_language(path),
        path.read_text(encoding="utf-8"),
    )
    labels, findings = _surface_labels(document)
    audited: list[AuditedBreadcrumb] = []
    for label in labels:
        resolution: BreadcrumbResolution | None = None
        observations: tuple[Mapping[str, object], ...] = ()
        attachments: tuple[Mapping[str, object], ...] = ()
        try:
            resolution = store.resolve(label.breadcrumb_id)
            observations = store.observations(label.breadcrumb_id)
            attachments = store.attachments(label.breadcrumb_id)
        except (BreadcrumbError, OSError, TypeError, ValueError) as exc:
            findings.append(
                BreadcrumbAuditFinding(
                    "breadcrumb-record-unavailable",
                    str(exc),
                    label.breadcrumb_id,
                    label.line,
                )
            )
        else:
            for finding in resolution.findings:
                findings.append(
                    BreadcrumbAuditFinding(
                        finding.code,
                        finding.message,
                        label.breadcrumb_id,
                        label.line,
                    )
                )
            if resolution.position is not None and (
                resolution.position.path.resolve() != path
                or resolution.position.line != label.line
            ):
                findings.append(
                    BreadcrumbAuditFinding(
                        "breadcrumb-position-disagrees",
                        "Resolved Breadcrumb position disagrees with this surface label.",
                        label.breadcrumb_id,
                        label.line,
                    )
                )
            if not attachments:
                findings.append(
                    BreadcrumbAuditFinding(
                        "breadcrumb-attachment-missing",
                        "Breadcrumb has no retained workflow attachment.",
                        label.breadcrumb_id,
                        label.line,
                    )
                )
        audited.append(
            AuditedBreadcrumb(
                label.breadcrumb_id,
                label.line,
                label.label,
                resolution,
                observations,
                attachments,
            )
        )
    context = BreadcrumbAuditContext(document, tuple(audited))
    findings.extend(workflow.audit(context, request))
    return BreadcrumbAuditResult(context, workflow.name, tuple(findings))


def _surface_labels(
    surface: BreadcrumbSurface,
) -> tuple[tuple[SurfaceBreadcrumbLabel, ...], list[BreadcrumbAuditFinding]]:
    candidates: list[tuple[int, str]] = []
    if surface.language == "markdown":
        model = normalize_markdown(surface.text)
        fenced = model.fenced_line_numbers()
        candidates.extend(
            (item.span.start_line, item.text)
            for item in model.lines
            if item.span.start_line not in fenced
            and "<!--" in item.text
            and "tarav.breadcrumb" in item.text
        )
        pattern = _MARKDOWN_BREADCRUMB
    elif surface.language == "python":
        model = normalize_python(surface.text)
        if model.diagnostics:
            raise BreadcrumbError(
                "Python surface has normalization diagnostics: "
                + "; ".join(item.message for item in model.diagnostics)
            )
        candidates.extend(
            (item.span.start_line, item.text)
            for item in model.comments
            if "tarav.breadcrumb" in item.text
        )
        pattern = _PYTHON_BREADCRUMB
    else:
        raise BreadcrumbError("Breadcrumb surface language must be markdown or python")

    labels: list[SurfaceBreadcrumbLabel] = []
    findings: list[BreadcrumbAuditFinding] = []
    for line, text in candidates:
        match = pattern.fullmatch(text)
        if match is None:
            findings.append(
                BreadcrumbAuditFinding(
                    "breadcrumb-label-malformed",
                    "Surface comment contains a malformed Breadcrumb label.",
                    line=line,
                )
            )
            continue
        breadcrumb_id = match.group(1)
        labels.append(
            SurfaceBreadcrumbLabel(
                breadcrumb_id,
                line,
                f"tarav.breadcrumb {breadcrumb_id}",
            )
        )
    return tuple(labels), findings


__all__ = [
    "AuditedBreadcrumb",
    "BreadcrumbAuditContext",
    "BreadcrumbAuditFinding",
    "BreadcrumbAuditResult",
    "SurfaceBreadcrumbLabel",
    "audit_annotations",
]
