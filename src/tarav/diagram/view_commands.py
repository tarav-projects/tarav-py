"""CLI composition for retained Diagram.View context surfaces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarav._core.errors import CliError
from tarav._core.persistence import atomic_write_text
from tarav._core.project import require_agentos_project

from . import ChatlasEvidence, DiagramConfiguration, DiagramError
from .views import (
    DIAGRAM_VIEW_TYPE,
    DiagramViewConfiguration,
    DiagramViewError,
    DiagramViewMutation,
    DiagramViewRepository,
    SessionDiagramView,
    VIEW_TYPES,
)


def _configuration(args: argparse.Namespace) -> DiagramConfiguration:
    path = (
        Path(args.diagram_config).expanduser().resolve()
        if args.diagram_config is not None
        else None
    )
    return DiagramConfiguration.load(path)


def _repository(
    args: argparse.Namespace, *, create: bool = False
) -> DiagramViewRepository:
    root = (
        Path(args.views_root).expanduser().resolve()
        if args.views_root is not None
        else None
    )
    return (
        DiagramViewRepository.create(root)
        if create
        else DiagramViewRepository.open(root)
    )


def _evidence(args: argparse.Namespace) -> ChatlasEvidence:
    root = (
        Path(args.chatlas_root).expanduser().resolve()
        if getattr(args, "chatlas_root", None) is not None
        else None
    )
    return ChatlasEvidence(chatlas_root=root)


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _emit_mutation(args: argparse.Namespace, mutation: DiagramViewMutation) -> int:
    payload = mutation.to_dict()
    rendered_blocks = mutation.view.render_blocks(
        change.target for change in mutation.changes
    )
    if args.json:
        payload["rendered_blocks"] = rendered_blocks
        _print_json(payload)
    else:
        print(f"view: {mutation.view.ship[:12]}")
        print(f"commit: {mutation.commit[:12]}")
        if rendered_blocks:
            print()
            print(rendered_blocks, end="")
        elif not mutation.changes:
            print("  no changes")
        else:
            for change in mutation.changes:
                print(change.render())
        findings = mutation.view.check()
        if findings:
            print(f"POIs: {len(findings)}")
    return 0


def _cmd_create(args: argparse.Namespace) -> int:
    try:
        diagram = _configuration(args).diagram()
        models = list(args.model_ship or ())
        if args.project is not None:
            project = require_agentos_project(project=args.project)
            models.append(diagram.project_model(project.root).ship)
        about: dict[str, object] = {}
        if args.about is not None:
            value = json.loads(Path(args.about).read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise DiagramViewError("--about must name one JSON object")
            about = value
        about.update(dict(_about_filters(args.about_field)))
        mutation = _repository(args, create=True).create_view(
            diagram,
            model_ships=models,
            block_ships=args.block_ship or (),
            view_type=args.view_type,
            about=about,
            configuration=DiagramViewConfiguration.create(
                bootstrap_visible_lines=args.bootstrap_visible_lines,
                max_visible_lines=args.max_visible_lines,
            ),
            evidence=_evidence(args),
        )
    except (DiagramError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise CliError(str(exc)) from exc
    return _emit_mutation(args, mutation)


def _cmd_list(args: argparse.Namespace) -> int:
    try:
        views = _repository(args).views()
        filters = _about_filters(args.about)
        if filters:
            views = tuple(
                view
                for view in views
                if all(str(view.about.get(key)) == value for key, value in filters)
            )
    except DiagramError as exc:
        raise CliError(str(exc)) from exc
    payload = [
        {
            "view_ship": view.ship,
            "view_type": view.view_type,
            "manifest_id": view.manifest_id,
            "scope": [
                item.model_dump(mode="json", exclude_none=True) for item in view.scopes
            ],
            "about": view.about,
            "edition": view.edition(),
            "path": str(view.root),
        }
        for view in views
    ]
    if args.json:
        _print_json({"views": payload})
    else:
        for item in payload:
            print(
                f"{str(item['view_ship'])[:12]}  "
                f"{len(item['scope'])} scope roots  {item['path']}"
            )
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    try:
        view = _repository(args).view(args.view)
    except DiagramError as exc:
        raise CliError(str(exc)) from exc
    if args.json:
        _print_json(
            {
                "manifest": view.manifest,
                "about": view.about,
                "config": view.configuration.to_json(),
                "view": view.state,
                "edition": view.edition(),
                "findings": [item.to_dict() for item in view.check()],
            }
        )
    else:
        print(view.render(), end="")
    return 0


def _cmd_peers(args: argparse.Namespace) -> int:
    try:
        repository = _repository(args)
        view = repository.view(args.view)
        hints = repository.session_peer_hints(view.ship)
    except DiagramError as exc:
        raise CliError(str(exc)) from exc
    if args.json:
        _print_json(
            {
                "view_ship": view.ship,
                "view_type": view.view_type,
                "peers": list(hints),
            }
        )
    else:
        print(f"view: {view.ship[:12]}")
        print(f"peer attention hints: {len(hints)}")
        for hint in hints:
            print(f"- view {str(hint['view_ship'])[:12]}")
            for block in hint["selected_blocks"]:
                print(
                    f"  - {block['label']} [{str(block['block_ship'])[:12]}] "
                    f"· {block['disclosure']} · "
                    f"{block['selected_line_count']} selected lines"
                )
    return 0


def _cmd_mentions(args: argparse.Namespace) -> int:
    try:
        diagram = _configuration(args).diagram()
        view = _repository(args).view(args.view)
        if not isinstance(view, SessionDiagramView):
            raise DiagramViewError("Mention inspection requires a Session.Diagram.View")
        mentions = view.mentions(diagram, _evidence(args))
    except DiagramError as exc:
        raise CliError(str(exc)) from exc
    if args.json:
        _print_json(
            {
                "view_ship": view.ship,
                "view_type": view.view_type,
                "mentions": list(mentions),
            }
        )
    else:
        print(f"view: {view.ship[:12]}")
        print(f"Diagram mentions: {len(mentions)}")
        for mention in mentions:
            standing = "present" if mention["present_in_view"] else "outside View"
            print(
                f"- {mention['label'] or mention['block_ship']} "
                f"[{str(mention['block_ship'])[:12]}] · "
                f"{mention['mention_count']} mentions · {standing}"
            )
    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    try:
        diagram = _configuration(args).diagram()
        mutation = _repository(args).synchronize(
            args.view, diagram, evidence=_evidence(args)
        )
    except DiagramError as exc:
        raise CliError(str(exc)) from exc
    return _emit_mutation(args, mutation)


def _cmd_disclose(args: argparse.Namespace) -> int:
    steps = args.steps
    if args.full:
        steps = 1000 if args.direction == "expand" else -1000
    elif args.direction == "collapse":
        steps = -steps
    try:
        diagram = _configuration(args).diagram()
        mutation = _repository(args).disclose(
            args.view,
            diagram,
            block_ship=args.block_ship,
            steps=steps,
            full=args.full,
            evidence=_evidence(args),
        )
    except DiagramError as exc:
        raise CliError(str(exc)) from exc
    return _emit_mutation(args, mutation)


def _cmd_line_selection(args: argparse.Namespace) -> int:
    try:
        diagram = _configuration(args).diagram()
        mutation = _repository(args).select_line(
            args.view,
            diagram,
            block_ship=args.block_ship,
            line_ship=args.line_ship,
            selected=args.operation == "include-line",
            evidence=_evidence(args),
        )
    except DiagramError as exc:
        raise CliError(str(exc)) from exc
    return _emit_mutation(args, mutation)


def _cmd_check(args: argparse.Namespace) -> int:
    try:
        diagram = _configuration(args).diagram()
        view = _repository(args).view(args.view)
        findings = view.check(diagram, evidence=_evidence(args))
    except DiagramError as exc:
        raise CliError(str(exc)) from exc
    if args.json:
        _print_json(
            {
                "status": "poi" if findings else "ok",
                "view_ship": view.ship,
                "findings": [item.to_dict() for item in findings],
            }
        )
    else:
        print(f"view: {view.ship[:12]}")
        print(f"POIs: {len(findings)}")
        for finding in findings:
            print(f"- {finding.code}: {finding.message}")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    try:
        view = _repository(args).view(args.view)
        content = view.render()
        if args.output is not None:
            atomic_write_text(Path(args.output).expanduser().resolve(), content)
    except (DiagramError, OSError) as exc:
        raise CliError(str(exc)) from exc
    if args.json:
        _print_json(
            {
                "renderer": "Kernel.Writing.View",
                "view_ship": view.ship,
                "media_type": "text/markdown",
                "content": content,
                "output": str(Path(args.output).expanduser().resolve())
                if args.output
                else None,
            }
        )
    elif args.output is None:
        print(content, end="")
    else:
        print(f"rendered: {Path(args.output).expanduser().resolve()}")
    return 0


def _json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )


def _about_filters(values: list[str] | None) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    for value in values or ():
        key, separator, expected = value.partition("=")
        if not separator or not key or not expected:
            raise DiagramViewError(
                "--about must use a non-empty top-level KEY=VALUE expression"
            )
        result.append((key, expected))
    return tuple(result)


def _root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--views-root",
        help="Diagram.View repository; defaults to ~/Documents/tarav/diagram/views.",
    )


def _diagram(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--diagram-config",
        help="Machine-local Diagram configuration; defaults to ~/.tarav/diagram.json.",
    )


def _chatlas(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--chatlas-root", help="Chatlas depot for review and support evidence."
    )


def _mutation_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--view", required=True, help="View UUID or unambiguous prefix."
    )
    _root(parser)
    _diagram(parser)
    _chatlas(parser)
    _json(parser)


def register_view_commands(diagram_commands: argparse._SubParsersAction) -> None:
    view = diagram_commands.add_parser(
        "view", help="Maintain retained Agent-readable context selections."
    )
    commands = view.add_subparsers(dest="diagram_view_command", required=True)

    create = commands.add_parser(
        "create", help="Bootstrap a View from Model or Block scope."
    )
    create.add_argument(
        "--model-ship", action="append", help="Model scope root; repeatable."
    )
    create.add_argument(
        "--block-ship", action="append", help="Block scope root; repeatable."
    )
    create.add_argument(
        "--project",
        nargs="?",
        const=".",
        help="Add the selected Project's main Model to View scope.",
    )
    create.add_argument(
        "--view-type",
        choices=tuple(VIEW_TYPES),
        default=DIAGRAM_VIEW_TYPE,
        help="Runtime Diagram.View Type retained by the View manifest.",
    )
    create.add_argument("--about", help="Open integration metadata JSON object.")
    create.add_argument(
        "--about-field",
        action="append",
        metavar="KEY=VALUE",
        help="Add one top-level about.json field; repeatable.",
    )
    create.add_argument("--bootstrap-visible-lines", type=int, default=4)
    create.add_argument("--max-visible-lines", type=int, default=120)
    _root(create)
    _diagram(create)
    _chatlas(create)
    _json(create)
    create.set_defaults(handler=_cmd_create)

    listing = commands.add_parser("list", help="List retained Views.")
    listing.add_argument(
        "--about",
        action="append",
        metavar="KEY=VALUE",
        help="Keep Views whose about.json has this exact top-level value; repeatable.",
    )
    _root(listing)
    _json(listing)
    listing.set_defaults(handler=_cmd_list)

    show = commands.add_parser("show", help="Read one self-contained View.")
    show.add_argument("--view", required=True)
    _root(show)
    _json(show)
    show.set_defaults(handler=_cmd_show)

    peers = commands.add_parser(
        "peers",
        help="Show selections from related Session Views as attention hints.",
    )
    peers.add_argument("--view", required=True)
    _root(peers)
    _json(peers)
    peers.set_defaults(handler=_cmd_peers)

    mentions = commands.add_parser(
        "mentions",
        help="Compare one Session View with exact Diagram mentions in its chat.",
    )
    mentions.add_argument("--view", required=True)
    _root(mentions)
    _diagram(mentions)
    _chatlas(mentions)
    _json(mentions)
    mentions.set_defaults(handler=_cmd_mentions)

    sync = commands.add_parser(
        "sync", help="Refresh one View against current Diagram editions."
    )
    _mutation_options(sync)
    sync.set_defaults(handler=_cmd_sync)

    for direction in ("expand", "collapse"):
        parser = commands.add_parser(
            direction, help=f"{direction.capitalize()} one scoped Block."
        )
        parser.add_argument("--block-ship", required=True)
        parser.add_argument("--steps", type=int, default=1)
        parser.add_argument("--full", action="store_true")
        _mutation_options(parser)
        parser.set_defaults(handler=_cmd_disclose, direction=direction)

    for operation in ("include-line", "exclude-line"):
        parser = commands.add_parser(
            operation,
            help=f"{operation.replace('-', ' ').capitalize()} in the materialized context.",
        )
        parser.add_argument("--block-ship", required=True)
        parser.add_argument("--line-ship", required=True)
        _mutation_options(parser)
        parser.set_defaults(handler=_cmd_line_selection, operation=operation)

    check = commands.add_parser(
        "check", help="Report View consistency and staleness POIs."
    )
    check.add_argument("--view", required=True)
    _root(check)
    _diagram(check)
    _chatlas(check)
    _json(check)
    check.set_defaults(handler=_cmd_check)

    render = commands.add_parser(
        "render", help="Render one View as Kernel.Writing Markdown."
    )
    render.add_argument("--view", required=True)
    render.add_argument("--output", help="Optional derived Markdown output path.")
    _root(render)
    _json(render)
    render.set_defaults(handler=_cmd_render)


__all__ = ["register_view_commands"]
