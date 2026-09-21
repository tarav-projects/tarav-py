"""CLI adapter for the Chatlas Context Breadcrumb workflow."""

from __future__ import annotations

import argparse
from pathlib import Path

from tarav.breadcrumbs.commands import (
    register_audit_command,
    register_submission_command,
)
from tarav.breadcrumbs.workflows import BreadcrumbAnnotationWorkflow

from .workflow import ChatlasContextRequest


def _request(args: argparse.Namespace) -> ChatlasContextRequest:
    return ChatlasContextRequest(
        provider=args.provider,
        session_id=args.session_id,
        instance=args.instance,
        chatlas_root=(
            Path(args.chatlas_root).expanduser() if args.chatlas_root else None
        ),
    )


def _audit_request(args: argparse.Namespace) -> ChatlasContextRequest:
    return ChatlasContextRequest(
        chatlas_root=(
            Path(args.chatlas_root).expanduser() if args.chatlas_root else None
        ),
    )


def register_chatlas_context_submission(
    subparsers: argparse._SubParsersAction,
    workflow: BreadcrumbAnnotationWorkflow,
) -> None:
    if workflow.name != "chatlas-context":
        raise ValueError(
            "Chatlas Context commands require the chatlas-context workflow"
        )
    parser = register_submission_command(
        subparsers,
        workflow=workflow,
        request_factory=_request,
        help_text="Resolve Chatlas User-Turn markers and write Breadcrumb labels.",
    )
    parser.add_argument("--provider")
    parser.add_argument("--session-id")
    parser.add_argument("--instance")
    parser.add_argument("--chatlas-root")


def register_chatlas_context_audit(
    subparsers: argparse._SubParsersAction,
    workflow: BreadcrumbAnnotationWorkflow,
) -> None:
    if workflow.name != "chatlas-context":
        raise ValueError(
            "Chatlas Context commands require the chatlas-context workflow"
        )
    parser = register_audit_command(
        subparsers,
        workflow=workflow,
        request_factory=_audit_request,
        help_text="Audit Breadcrumb positions and retained Chatlas User-Turn context.",
    )
    parser.add_argument("--chatlas-root")


__all__ = [
    "register_chatlas_context_audit",
    "register_chatlas_context_submission",
]
