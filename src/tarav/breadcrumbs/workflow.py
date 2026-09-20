"""Breadcrumb Record registration."""

from tarav.harness.workflows import Workflow

from .model import Breadcrumb, ChatlasContextAttachment, LocatorObservation


class BreadcrumbWorkflow(Workflow):
    name = "breadcrumbs"
    record_types = (Breadcrumb, LocatorObservation, ChatlasContextAttachment)


__all__ = ["BreadcrumbWorkflow"]
