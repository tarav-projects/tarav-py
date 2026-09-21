"""Opaque surface anchors with workflow-owned typed attachments."""

from .auditing import (
    AuditedBreadcrumb,
    BreadcrumbAuditContext,
    BreadcrumbAuditFinding,
    BreadcrumbAuditResult,
    SurfaceBreadcrumbLabel,
    audit_annotations,
)
from .integrations import BreadcrumbCommandAdapter, BreadcrumbIntegration
from .model import Breadcrumb, BreadcrumbId, LocatorObservation
from .store import (
    BreadcrumbError,
    BreadcrumbFinding,
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
    "Breadcrumb",
    "BreadcrumbAnnotationWorkflow",
    "BreadcrumbAnnotationWorkflowRegistry",
    "BreadcrumbAuditContext",
    "BreadcrumbAuditFinding",
    "BreadcrumbAuditResult",
    "BreadcrumbCommandAdapter",
    "BreadcrumbError",
    "BreadcrumbFinding",
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
