"""CLI adapter for the Chatlas Context Breadcrumb workflow."""

from __future__ import annotations

import argparse
from collections.abc import Callable
import json
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l1.breadcrumbs.commands import (
    register_audit_command,
    register_submission_command,
)
from tarav.l1.breadcrumbs import BreadcrumbError, BreadcrumbStore
from tarav.l1.breadcrumbs.workflows import BreadcrumbAnnotationWorkflow
from tarav.l1.poi.rendering import POIRenderError, POISelection, renderer
from tarav.l1.poi.reporting import retain_presented_pois

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
    *,
    commit_auditor: Callable[..., object] | None = None,
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
    if commit_auditor is not None:
        parser.add_argument("--commit")
        parser.add_argument("--repo")
        file_handler = parser.get_default("handler")
        parser.set_defaults(
            handler=_audit_dispatch,
            breadcrumb_file_audit_handler=file_handler,
            breadcrumb_commit_auditor=commit_auditor,
        )
    else:
        parser.set_defaults(commit=None, repo=None)


# tarav.breadcrumb 1e8258ee6485cebe0f7d899a1c691162632236275a5acb2388a9a94e56c621e7
def _audit_dispatch(args: argparse.Namespace) -> int:
    # tarav.breadcrumb 2fca27c41ee9a7bc4256a20ada664c0e38406ef56fb1dc2147899e0493733868
    if args.commit is None:
        if (not args.surface and not args.files_from) or args.repo is not None:
            raise CliError("File audit requires --surface or --files-from and does not accept --repo")
        return int(args.breadcrumb_file_audit_handler(args))
    if args.surface or args.files_from or args.repo is None:
        raise CliError("Commit audit requires --commit and --repo without file-selection options")
    if args.refresh_positions:
        raise CliError("--refresh-positions is only supported for file audits")
    try:
        result = args.breadcrumb_commit_auditor(
            args.repo,
            args.commit,
            store=BreadcrumbStore(args.breadcrumbs_root),
            workflow=args.breadcrumb_annotation_workflow,
            request=_audit_request(args),
        )
    except (BreadcrumbError, OSError, TypeError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    payload = result.to_json()
    payload["command"] = "tarav breadcrumbs audit chatlas-context"
    payload["repository"] = str(Path(args.repo).expanduser().resolve())
    payload["commit"] = args.commit
    retain_presented_pois(result.pois, kind="breadcrumbs-commit",
                          name="chatlas-context", root=args.repo)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"status: {payload['status']}")
        print(f"commit: {args.commit}")
        print(f"breadcrumbs: {len(result.context.breadcrumbs)}")
        if result.pois:
            try:
                print(renderer(args.renderer).render(
                    POISelection.from_pois(result.pois, title="Breadcrumb POIs"),
                    level=args.level))
            except POIRenderError as exc:
                raise CliError(str(exc)) from exc
    return 0 if result.ok else 1


__all__ = [
    "register_chatlas_context_audit",
    "register_chatlas_context_submission",
]
