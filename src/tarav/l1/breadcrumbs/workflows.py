"""Plugin contract for Product.Surface Breadcrumb annotation workflows."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from tarav.l0.kernel import TaravObject

if TYPE_CHECKING:
    from .auditing import BreadcrumbAuditContext, BreadcrumbAuditConcern
    from .surfaces import BreadcrumbSurface


@dataclass(frozen=True, slots=True)
class SurfaceMarker:
    line: int
    start_column: int
    end_column: int


@dataclass(frozen=True, slots=True)
class PreparedAnnotation:
    marker: SurfaceMarker
    provisional: str
    state: object


class BreadcrumbAnnotationWorkflow(ABC):
    """One independently owned producer of Breadcrumb attachments."""

    name: str
    record_types: tuple[type[TaravObject], ...] = ()

    @abstractmethod
    def prepare(
        self,
        surface: BreadcrumbSurface,
        request: object,
    ) -> tuple[PreparedAnnotation, ...]: ...

    @abstractmethod
    def attachments(
        self,
        annotation: PreparedAnnotation,
        breadcrumb_id: str,
    ) -> tuple[Mapping[str, object], ...]: ...

    @abstractmethod
    def audit(
        self,
        context: BreadcrumbAuditContext,
        request: object,
    ) -> tuple[BreadcrumbAuditConcern, ...]: ...


class BreadcrumbAnnotationWorkflowRegistry:
    def __init__(
        self,
        workflows: Iterable[BreadcrumbAnnotationWorkflow] = (),
    ) -> None:
        self.workflows: dict[str, BreadcrumbAnnotationWorkflow] = {}
        for workflow in workflows:
            self.register(workflow)

    def register(self, workflow: BreadcrumbAnnotationWorkflow) -> None:
        if not isinstance(workflow, BreadcrumbAnnotationWorkflow):
            raise TypeError("Expected a BreadcrumbAnnotationWorkflow")
        if not workflow.name or workflow.name in self.workflows:
            raise ValueError(
                f"Invalid or duplicate Breadcrumb workflow: {workflow.name}"
            )
        self.workflows[workflow.name] = workflow

    def resolve(self, name: str) -> BreadcrumbAnnotationWorkflow:
        try:
            return self.workflows[name]
        except KeyError as exc:
            raise ValueError(f"Unknown Breadcrumb workflow: {name}") from exc


__all__ = [
    "BreadcrumbAnnotationWorkflow",
    "BreadcrumbAnnotationWorkflowRegistry",
    "PreparedAnnotation",
    "SurfaceMarker",
]
