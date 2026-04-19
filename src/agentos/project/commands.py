from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentos._core.project import (
    build_not_inside_project_message,
    initialize_global_layout,
    initialize_project_layout,
    find_agentos_project_root,
)


def _rev_parse_not_inside_project() -> int:
    print(build_not_inside_project_message(git_style=True), file=sys.stderr)
    return 128


def _cmd_init(args: argparse.Namespace) -> int:
    if args.scope == "global":
        payload = initialize_global_layout(ensure=args.ensure)
        output = {
            "status": "ok",
            "command": "init",
            "scope": "global",
            "agentos_dir": str(payload["agentos_dir"]),
            "config_path": str(payload["config_path"]),
            "config_created": payload["config_created"],
            "dirs": {name: str(path) for name, path in payload["dirs"].items()},
        }
        print(json.dumps(output, indent=2))
        return 0

    root = args.project.expanduser().resolve()
    payload = initialize_project_layout(
        root,
        ensure=args.ensure,
        project_id=args.project_id,
    )
    output = {
        "status": "ok",
        "command": "init",
        "scope": "project",
        "project_root": str(payload["project_root"]),
        "agentos_dir": str(payload["agentos_dir"]),
        "marker_path": str(payload["marker_path"]),
        "marker_created": payload["marker_created"],
        "config_path": str(payload["config_path"]),
        "config_created": payload["config_created"],
        "dirs": {name: str(path) for name, path in payload["dirs"].items()},
        "marker": payload["marker"],
    }
    print(json.dumps(output, indent=2))
    return 0


def _cmd_rev_parse(args: argparse.Namespace) -> int:
    project_root = find_agentos_project_root(args.path_hint)
    if args.is_inside_agentos_project:
        if project_root is None:
            return _rev_parse_not_inside_project()
        print("true")
        return 0

    if args.show_toplevel:
        if project_root is None:
            return _rev_parse_not_inside_project()
        print(str(project_root))
        return 0

    raise SystemExit("error: missing rev-parse mode")


def register_project_commands(subparsers: argparse._SubParsersAction) -> None:
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize local or global agentos storage.",
    )
    init_parser.add_argument(
        "--scope",
        choices=["project", "global"],
        default="project",
        help="Initialization scope (default: project).",
    )
    init_parser.add_argument(
        "--project",
        type=Path,
        nargs="?",
        const=Path("."),
        default=Path("."),
        help="Project target for --scope project (default: current directory). Bare --project targets current pwd.",
    )
    init_parser.add_argument(
        "--project-id",
        default=None,
        help="Explicit project UUID for --scope project.",
    )
    init_parser.add_argument(
        "--ensure",
        action="store_true",
        help="If already initialized, return existing layout metadata.",
    )
    init_parser.set_defaults(handler=_cmd_init)

    rev_parse_parser = subparsers.add_parser(
        "rev-parse",
        help="Git-like project context introspection.",
    )
    rev_parse_flags = rev_parse_parser.add_mutually_exclusive_group(required=True)
    rev_parse_flags.add_argument(
        "--is-inside-agentos-project",
        action="store_true",
        dest="is_inside_agentos_project",
        help="Print true when executed inside an agentos project.",
    )
    rev_parse_flags.add_argument(
        "--show-toplevel",
        action="store_true",
        dest="show_toplevel",
        help="Print absolute project root path.",
    )
    rev_parse_parser.add_argument(
        "--path",
        default=".",
        dest="path_hint",
        help="Start path for parent-walk discovery (default: current directory).",
    )
    rev_parse_parser.set_defaults(handler=_cmd_rev_parse)
