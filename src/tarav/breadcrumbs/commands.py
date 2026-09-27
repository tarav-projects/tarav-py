"""CLI adapter for Breadcrumb stores and surface submission."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence

from tarav.l0._core.errors import CliError

from .auditing import audit_annotations
from .integrations import BreadcrumbIntegration
from .store import BreadcrumbError, BreadcrumbStore
from .surfaces import submit_annotations
from .workflows import BreadcrumbAnnotationWorkflow


RequestFactory = Callable[[argparse.Namespace], object]


def _store(args: argparse.Namespace) -> BreadcrumbStore:
    return BreadcrumbStore(args.breadcrumbs_root)


def _print(
    args: argparse.Namespace, payload: dict[str, object], lines: tuple[str, ...]
) -> int:
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for line in lines:
            print(line)
    return 0


def _cmd_submit(args: argparse.Namespace) -> int:
    try:
        workflow = args.breadcrumb_annotation_workflow
        request_factory = args.breadcrumb_request_factory
        assert isinstance(workflow, BreadcrumbAnnotationWorkflow)
        result = submit_annotations(
            args.surface,
            store=_store(args),
            workflow=workflow,
            request=request_factory(args),
            language=args.language,
        )
    except (BreadcrumbError, OSError, TypeError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    payload = result.to_json()
    payload["command"] = f"tarav breadcrumbs submit {workflow.name}"
    payload["store"] = str(_store(args).root)
    return _print(
        args,
        payload,
        (
            f"submitted: {len(result.breadcrumbs)}",
            f"surface: {result.surface}",
            f"store: {_store(args).root}",
        ),
    )


def _cmd_audit(args: argparse.Namespace) -> int:
    try:
        workflow = args.breadcrumb_annotation_workflow
        request_factory = args.breadcrumb_request_factory
        assert isinstance(workflow, BreadcrumbAnnotationWorkflow)
        result = audit_annotations(
            args.surface,
            store=_store(args),
            workflow=workflow,
            request=request_factory(args),
            language=args.language,
        )
    except (BreadcrumbError, OSError, TypeError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    payload = result.to_json()
    payload["command"] = f"tarav breadcrumbs audit {workflow.name}"
    payload["store"] = str(_store(args).root)
    lines = [
        f"status: {payload['status']}",
        f"surface: {result.context.surface.path}",
        f"breadcrumbs: {len(result.context.breadcrumbs)}",
    ]
    lines.extend(
        f"poi: {finding.code}: {finding.message}" for finding in result.findings
    )
    _print(args, payload, tuple(lines))
    return 0 if result.ok else 1


def _cmd_workflows(
    args: argparse.Namespace,
    integrations: Sequence[BreadcrumbIntegration],
) -> int:
    items = tuple(
        {
            "name": integration.workflow.name,
            "capabilities": list(integration.commands.capabilities),
        }
        for integration in sorted(integrations, key=lambda item: item.workflow.name)
    )
    return _print(
        args,
        {
            "status": "ok",
            "command": "tarav breadcrumbs workflows",
            "workflows": list(items),
        },
        tuple(
            f"{integration.workflow.name}  "
            f"{','.join(integration.commands.capabilities)}"
            for integration in sorted(
                integrations,
                key=lambda item: item.workflow.name,
            )
        ),
    )


def _cmd_show(args: argparse.Namespace) -> int:
    try:
        payload = {
            "status": "ok",
            "command": "tarav breadcrumbs show",
            "store": str(_store(args).root),
            **_store(args).show(args.label),
        }
    except (BreadcrumbError, OSError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    breadcrumb = payload["breadcrumb"]
    assert isinstance(breadcrumb, dict)
    return _print(
        args,
        payload,
        (
            f"breadcrumb: {breadcrumb['id']}",
            f"observations: {len(payload['observations'])}",  # type: ignore[arg-type]
            f"attachments: {len(payload['attachments'])}",  # type: ignore[arg-type]
        ),
    )


def _cmd_resolve(args: argparse.Namespace) -> int:
    try:
        resolution = _store(args).resolve(args.label)
    except (BreadcrumbError, OSError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    payload = {
        "command": "tarav breadcrumbs resolve",
        "store": str(_store(args).root),
        **resolution.to_json(),
    }
    lines = [f"status: {resolution.status}"]
    if resolution.position is not None:
        lines.append(f"position: {resolution.position.path}:{resolution.position.line}")
    else:
        lines.extend(
            f"poi: {finding.code}: {finding.message}" for finding in resolution.findings
        )
    _print(args, payload, tuple(lines))
    return 0 if resolution.ok else 1


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--breadcrumbs-root", help="Breadcrumb store root override.")
    parser.add_argument("--json", action="store_true")


def register_submission_command(
    subparsers: argparse._SubParsersAction,
    *,
    workflow: BreadcrumbAnnotationWorkflow,
    request_factory: RequestFactory,
    help_text: str,
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(workflow.name, help=help_text)
    parser.add_argument("--surface", required=True)
    parser.add_argument("--language", choices=("markdown", "python"))
    _add_common(parser)
    parser.set_defaults(
        handler=_cmd_submit,
        breadcrumb_annotation_workflow=workflow,
        breadcrumb_request_factory=request_factory,
    )
    return parser


def register_audit_command(
    subparsers: argparse._SubParsersAction,
    *,
    workflow: BreadcrumbAnnotationWorkflow,
    request_factory: RequestFactory,
    help_text: str,
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(workflow.name, help=help_text)
    parser.add_argument("--surface", required=True)
    parser.add_argument("--language", choices=("markdown", "python"))
    _add_common(parser)
    parser.set_defaults(
        handler=_cmd_audit,
        breadcrumb_annotation_workflow=workflow,
        breadcrumb_request_factory=request_factory,
    )
    return parser


def register_breadcrumb_commands(
    subparsers: argparse._SubParsersAction,
    *,
    integrations: Sequence[BreadcrumbIntegration],
) -> None:
    parser = subparsers.add_parser(
        "breadcrumbs",
        help="Create and resolve opaque annotations embedded in Product.Surfaces.",
    )
    commands = parser.add_subparsers(dest="breadcrumbs_command", required=True)

    submit = commands.add_parser(
        "submit",
        help="Submit provisional annotations through a registered workflow.",
    )
    submit_workflows = submit.add_subparsers(
        dest="breadcrumb_submit_workflow",
        required=True,
    )
    for integration in integrations:
        integration.commands.register_submit(
            submit_workflows,
            integration.workflow,
        )

    audit = commands.add_parser(
        "audit",
        help="Audit retained annotations through their owning workflow.",
    )
    audit_workflows = audit.add_subparsers(
        dest="breadcrumb_audit_workflow",
        required=True,
    )
    for integration in integrations:
        integration.commands.register_audit(
            audit_workflows,
            integration.workflow,
        )

    listed = commands.add_parser(
        "workflows",
        help="List registered Breadcrumb annotation workflows.",
    )
    listed.add_argument("--json", action="store_true")
    listed.set_defaults(handler=lambda args: _cmd_workflows(args, integrations))

    resolve = commands.add_parser(
        "resolve", help="Resolve a Breadcrumb label to its observed surface position."
    )
    resolve.add_argument("--label", required=True)
    _add_common(resolve)
    resolve.set_defaults(handler=_cmd_resolve)

    show = commands.add_parser(
        "show", help="Show a Breadcrumb, its observation history, and attachments."
    )
    show.add_argument("--label", required=True)
    _add_common(show)
    show.set_defaults(handler=_cmd_show)


__all__ = [
    "RequestFactory",
    "register_audit_command",
    "register_breadcrumb_commands",
    "register_submission_command",
]
