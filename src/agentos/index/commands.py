"""CLI commands for agentos index."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from .linter import (
    LinterCheck,
    build_linter_config,
    render_linter_json,
    render_linter_text,
    run_linter,
)


def _cmd_linter(args: argparse.Namespace) -> int:
    config, raw_depot_paths, raw_index_paths, raw_appendix_paths = build_linter_config(
        depot_paths=tuple(args.depot),
        index_paths=tuple(args.index),
        appendix_paths=tuple(args.appendix),
        coverage=tuple(getattr(args, "coverage", ()) or ()),
        scope_paths=tuple(getattr(args, "scope", ()) or ()),
        warn_unlinked=bool(getattr(args, "warn_unlinked", False)),
    )
    state = run_linter(
        config,
        raw_depot_paths,
        raw_index_paths,
        raw_appendix_paths,
        extra_checks=tuple(getattr(args, "_extra_linter_checks", ()) or ()),
    )
    json_output = render_linter_json(state)
    if args.json:
        print(json_output)
    else:
        print(render_linter_text(state))
    payload = json.loads(json_output)
    return int(payload["exit_code"])


def register_index_commands(
    subparsers: argparse._SubParsersAction,
    *,
    extra_linter_checks: Sequence[LinterCheck] = (),
) -> None:
    index_parser = subparsers.add_parser(
        "index",
        help="Index knowledge surface operations.",
    )
    index_subparsers = index_parser.add_subparsers(dest="index_command")

    linter_parser = index_subparsers.add_parser(
        "linter",
        help="Lint index and appendix surfaces.",
        description="Lint explicit Agentos index and appendix files or directories, or derive them from depot roots.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  agentos index linter --depot skills/agentos-pkg\n"
            "  agentos index linter --index skills/agentos-pkg/design "
            "--appendix skills/agentos-pkg/appendix\n"
            "  agentos index linter --index skills/agentos-pkg/000-INDEX.md --json\n\n"
            "Finding and check codes are Agentos Index concepts under Index.Linter/*.\n"
            "Resolve their meaning through the agentos-pkg Index.Linter concept\n"
            "and normal appendix discovery."
        ),
    )
    linter_parser.add_argument(
        "--depot",
        action="append",
        default=[],
        help="Depot root to derive index chapter directories and appendix surfaces from. Repeat to lint multiple depots.",
    )
    linter_parser.add_argument(
        "--index",
        action="append",
        default=[],
        help="Index file or directory to lint. Repeat to lint multiple index surfaces.",
    )
    linter_parser.add_argument(
        "--appendix",
        action="append",
        default=[],
        help="Appendix file or directory to lint. Repeat to lint multiple appendix surfaces.",
    )
    linter_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON output.",
    )
    linter_parser.add_argument(
        "--coverage",
        action="append",
        default=[],
        choices=("line", "block", "all"),
        help="Enable an optional coverage meter: line, block, or all. Repeatable.",
    )
    linter_parser.add_argument(
        "--scope",
        action="append",
        default=[],
        help="Report findings and coverage only for this file or directory scope. Repeatable.",
    )
    linter_parser.add_argument(
        "--warn-unlinked",
        action="store_true",
        help="Alias for --coverage line.",
    )
    linter_parser.set_defaults(handler=_cmd_linter, _extra_linter_checks=tuple(extra_linter_checks))
