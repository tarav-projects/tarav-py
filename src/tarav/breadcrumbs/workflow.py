"""Breadcrumb Record and annotation-workflow registration."""

from tarav.l0.kernel import TaravClass
from tarav.l0.kernel import TypeShip
from tarav.l0.kernel.workflows import TaravWorkflow
from tarav.breadcrumbs.identity import BREADCRUMBS_WORKFLOW_SHIP

from .integrations import BreadcrumbIntegration
from .model import Breadcrumb, LocatorObservation
from .workflows import BreadcrumbAnnotationWorkflowRegistry


BREADCRUMB_RECORD_TYPES = (Breadcrumb, LocatorObservation)


class BreadcrumbWorkflow(TaravWorkflow):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('172133fa-7ec0-43f0-92f7-38ba54c45824'),
            name='Tarav.Workflow.Breadcrumbs',
            workflow=BREADCRUMBS_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return BREADCRUMBS_WORKFLOW_SHIP
    workflow_name = "breadcrumbs"
    constitution = (
        "Annotate product surfaces with stable Breadcrumbs, positions, and "
        "workflow-owned attachments."
    )

    @staticmethod
    def service(integrations: tuple[BreadcrumbIntegration, ...] = ()) -> "BreadcrumbService":
        return BreadcrumbService(integrations)


class BreadcrumbService:
    """Runtime-specific annotation integrations."""

    def __init__(
        self,
        integrations: tuple[BreadcrumbIntegration, ...] = (),
    ) -> None:
        self.integrations = integrations
        self.annotations = BreadcrumbAnnotationWorkflowRegistry(
            integration.workflow for integration in integrations
        )

__all__ = ["BreadcrumbWorkflow", "BreadcrumbService"]
