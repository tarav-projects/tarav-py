"""Complete Breadcrumb integration bundle for Chatlas User-Turn context."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tarav.breadcrumbs.integrations import (
    BreadcrumbCommandAdapter,
    BreadcrumbIntegration,
)
from tarav.breadcrumbs.workflows import BreadcrumbAnnotationWorkflow

from .workflow import ChatlasContextBreadcrumbWorkflow

if TYPE_CHECKING:
    import argparse


class ChatlasContextCommands(BreadcrumbCommandAdapter):
    def register_submit(
        self,
        subparsers: argparse._SubParsersAction,
        workflow: BreadcrumbAnnotationWorkflow,
    ) -> None:
        from .commands import register_chatlas_context_submission

        register_chatlas_context_submission(subparsers, workflow)

    def register_audit(
        self,
        subparsers: argparse._SubParsersAction,
        workflow: BreadcrumbAnnotationWorkflow,
    ) -> None:
        from .commands import register_chatlas_context_audit

        register_chatlas_context_audit(subparsers, workflow)


CHATLAS_CONTEXT = BreadcrumbIntegration(
    ChatlasContextBreadcrumbWorkflow(),
    ChatlasContextCommands(),
)


__all__ = ["CHATLAS_CONTEXT", "ChatlasContextCommands"]
