"""Inspect Breadcrumbs, optionally recording refreshed file positions."""

from __future__ import annotations

from collections.abc import Mapping
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re

from tarav.l0.kernel import TaravClass, entity
from tarav.l0.kernel import TypeShip
from tarav.l1.checks import Check, CheckPOI, CheckResult
from tarav.l1.poi import NotificationPOI, POI, POIDetails
from tarav.l1.surfaces.markdown import MarkdownNormalModel
from tarav.l1.surfaces.python import PythonNormalModel
from tarav.l1.references.git import GitCommitMessagePositionTarget

from .store import BreadcrumbError, BreadcrumbResolution, BreadcrumbStore
from .identity import BREADCRUMBS_WORKFLOW_SHIP
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
class BreadcrumbAuditConcern:
    """Transient input to the bound audit Check, never a retained POI."""

    code: str
    message: str
    breadcrumb_id: str | None = None
    line: int | None = None

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
            if hasattr(self.resolution.position, "path"):
                position = {
                    "file": str(self.resolution.position.path),
                    "line": self.resolution.position.line,
                    "text": self.resolution.position.text,
                }
            elif isinstance(
                self.resolution.position, GitCommitMessagePositionTarget
            ):
                position = {
                    "repository": str(self.resolution.position.repository),
                    "commit": self.resolution.position.commit,
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


# tarav.breadcrumb 43e2d650575b47a3589da47e2f062ae65d74c9238883b59137993caa52c4f0fd
class BreadcrumbAuditCheck(Check):
    """Run the owning workflow's audit and report its bounded concerns."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls,
                          id=TypeShip('6962e10b-d96d-4434-b647-9cb41165a7df'),
                          name='Tarav.Breadcrumbs.Audit.Check',
                          workflow=BREADCRUMBS_WORKFLOW_SHIP)

    def __init__(self, context: BreadcrumbAuditContext,
                 concerns: tuple[BreadcrumbAuditConcern, ...],
                 workflow: BreadcrumbAnnotationWorkflow, request: object):
        super().__init__()
        self.audit_context = context
        self.concerns = concerns
        self.annotation_workflow = workflow
        self.request = request

    def _run(self) -> CheckResult:
        concerns = (*self.concerns, *self.annotation_workflow.audit(
            self.audit_context, self.request))

        def poi(item):
            details = {'surface': str(self.audit_context.surface.path),
                       **({'breadcrumb_id': item.breadcrumb_id}
                          if item.breadcrumb_id else {}),
                       **({'line': item.line} if item.line is not None else {})}
            return CheckPOI(
                self,
                item.code,
                item.message,
                situation={'code': item.code, **details},
                details=details,
            )

        return CheckResult(self, status='completed', pois=(
            poi(item) for item in concerns
        ))

    # tarav.breadcrumb 596b1161c0983854154effc76ffa82d48ca21c56785d6915423fe9d12ff196cf
    def obj_context(self, builder) -> None:
        builder.add('audit', opener=lambda: POIDetails.records.from_record({
            'type': entity(POIDetails).name,
            'value': {
                'surface': str(self.audit_context.surface.path),
                'language': self.audit_context.surface.language,
                'breadcrumbs': len(self.audit_context.breadcrumbs),
                'concerns': len(self.concerns),
            },
        }))


@dataclass(frozen=True, slots=True)
class BreadcrumbAuditResult:
    context: BreadcrumbAuditContext
    workflow: str
    pois: tuple[POI, ...] = ()

    @classmethod
    def from_concerns(cls, context: BreadcrumbAuditContext,
                      workflow: BreadcrumbAnnotationWorkflow, request: object,
                      concerns: tuple[BreadcrumbAuditConcern, ...],
                      updates: tuple[Mapping[str, object], ...] = ()) -> 'BreadcrumbAuditResult':
        checked = BreadcrumbAuditCheck(context, concerns, workflow, request).run().pois()
        notifications = tuple(NotificationPOI(
            str(update['code']), 'Breadcrumb position observation appended.',
            details=dict(update)) for update in updates)
        return cls(context, workflow.name, (*checked, *notifications))

    @property
    def findings(self) -> tuple[CheckPOI, ...]:
        return tuple(poi for poi in self.pois if isinstance(poi, CheckPOI))

    @property
    def notifications(self) -> tuple[NotificationPOI, ...]:
        return tuple(poi for poi in self.pois if isinstance(poi, NotificationPOI))

    @property
    def ok(self) -> bool:
        return not any(poi.failure for poi in self.findings)

    def to_json(self) -> dict[str, object]:
        return {
            "status": "ok" if self.ok else "pois",
            "workflow": self.workflow,
            "surface": str(self.context.surface.path),
            "language": self.context.surface.language,
            "breadcrumbs": [item.to_json() for item in self.context.breadcrumbs],
            "pois": [item.as_dict() for item in self.pois],
        }


def audit_annotations(
    surface: str | Path,
    *,
    store: BreadcrumbStore,
    workflow: BreadcrumbAnnotationWorkflow,
    request: object,
    language: str | None = None,
    refresh_positions: bool = False,
) -> BreadcrumbAuditResult:
    """Audit without mutation by default.

    Opt-in refresh appends uniquely observed, stale locations to the store;
    it never edits the surface, identity or attachments. Updates are informational,
    not findings. Ambiguous positions and failed writes remain warnings.
    """
    path = Path(surface).expanduser().resolve()
    if not path.is_file():
        raise BreadcrumbError(f"Surface is not a file: {path}")
    document = BreadcrumbSurface(
        path,
        language or infer_surface_language(path),
        path.read_text(encoding="utf-8"),
    )
    labels, findings = _surface_labels(document)
    counts = Counter(label.breadcrumb_id for label in labels)
    updates: list[Mapping[str, object]] = []
    audited: list[AuditedBreadcrumb] = []
    for label in labels:
        resolution: BreadcrumbResolution | None = None
        observations: tuple[Mapping[str, object], ...] = ()
        attachments: tuple[Mapping[str, object], ...] = ()
        try:
            resolution = store.resolve(label.breadcrumb_id)
            if refresh_positions and counts[label.breadcrumb_id] == 1 and (
                resolution.status == "unresolvable"
            ):
                try:
                    store.observe_position(label.breadcrumb_id, file=str(path), line=label.line)
                except (BreadcrumbError, OSError, TypeError, ValueError) as exc:
                    findings.append(BreadcrumbAuditConcern(
                        "breadcrumb-position-refresh-failed", str(exc),
                        label.breadcrumb_id, label.line))
                else:
                    updates.append({"code": "breadcrumb-position-updated",
                                    "breadcrumb_id": label.breadcrumb_id,
                                    "file": str(path), "line": label.line})
                    resolution = store.resolve(label.breadcrumb_id)
            observations = store.observations(label.breadcrumb_id)
            attachments = store.attachments(label.breadcrumb_id)
        except (BreadcrumbError, OSError, TypeError, ValueError) as exc:
            findings.append(
                BreadcrumbAuditConcern(
                    "breadcrumb-record-unavailable",
                    str(exc),
                    label.breadcrumb_id,
                    label.line,
                )
            )
        else:
            for finding in resolution.findings:
                findings.append(
                    BreadcrumbAuditConcern(
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
                    BreadcrumbAuditConcern(
                        "breadcrumb-position-disagrees",
                        "Resolved Breadcrumb position disagrees with this surface label.",
                        label.breadcrumb_id,
                        label.line,
                    )
                )
            if not attachments:
                findings.append(
                    BreadcrumbAuditConcern(
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
    return BreadcrumbAuditResult.from_concerns(
        context, workflow, request, tuple(findings), tuple(updates))


def _surface_labels(
    surface: BreadcrumbSurface,
) -> tuple[tuple[SurfaceBreadcrumbLabel, ...], list[BreadcrumbAuditConcern]]:
    candidates: list[tuple[int, str]] = []
    if surface.language == "markdown":
        model = MarkdownNormalModel.from_text(surface.text)
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
        model = PythonNormalModel.from_text(surface.text)
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
    findings: list[BreadcrumbAuditConcern] = []
    for line, text in candidates:
        match = pattern.fullmatch(text)
        if match is None:
            findings.append(
                BreadcrumbAuditConcern(
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


def surface_labels(
    surface: BreadcrumbSurface,
) -> tuple[tuple[SurfaceBreadcrumbLabel, ...], list[BreadcrumbAuditConcern]]:
    """Parse exact Breadcrumb labels from an already loaded surface."""

    return _surface_labels(surface)


__all__ = [
    "AuditedBreadcrumb",
    "BreadcrumbAuditContext",
    "BreadcrumbAuditConcern",
    "BreadcrumbAuditResult",
    "SurfaceBreadcrumbLabel",
    "audit_annotations",
    "surface_labels",
]
