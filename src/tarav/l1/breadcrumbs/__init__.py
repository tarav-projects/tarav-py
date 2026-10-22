"""Opaque surface anchors with workflow-owned typed attachments."""
# tarav.breadcrumb d327a10f9ce7

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
# tarav.breadcrumb 9cf8b90c4704
from .store import (
    LABEL_PREFIX,
    BreadcrumbAmbiguous,
    BreadcrumbError,
    BreadcrumbNotFound,
    BreadcrumbResolutionPOI,
    BreadcrumbPositionMissing,
    BreadcrumbPositionAmbiguous,
    BreadcrumbResolution,
    ExternalAnchorMissing,
    ExternalAnchorAmbiguous,
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
    submit_external_annotation,
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
    "submit_external_annotation",
    "ExternalAnchorMissing",
    "ExternalAnchorAmbiguous",
]
