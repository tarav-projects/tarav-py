"""CLI adapter for Breadcrumb stores and surface submission."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l1.poi.rendering import (
    DEFAULT_POI_RENDERER, POIRenderError, POISelection, renderer,
)

from .auditing import audit_annotations
from .integrations import BreadcrumbIntegration
from .store import BreadcrumbError, BreadcrumbStore
from .surfaces import SURFACE_LANGUAGES, submit_annotations
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


def _render_pois(pois, args: argparse.Namespace) -> str:
    try:
        return renderer(args.renderer).render(
            POISelection.from_pois(pois, title="Breadcrumb POIs"), level=args.level)
    except POIRenderError as exc:
        raise CliError(str(exc)) from exc


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


# tarav.breadcrumb 2d4af9cff1b5
# tarav.breadcrumb 9e49acb899c1
def _audit_paths(args: argparse.Namespace) -> tuple[Path, ...]:
    paths = list(args.surface or ())
    if args.files_from:
        manifest = Path(args.files_from).expanduser()
        try:
            paths.extend(line.strip() for line in manifest.read_text(encoding="utf-8").splitlines()
                         if line.strip())
        except OSError as exc:
            raise CliError(f"Cannot read audit manifest {manifest}: {exc}") from exc
    selected = tuple(dict.fromkeys(Path(path).expanduser().resolve() for path in paths))
    if not selected:
        raise CliError("File audit requires --surface or --files-from")
    return selected


def _audit_file(args: argparse.Namespace, surface: Path) -> tuple[dict[str, object], tuple, bool]:
    workflow = args.breadcrumb_annotation_workflow
    request_factory = args.breadcrumb_request_factory
    assert isinstance(workflow, BreadcrumbAnnotationWorkflow)
    result = audit_annotations(
        surface,
        store=_store(args),
        workflow=workflow,
        request=request_factory(args),
        language=args.language,
        refresh_positions=args.refresh_positions,
    )
    payload = result.to_json()
    payload["command"] = f"tarav breadcrumbs audit {workflow.name}"
    payload["store"] = str(_store(args).root)
    return payload, result.pois, result.ok


def _cmd_audit(args: argparse.Namespace) -> int:
    paths = _audit_paths(args)
    batch = len(args.surface or ()) != 1 or args.files_from is not None
    if not batch:
        try:
            payload, pois, ok = _audit_file(args, paths[0])
        except (BreadcrumbError, OSError, TypeError, ValueError) as exc:
            raise CliError(str(exc)) from exc
        lines = [f"status: {payload['status']}", f"surface: {payload['surface']}",
                 f"breadcrumbs: {len(payload['breadcrumbs'])}"]
        if pois:
            lines.append(_render_pois(pois, args))
        _print(args, payload, tuple(lines))
        return 0 if ok else 1

    files: list[dict[str, object]] = []
    lines: list[str] = []
    all_ok = True
    for path in paths:
        try:
            payload, pois, ok = _audit_file(args, path)
        except (BreadcrumbError, OSError, TypeError, ValueError) as exc:
            payload, pois, ok = {"status": "error", "surface": str(path),
                                 "error": str(exc)}, (), False
        files.append(payload)
        all_ok = all_ok and ok
        lines.append(f"{payload['status']}: {path}")
        if payload.get("error"):
            lines.append(f"  {payload['error']}")
        elif pois:
            lines.append(_render_pois(pois, args))
    errors = sum(item["status"] == "error" for item in files)
    output = {
        "status": "error" if errors else "ok" if all_ok else "pois",
        "command": f"tarav breadcrumbs audit {args.breadcrumb_annotation_workflow.name}",
        "store": str(_store(args).root),
        "files": files,
        "summary": {"files": len(files),
                    "ok": sum(item["status"] == "ok" for item in files),
                    "pois": sum(len(item.get("pois", ())) for item in files),
                    "errors": errors},
    }
    _print(args, output, tuple(lines))
    return 0 if all_ok else 1


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
    if resolution.pois:
        lines.append(_render_pois(resolution.pois, args))
    _print(args, payload, tuple(lines))
    return 0 if resolution.ok else 1


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--breadcrumbs-root", help="Breadcrumb store root override.")
    parser.add_argument("--json", action="store_true")


def _add_poi_render_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--renderer", default=DEFAULT_POI_RENDERER)
    parser.add_argument("--level", choices=("line", "record"), default="line")


def register_submission_command(
    subparsers: argparse._SubParsersAction,
    *,
    workflow: BreadcrumbAnnotationWorkflow,
    request_factory: RequestFactory,
    help_text: str,
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(workflow.name, help=help_text)
    parser.add_argument("--surface", required=True)
    parser.add_argument("--language", choices=SURFACE_LANGUAGES)
    _add_common(parser)
    parser.set_defaults(
        handler=_cmd_submit,
        usage_descriptor=lambda args: {
            "surface": args.surface,
            **({"language": args.language} if args.language else {}),
        },
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
    parser.add_argument("--surface", action="append", help="Surface to audit; repeat for several files.")
    parser.add_argument("--files-from", help="Read one surface path per line from a UTF-8 manifest.")
    parser.add_argument("--language", choices=SURFACE_LANGUAGES)
    parser.add_argument(
        "--refresh-positions",
        action="store_true",
        help="Append repaired file-position observations for uniquely located stale Breadcrumbs; leave the surface unchanged.",
    )
    _add_common(parser)
    _add_poi_render_options(parser)
    parser.set_defaults(
        handler=_cmd_audit,
        usage_descriptor=lambda args: {
            **({"surface": args.surface[0] if len(args.surface) == 1 else args.surface}
               if args.surface else {}),
            **({"files_from": args.files_from} if args.files_from else {}),
            **({"repo": args.repo, "commit": args.commit}
               if getattr(args, "commit", None) else {}),
            **({"language": args.language} if args.language else {}),
            **({"refresh_positions": True} if args.refresh_positions else {}),
        },
        breadcrumb_annotation_workflow=workflow,
        breadcrumb_request_factory=request_factory,
    )
    return parser


def register_breadcrumb_commands(
    subparsers: argparse._SubParsersAction,
    *,
    integrations: Sequence[BreadcrumbIntegration],
    command_registrars: Sequence[
        Callable[[argparse._SubParsersAction], None]
    ] = (),
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
    _add_poi_render_options(resolve)
    resolve.set_defaults(handler=_cmd_resolve)

    show = commands.add_parser(
        "show", help="Show a Breadcrumb, its observation history, and attachments."
    )
    show.add_argument("--label", required=True)
    _add_common(show)
    show.set_defaults(handler=_cmd_show)

    for registrar in command_registrars:
        registrar(commands)


__all__ = [
    "RequestFactory",
    "register_audit_command",
    "register_breadcrumb_commands",
    "register_submission_command",
]
