from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos._core.scan import resolve_relative_paths_under_root, resolve_root_dir

from agentos._core.scan import DEFAULT_SCAN_EXCLUDES

from .core import PrefixScanConfig, collect_prefixes, format_prefix, next_prefix_value


def _cmd_prefix_next(args: argparse.Namespace) -> int:
    root = resolve_root_dir(args.root)
    if args.min < 0:
        raise SystemExit("error: --min must be >= 0")
    if args.width < 1:
        raise SystemExit("error: --width must be >= 1")

    includes = resolve_relative_paths_under_root(
        root,
        args.include,
        option_name="include",
    )
    excludes: tuple[str, ...]
    if args.no_default_excludes:
        excludes = tuple(args.exclude)
    else:
        excludes = tuple(DEFAULT_SCAN_EXCLUDES) + tuple(args.exclude)

    config = PrefixScanConfig(
        root=root,
        includes=includes,
        excludes=excludes,
        width=args.width,
    )

    prefixes = collect_prefixes(config)
    value = next_prefix_value(prefixes, args.min)
    prefix = format_prefix(value, args.width)

    if args.json:
        payload = {
            "next_prefix": prefix,
            "next_value": value,
            "minimum": args.min,
            "width": args.width,
            "root": str(root),
            "includes": list(includes),
            "excludes": list(excludes),
            "matched_prefix_count": len(prefixes),
        }
        print(json.dumps(payload, indent=2))
        return 0

    print(prefix)
    return 0


def register_prefix_commands(subparsers: argparse._SubParsersAction) -> None:
    prefix_parser = subparsers.add_parser(
        "prefix",
        help="Allocate unique numeric filename prefixes.",
    )
    prefix_subparsers = prefix_parser.add_subparsers(dest="prefix_command")

    prefix_next_parser = prefix_subparsers.add_parser(
        "next",
        help="Scan files and print the next available NNN- prefix.",
    )
    prefix_next_parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Project root for scanning (default: current directory).",
    )
    prefix_next_parser.add_argument(
        "--min",
        type=int,
        default=500,
        help="Minimum prefix floor when no existing prefixes are found.",
    )
    prefix_next_parser.add_argument(
        "--width",
        type=int,
        default=3,
        help="Numeric width for both matching and zero-padding output.",
    )
    prefix_next_parser.add_argument(
        "--include",
        action="append",
        default=[],
        help="Relative path to include in scan (repeatable). Defaults to full root.",
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
