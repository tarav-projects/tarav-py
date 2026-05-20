from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentos._core.project import (
    assert_project_base,
    build_not_inside_project_message,
    find_agentos_project_roots_under,
    initialize_global_layout,
    initialize_project_layout,
    find_agentos_project_root,
    load_project_marker,
    project_marker_path,
    require_agentos_project,
    require_explicit_project_target,
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

    project_target = require_explicit_project_target(args.project, command_name="agentos init")
    root = project_target.expanduser().resolve()
    payload = initialize_project_layout(
        root,
        ensure=args.ensure,
        project_id=args.project_id,
        project_name=args.project_name,
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


def _project_list_record(project_root: Path) -> dict[str, object]:
    marker_path = project_marker_path(project_root)
    marker = load_project_marker(marker_path)
    return {
        "project_root": str(project_root),
        "project_id": marker["project_id"],
        "project_name": marker.get("project_name"),
        "marker_path": str(marker_path),
    }


def _cmd_projects_list(args: argparse.Namespace) -> int:
    project_roots = find_agentos_project_roots_under(args.root)
    if args.json_output:
        print(json.dumps([_project_list_record(root) for root in project_roots], indent=2))
        return 0

    for project_root in project_roots:
        print(project_root)
    return 0


def _cmd_projects_resolve(args: argparse.Namespace) -> int:
    project = require_agentos_project(
        start_path=Path.cwd(),
        project=args.project,
        include_init_hint=True,
    )
    assert_project_base(project, args.project_base)
    print("true")
    return 0


def register_project_commands(subparsers: argparse._SubParsersAction) -> None:
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a project target or the global agentos home.",
    )
    init_parser.add_argument(
        "--scope",
        choices=["project", "global"],
        default="project",
        help="Initialization scope. Project scope targets a local Agentos.Project; global scope initializes ~/.agentos (default: project).",
    )
    init_parser.add_argument(
        "--project",
        type=Path,
        nargs="?",
        const=Path("."),
        default=None,
        help="Required for --scope project. Bare --project targets current pwd and may be initialized if missing.",
    )
    init_parser.add_argument(
        "--project-id",
        default=None,
        help="Explicit project UUID for --scope project.",
    )
    init_parser.add_argument(
        "--project-name",
        default=None,
        help="Optional project name to store in the project marker.",
    )
    init_parser.add_argument(
        "--ensure",
        action="store_true",
        help="If already initialized, return existing layout metadata.",
    )
    init_parser.set_defaults(handler=_cmd_init)

    rev_parse_parser = subparsers.add_parser(
        "rev-parse",
        help="Inspect Agentos.Project resolution state without requiring an existing project.",
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

    projects_parser = subparsers.add_parser(
        "projects",
        help="Discover and verify Agentos.Project roots.",
    )
    projects_subparsers = projects_parser.add_subparsers(
        dest="projects_command",
        required=True,
    )

    projects_list_parser = projects_subparsers.add_parser(
        "list",
        help="List Agentos projects under a root.",
    )
    projects_list_parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help="Root directory to scan for Agentos.Project markers.",
    )
    projects_list_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit discovered project roots and marker metadata as JSON.",
    )
    projects_list_parser.set_defaults(handler=_cmd_projects_list)

    projects_resolve_parser = projects_subparsers.add_parser(
        "resolve",
        help="Resolve an Agentos project and assert its root basename.",
    )
    projects_resolve_parser.add_argument(
        "--project",
        nargs="?",
        type=Path,
        const=Path("."),
        default=None,
        help=(
            "Optional project selector. Bare --project targets current pwd. "
            "Requires an existing project."
        ),
    )
    projects_resolve_parser.add_argument(
        "--project-base",
        required=True,
        help="Required assertion for the resolved project root basename.",
    )
    projects_resolve_parser.set_defaults(handler=_cmd_projects_resolve)
