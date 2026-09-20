"""CLI adapter for Breadcrumb stores and surface submission."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarav._core.errors import CliError
from tarav.chatlas.query import ChatlasQueryError

from .store import BreadcrumbError, BreadcrumbStore
from .surfaces import submit_chatlas_context


def _store(args: argparse.Namespace) -> BreadcrumbStore:
    return BreadcrumbStore(args.breadcrumbs_root)


def _print(args: argparse.Namespace, payload: dict[str, object], lines: tuple[str, ...]) -> int:
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for line in lines:
            print(line)
    return 0


def _cmd_submit(args: argparse.Namespace) -> int:
    try:
        result = submit_chatlas_context(
            args.surface,
            store=_store(args),
            language=args.language,
            provider=args.provider,
            session_id=args.session_id,
            instance=args.instance,
            chatlas_root=Path(args.chatlas_root).expanduser() if args.chatlas_root else None,
        )
    except (BreadcrumbError, ChatlasQueryError, OSError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    payload = result.to_json()
    payload["command"] = "tarav breadcrumbs submit"
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
        lines.extend(f"poi: {finding.code}: {finding.message}" for finding in resolution.findings)
    _print(args, payload, tuple(lines))
    return 0 if resolution.ok else 1


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--breadcrumbs-root", help="Breadcrumb store root override.")
    parser.add_argument("--json", action="store_true")


def register_breadcrumb_commands(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "breadcrumbs",
        help="Create and resolve opaque annotations embedded in Product.Surfaces.",
    )
    commands = parser.add_subparsers(dest="breadcrumbs_command", required=True)

    submit = commands.add_parser(
        "submit",
        help="Resolve provisional Chatlas context markers and write Breadcrumb labels.",
    )
    submit.add_argument("--surface", required=True)
    submit.add_argument("--language", choices=("markdown", "python"))
    submit.add_argument("--provider")
    submit.add_argument("--session-id")
    submit.add_argument("--instance")
    submit.add_argument("--chatlas-root")
    _add_common(submit)
    submit.set_defaults(handler=_cmd_submit)

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


__all__ = ["register_breadcrumb_commands"]
