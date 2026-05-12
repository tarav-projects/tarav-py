from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.project import (
    load_project_config,
    require_explicit_agentos_project,
)
from agentos._core.project_command_log import record_project_command_from_args
from agentos._core.scan import DEFAULT_SCAN_EXCLUDES
from agentos._core.scan import resolve_relative_paths_under_root

from .core import (
    DEFAULT_PREFIX_WIDTH,
    PrefixPolicy,
    default_prefix_policy,
    next_project_prefix,
)


def _cmd_prefix_next(args: argparse.Namespace) -> int:
    return _cmd_prefix_next_project(args)


def _load_prefix_policy(project_config_path: Path) -> PrefixPolicy:
    config = load_project_config(project_config_path)
    if "prefix" in config:
        raise CliError("custom project prefix config is not supported yet")
    return default_prefix_policy()


def _normalize_project_relative_target(root: Path, raw_target: str) -> str:
    target = Path(raw_target)
    if target.is_absolute():
        raise CliError("prefix target must be relative to the agentos project root")
    resolved = (root / target).resolve()
    try:
        rel_path = resolved.relative_to(root)
    except ValueError as exc:
        raise CliError(f"prefix target escapes project root: {raw_target}") from exc
    normalized = rel_path.as_posix().strip("/")
    if not normalized:
        raise CliError("prefix target must not be the project root")
    return normalized


def _cmd_prefix_next_project(args: argparse.Namespace) -> int:
    project = require_explicit_agentos_project(
        project=args.project,
        project_base=args.project_base,
        command_name="agentos stdlib prefix next",
    )
    record_project_command_from_args(
        project=project,
        args=args,
    )
    root = project.root
    policy = _load_prefix_policy(project.config_path)

    target = _normalize_project_relative_target(root, args.target)
    includes = (
        None
        if not args.include
        else resolve_relative_paths_under_root(root, args.include, option_name="include")
    )
    extra_excludes = resolve_relative_paths_under_root(root, args.exclude, option_name="exclude")
    if args.no_default_excludes:
        excludes = policy.excludes + extra_excludes
    else:
        excludes = tuple(DEFAULT_SCAN_EXCLUDES) + policy.excludes + extra_excludes

    allocation = next_project_prefix(
        root=root,
        target=target,
        policy=policy,
        includes=includes,
        excludes=excludes,
    )

    if args.json:
        scan_includes = policy.includes if includes is None else includes
        payload = {
            "next_prefix": allocation.prefix,
            "next_value": allocation.value,
            "project_root": str(root),
            "target": target,
            "route": allocation.route.name,
            "range": [allocation.route.minimum, allocation.route.maximum],
            "scan": {
                "includes": list(scan_includes),
                "excludes": list(excludes),
            },
            "matched_prefix_count": len(allocation.prefixes),
            "reserved_prefix_count": allocation.reserved_count,
            "policy_source": policy.source,
            "width": DEFAULT_PREFIX_WIDTH,
        }
        print(json.dumps(payload, indent=2))
        return 0

    print(allocation.prefix)
    return 0


def register_prefix_commands(subparsers: argparse._SubParsersAction) -> None:
    prefix_parser = subparsers.add_parser(
        "prefix",
        help="Allocate unique numeric filename prefixes.",
    )
    prefix_subparsers = prefix_parser.add_subparsers(dest="prefix_command")

    prefix_next_parser = prefix_subparsers.add_parser(
        "next",
        help="Print the next available numeric prefix for a project target.",
    )
    prefix_next_parser.add_argument(
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
    prefix_next_parser.add_argument(
        "--project-base",
        required=True,
        help="Required assertion for the resolved project root basename.",
    )
    prefix_next_parser.add_argument(
        "--target",
        required=True,
        help="Project-relative numbered surface target, such as notes/live or notes/index.",
    )
    prefix_next_parser.add_argument(
        "--include",
        action="append",
        default=[],
        help="Relative path to include in scan (repeatable). Overrides policy includes.",
    )
    prefix_next_parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Directory or path pattern to exclude from scan (repeatable).",
    )
    prefix_next_parser.add_argument(
        "--no-default-excludes",
        action="store_true",
        help="Disable built-in excludes (.git, .venv, __pycache__, ...).",
    )
    prefix_next_parser.add_argument(
        "--json",
        action="store_true",
        help="Print rich JSON metadata instead of plain prefix.",
    )
    prefix_next_parser.set_defaults(handler=_cmd_prefix_next)
