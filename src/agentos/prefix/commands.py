from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import DEFAULT_EXCLUDES, PrefixScanConfig, collect_prefixes, format_prefix, next_prefix_value


def _cmd_prefix_next(args: argparse.Namespace) -> int:
    root = args.root.expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"error: root path does not exist: {root}")
    if not root.is_dir():
        raise SystemExit(f"error: root path is not a directory: {root}")
    if args.min < 0:
        raise SystemExit("error: --min must be >= 0")
    if args.width < 1:
        raise SystemExit("error: --width must be >= 1")

    normalized_includes: list[str] = []
    for include in args.include:
        include_path = Path(include)
        if include_path.is_absolute():
            raise SystemExit("error: --include paths must be relative to --root")

        resolved = (root / include_path).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise SystemExit(f"error: include path escapes --root: {include}") from exc
        normalized_includes.append(str(include_path))

    includes = tuple(normalized_includes)
    excludes: tuple[str, ...]
    if args.no_default_excludes:
        excludes = tuple(args.exclude)
    else:
        excludes = tuple(DEFAULT_EXCLUDES) + tuple(args.exclude)

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
