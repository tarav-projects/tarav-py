"""Breadcrumb Record and annotation-workflow registration."""

from tarav.harness.workflows import Workflow, WorkflowRegistry

from .integrations import BreadcrumbIntegration
from .model import Breadcrumb, LocatorObservation
from .workflows import BreadcrumbAnnotationWorkflowRegistry


class BreadcrumbWorkflow(Workflow):
    name = "breadcrumbs"
    record_types = (Breadcrumb, LocatorObservation)

    def __init__(
        self,
        integrations: tuple[BreadcrumbIntegration, ...] = (),
    ) -> None:
        self.integrations = integrations
        self.annotations = BreadcrumbAnnotationWorkflowRegistry(
            integration.workflow for integration in integrations
        )

    def register(self, registry: WorkflowRegistry) -> None:
        super().register(registry)
        for workflow in self.annotations.workflows.values():
            for record_type in workflow.record_types:
                registry.records.register(record_type)


__all__ = ["BreadcrumbWorkflow"]
