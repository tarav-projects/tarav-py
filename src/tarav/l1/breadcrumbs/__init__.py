"""Opaque surface anchors with workflow-owned typed attachments."""

from .auditing import (
    AuditedBreadcrumb,
    BreadcrumbAuditContext,
    BreadcrumbAuditConcern,
    BreadcrumbAuditResult,
    SurfaceBreadcrumbLabel,
    audit_annotations,
)
from .integrations import BreadcrumbCommandAdapter, BreadcrumbIntegration
from .model import Breadcrumb, BreadcrumbId, LocatorObservation
# tarav.breadcrumb 9cf8b90c47044379094d8f71ed551105c57120dc9a16e5e12dcc61a22910d1aa
from .store import (
    LABEL_PREFIX,
    BreadcrumbAmbiguous,
    BreadcrumbError,
    BreadcrumbNotFound,
    BreadcrumbResolutionPOI,
    BreadcrumbPositionMissing,
    BreadcrumbPositionAmbiguous,
    BreadcrumbResolution,
    BreadcrumbStore,
    breadcrumb_label,
    default_breadcrumbs_root,
    parse_breadcrumb_label,
)
from .surfaces import (
    BreadcrumbSurface,
    SubmissionResult,
    SubmittedBreadcrumb,
    submit_annotations,
)
from .workflow import BreadcrumbWorkflow
from .workflows import (
    BreadcrumbAnnotationWorkflow,
    BreadcrumbAnnotationWorkflowRegistry,
    PreparedAnnotation,
    SurfaceMarker,
)

__all__ = [
    "LABEL_PREFIX",
    "Breadcrumb",
    "BreadcrumbAmbiguous",
    "BreadcrumbNotFound",
    "BreadcrumbAnnotationWorkflow",
    "BreadcrumbAnnotationWorkflowRegistry",
    "BreadcrumbAuditContext",
    "BreadcrumbAuditConcern",
    "BreadcrumbAuditResult",
    "BreadcrumbCommandAdapter",
    "BreadcrumbError",
    "BreadcrumbResolutionPOI",
    "BreadcrumbPositionMissing",
    "BreadcrumbPositionAmbiguous",
    "BreadcrumbResolution",
    "BreadcrumbStore",
    "BreadcrumbSurface",
    "BreadcrumbWorkflow",
    "BreadcrumbIntegration",
    "BreadcrumbId",
    "LocatorObservation",
    "PreparedAnnotation",
    "AuditedBreadcrumb",
    "SubmissionResult",
    "SubmittedBreadcrumb",
    "SurfaceMarker",
    "SurfaceBreadcrumbLabel",
    "audit_annotations",
    "breadcrumb_label",
    "default_breadcrumbs_root",
    "parse_breadcrumb_label",
    "submit_annotations",
]
