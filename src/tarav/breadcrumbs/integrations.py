"""Complete registration units for Breadcrumb workflow integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .workflows import BreadcrumbAnnotationWorkflow

if TYPE_CHECKING:
    import argparse


class BreadcrumbCommandAdapter(ABC):
    """CLI capabilities supplied by one independently owned integration."""

    capabilities: tuple[str, ...] = ("submit", "audit")

    @abstractmethod
    def register_submit(
        self,
        subparsers: argparse._SubParsersAction,
        workflow: BreadcrumbAnnotationWorkflow,
    ) -> None: ...

    @abstractmethod
    def register_audit(
        self,
        subparsers: argparse._SubParsersAction,
        workflow: BreadcrumbAnnotationWorkflow,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class BreadcrumbIntegration:
    """One workflow together with every public command that operates it."""

    workflow: BreadcrumbAnnotationWorkflow
    commands: BreadcrumbCommandAdapter

    def __post_init__(self) -> None:
        if not isinstance(self.workflow, BreadcrumbAnnotationWorkflow):
            raise TypeError("Breadcrumb integration requires an annotation workflow")
        if not isinstance(self.commands, BreadcrumbCommandAdapter):
            raise TypeError("Breadcrumb integration requires a command adapter")
        capabilities = self.commands.capabilities
        if not capabilities or len(capabilities) != len(set(capabilities)):
            raise ValueError("Breadcrumb integration capabilities must be unique")


__all__ = ["BreadcrumbCommandAdapter", "BreadcrumbIntegration"]
