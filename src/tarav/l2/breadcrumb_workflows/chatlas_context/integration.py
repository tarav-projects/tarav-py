"""Complete Breadcrumb integration bundle for Chatlas User-Turn context."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from tarav.l1.breadcrumbs.integrations import (
    BreadcrumbCommandAdapter,
    BreadcrumbIntegration,
)
from tarav.l1.breadcrumbs.workflows import BreadcrumbAnnotationWorkflow

from .workflow import ChatlasContextBreadcrumbWorkflow

if TYPE_CHECKING:
    import argparse


class ChatlasContextCommands(BreadcrumbCommandAdapter):
    def __init__(self, commit_auditor: Callable[..., object] | None = None) -> None:
        self.commit_auditor = commit_auditor

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

        register_chatlas_context_audit(
            subparsers,
            workflow,
            commit_auditor=self.commit_auditor,
        )


def chatlas_context_integration(
    *,
    commit_auditor: Callable[..., object] | None = None,
) -> BreadcrumbIntegration:
    return BreadcrumbIntegration(
        ChatlasContextBreadcrumbWorkflow(),
        ChatlasContextCommands(commit_auditor),
    )


CHATLAS_CONTEXT = chatlas_context_integration()


__all__ = [
    "CHATLAS_CONTEXT",
    "ChatlasContextCommands",
    "chatlas_context_integration",
]
