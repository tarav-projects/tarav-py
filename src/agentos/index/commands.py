"""CLI commands for agentos index."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from .linter import (
    LinterCheck,
    build_linter_config,
    check_registry,
    render_linter_json,
    render_linter_text,
    run_linter,
)


def _cmd_linter(args: argparse.Namespace) -> int:
    if getattr(args, "list_checks", False):
        for row in check_registry():
            state = "on " if row["default_on"] else "off"
            tier = "structural" if row["structural"] else "reportable"
            print(f"{row['selector']:<24} [{state}] {tier:<11} {row['title']}")
        return 0
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
        include=tuple(getattr(args, "check", ()) or ()),
        exclude=tuple(getattr(args, "skip", ()) or ()),
    )
    json_output = render_linter_json(state)
    if args.json:
        print(json_output)
    else:
        print(render_linter_text(state))
    payload = json.loads(json_output)
    return int(payload["exit_code"])


_BLOCKS_SORT_KEYS = ("gr-density",)


def _cmd_blocks(args: argparse.Namespace) -> int:
    from pathlib import Path

    from agentos._core.errors import CliError

    from .model import parse_depot
    from .model.stats import block_grounding_stats

    sort = getattr(args, "sort", None)
    if sort is not None and sort not in _BLOCKS_SORT_KEYS:
        raise CliError(
            f"unsupported agentos index blocks sort: {sort!r} "
            f"(supported: {', '.join(_BLOCKS_SORT_KEYS)})"
        )
    root = Path.cwd().resolve()
    rows = []
    for raw_depot in args.depot:
        depot = (root / raw_depot).resolve()
        if not depot.is_dir():
            raise CliError(f"agentos index blocks depot is not a directory: {raw_depot}")
        rows.extend(block_grounding_stats(parse_depot(depot)))

    def _rel(path: Path | None) -> str:
        if path is None:
            return "."
        try:
            return str(path.resolve().relative_to(root))
        except ValueError:
            return str(path)

    scope_entries = tuple(getattr(args, "scope", ()) or ())
    if scope_entries:
        scope_paths = tuple((root / entry).resolve() for entry in scope_entries)
        matched: set[Path] = set()
        scoped_rows = []
        for row in rows:
            row_path = row.path.resolve() if row.path is not None else None
            for scope in scope_paths:
                if row_path is not None and row_path.is_relative_to(scope):
                    matched.add(scope)
                    scoped_rows.append(row)
                    break
        for entry, scope in zip(scope_entries, scope_paths):
            if scope not in matched:
                raise CliError(
                    f"agentos index blocks scope matches no listed block file: {entry}"
                )
        rows = scoped_rows

    if sort == "gr-density":
        rows.sort(key=lambda row: (row.gr_density, -row.kernel_lines, row.block_path))

    summary_lines = sum(row.kernel_lines for row in rows)
    # aggregate density is unique-within-scope: a stamp shared across blocks counts once
    summary_anchors = len({anchor for row in rows for anchor in row.anchors})
    listed = rows if getattr(args, "limit", None) is None else rows[: args.limit]
    payload = {
        "command": "agentos index blocks",
        "root": str(root),
        "depot": list(args.depot),
        "scope": list(scope_entries),
        "sort": sort,
        "blocks": [
            {
                "block_path": row.block_path,
                "path": _rel(row.path),
                "line": row.line,
                "kernel_lines": row.kernel_lines,
                "unique_anchors": row.unique_anchors,
                "gr_density": round(row.gr_density, 4),
                "grounded_lines": row.grounded_lines,
            }
            for row in listed
        ],
        "summary": {
            "blocks": len(rows),
            "kernel_lines": summary_lines,
            "unique_anchors": summary_anchors,
            "gr_density": round(summary_anchors / summary_lines, 4) if summary_lines else 0.0,
        },
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    header = f"{'gr-density':>10}  {'anchors':>7}  {'lines':>5}  {'grounded':>8}  block"
    print("Index blocks")
    print(header)
    for row in listed:
        grounded = f"{row.grounded_lines}/{row.kernel_lines}"
        print(
            f"{row.gr_density:>10.3f}  {row.unique_anchors:>7}  {row.kernel_lines:>5}  "
            f"{grounded:>8}  {row.block_path}  ({_rel(row.path)}:{row.line})"
        )
    summary = payload["summary"]
    print(
        f"Summary: {summary['blocks']} block(s), {summary['kernel_lines']} kernel line(s), "
        f"aggregate gr-density {summary['gr_density']}."
    )
    return 0


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

    blocks_parser = index_subparsers.add_parser(
        "blocks",
        help="List concept blocks with grounding statistics.",
        description=(
            "Query the parsed index model: one row per concept block with its "
            "Grounding.Density (unique inline anchors / kernel lines) and grounded-line "
            "coverage. `--sort gr-density` returns the grounding/enrichment worklist."
        ),
    )
    blocks_parser.add_argument(
        "--depot",
        action="append",
        default=[],
        help="Depot root to list blocks from. Repeat for multiple depots.",
    )
    blocks_parser.add_argument(
        "--scope",
        action="append",
        default=[],
        help="Limit listed blocks to files under this path. Repeatable.",
    )
    blocks_parser.add_argument(
        "--sort",
        help="Sort order. Supported: gr-density (ascending — the worklist).",
    )
    blocks_parser.add_argument(
        "--limit",
        type=int,
        help="Truncate the listing after sorting.",
    )
    blocks_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON output.",
    )
    blocks_parser.set_defaults(handler=_cmd_blocks)

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
    linter_parser.add_argument(
        "--check",
        action="append",
        default=[],
        metavar="SELECTOR",
        help="Enable a check by selector (repeatable); opts into default-off checks like 'dangling-mention'.",
    )
    linter_parser.add_argument(
        "--skip",
        action="append",
        default=[],
        metavar="SELECTOR",
        help="Disable a check by selector (repeatable); structural checks cannot be disabled.",
    )
    linter_parser.add_argument(
        "--list-checks",
        action="store_true",
        help="List check selectors with their default state and tier, then exit.",
    )
    linter_parser.set_defaults(handler=_cmd_linter, _extra_linter_checks=tuple(extra_linter_checks))
