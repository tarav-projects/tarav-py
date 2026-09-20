"""Opaque surface anchors with workflow-owned typed attachments."""

from .model import Breadcrumb, ChatlasContextAttachment, LocatorObservation
from .store import (
    BreadcrumbError,
    BreadcrumbFinding,
    BreadcrumbResolution,
    BreadcrumbStore,
    breadcrumb_label,
    default_breadcrumbs_root,
    parse_breadcrumb_label,
)
from .surfaces import SubmissionResult, SubmittedBreadcrumb, submit_chatlas_context
from .workflow import BreadcrumbWorkflow

__all__ = [
    "Breadcrumb",
    "BreadcrumbError",
    "BreadcrumbFinding",
    "BreadcrumbResolution",
    "BreadcrumbStore",
    "BreadcrumbWorkflow",
    "ChatlasContextAttachment",
    "LocatorObservation",
    "SubmissionResult",
    "SubmittedBreadcrumb",
    "breadcrumb_label",
    "default_breadcrumbs_root",
    "parse_breadcrumb_label",
    "submit_chatlas_context",
]
