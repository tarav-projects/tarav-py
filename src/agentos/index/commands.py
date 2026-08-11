# $kw: ^index-poi-command --from POI.System --from POI.Linter --note [CT] Index command output uses the common POI report boundary ^c20260729-49u
"""CLI commands for agentos index."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path

from agentos._core.errors import CliError
from agentos.poi import POICatalog
from agentos.poi import add_check_selection_args

from .linter import (
    CHECKS,
    LinterCheck,
    build_linter_config,
    build_linter_poi_report,
    check_registry,
    render_linter_json,
    render_linter_text,
    run_linter,
)


def _line_manifest_from_args(args: argparse.Namespace) -> dict[str, object]:
    from .line_manifest import build_index_line_manifest

    effective_relationships = tuple(
        args.relationships or ("support", "gates", "provenance")
    )
    projector_factory = getattr(
        args, "_line_manifest_relationship_projector_factory", None
    )
    projector = None
    if projector_factory is not None:
        projector = projector_factory(
            relationships=effective_relationships,
            verification=args.verification,
            sample_size=args.verification_sample,
            detail=args.detail,
            radius=args.chat_radius,
        )
    return build_index_line_manifest(
        depot_root=args.depot,
        anchors=tuple(args.anchors or ()),
        scopes=tuple(args.scopes or ()),
        neighbors=args.neighbors,
        limit=args.limit,
        relationship_projector=projector,
        inputs={
            "relationships": list(effective_relationships),
            "verification": args.verification,
            "verification_sample": args.verification_sample,
            "detail": args.detail,
            "chat_radius": args.chat_radius,
        },
    )


def _cmd_line_manifest_show(args: argparse.Namespace) -> int:
    from .line_manifest import format_index_line_manifest_text

    payload = _line_manifest_from_args(args)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(format_index_line_manifest_text(payload))
    return 1 if payload.get("status") == "ambiguous" else 0


def _cmd_line_manifest_materialize(args: argparse.Namespace) -> int:
    from agentos._core.errors import CliError

    materializer = getattr(args, "_line_manifest_materializer", None)
    if materializer is None:
        raise CliError("agentos index line manifest materialize has no provider")
    manifest = _line_manifest_from_args(args)
    result = materializer(manifest)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result["path"])
    return 1 if manifest.get("status") == "ambiguous" else 0


def _add_line_manifest_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--depot",
        required=True,
        help="Index depot whose parsed lines are the manifest subjects.",
    )
    parser.add_argument(
        "--anchor",
        action="append",
        dest="anchors",
        default=[],
        help="Select a line by attached anchor. Repeatable; optional ^ is accepted.",
    )
    parser.add_argument(
        "--scope",
        action="append",
        dest="scopes",
        default=[],
        help="Select Index lines in this depot-relative file or directory. Repeatable.",
    )
    parser.add_argument(
        "--relationship",
        action="append",
        dest="relationships",
        choices=("support", "gates", "provenance"),
        default=[],
        help="Include this relationship namespace. Repeatable; defaults to all.",
    )
    parser.add_argument(
        "--verification",
        choices=("stored", "sampled", "complete"),
        default="stored",
        help="Turn-reference verification breadth (default: stored).",
    )
    parser.add_argument(
        "--verification-sample",
        type=int,
        default=2,
        help="Deterministic turn sample size for --verification sampled (default: 2).",
    )
    parser.add_argument(
        "--detail",
        choices=("reference", "turn", "context"),
        default="reference",
        help="Evidence rendering for verified turns (default: reference).",
    )
    parser.add_argument(
        "--neighbors",
        type=int,
        default=2,
        help="Sibling lines before and after each subject, clipped to its block (default: 2).",
    )
    parser.add_argument(
        "--chat-radius",
        type=int,
        default=2,
        help="Visible chat turns around verified members with --detail context (default: 2).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum selected lines to emit; omission counts remain explicit.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the normalized JSON object.",
    )


def _cmd_linter(args: argparse.Namespace) -> int:
    if getattr(args, "list_checks", False):
        from agentos.poi import render_check_registry

        extra_checks = tuple(getattr(args, "_extra_linter_checks", ()) or ())
        for line in render_check_registry(check_registry((*CHECKS, *extra_checks))):
            print(line)
        return 0
    config, raw_depot_paths, raw_index_paths, raw_appendix_paths = build_linter_config(
        depot_paths=tuple(args.depot),
        index_paths=tuple(args.index),
        appendix_paths=tuple(args.appendix),
        coverage=tuple(getattr(args, "coverage", ()) or ()),
        scope_paths=tuple(getattr(args, "scope", ()) or ()),
        anchors=tuple(getattr(args, "anchor", ()) or ()),
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
    from .anchor_locator import materialize_index_anchor_locator

    for depot in config.depot_paths:
        lines = [
            line
            for document in state.parsed_documents
            if document.path is not None and _path_is_within(document.path, depot)
            for line in document.kernel_lines()
        ]
        try:
            locator = materialize_index_anchor_locator(
                depot_root=depot,
                lines=lines,
                workspace_root=config.root,
            )
            state.anchor_locators.append({"standing": "written", **locator})
        except (CliError, OSError) as exc:
            state.anchor_locators.append(
                {
                    "standing": "unavailable",
                    "depot": str(depot),
                    "reason": str(exc),
                }
            )
    poi_catalog = getattr(args, "_poi_catalog", None)
    poi_report = build_linter_poi_report(state, catalog=poi_catalog)
    json_output = render_linter_json(
        state,
        catalog=poi_catalog,
        poi_report=poi_report,
    )
    if args.json:
        print(json_output)
    else:
        print(
            render_linter_text(
                state,
                catalog=poi_catalog,
                poi_report=poi_report,
                show_passed=bool(getattr(args, "show_passed", False)),
            )
        )
    payload = json.loads(json_output)
    return int(payload["exit_code"])


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


_BLOCKS_SORT_KEYS = ("gr-density",)


def _cmd_blocks(args: argparse.Namespace) -> int:
    from pathlib import Path

    from agentos._core.errors import CliError

    from .model import parse_depot
    from .model.stats import block_grounding_stats

    support_resolver = getattr(args, "_support_reference_resolver", None)
    if support_resolver is None:
        raise CliError(
            "agentos index blocks requires a support-reference resolver; "
            "grounding cannot be inferred from anchor syntax"
        )
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
            raise CliError(
                f"agentos index blocks depot is not a directory: {raw_depot}"
            )
        rows.extend(
            block_grounding_stats(
                parse_depot(depot),
                resolve_support_reference=support_resolver,
            )
        )

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
            "gr_density": round(summary_anchors / summary_lines, 4)
            if summary_lines
            else 0.0,
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


def _cmd_issues(args: argparse.Namespace) -> int:
    from pathlib import Path

    from agentos._core.errors import CliError

    from .issues import issue_inventory
    from .model import parse_depot

    support_resolver = getattr(args, "_support_reference_resolver", None)
    review_resolver = getattr(args, "_review_reference_resolver", None)
    if support_resolver is None or review_resolver is None:
        raise CliError(
            "agentos index issues requires support and review reference resolvers"
        )
    root = Path.cwd().resolve()
    rows = []
    for raw_depot in args.depot:
        depot = (root / raw_depot).resolve()
        if not depot.is_dir():
            raise CliError(f"agentos index issues depot is not a directory: {raw_depot}")
        rows.extend(
            issue_inventory(
                parse_depot(depot),
                resolve_support_reference=support_resolver,
                resolve_review_reference=review_resolver,
            )
        )
    payload = {
        "command": "agentos index issues",
        "issues": [
            {
                "identity": issue.identity,
                "number": issue.number,
                "name": issue.name,
                "block_path": issue.block_path,
                "path": str(issue.path),
                "line": issue.line,
                "state": issue.state,
                "healthy": issue.healthy,
                "resolution_lines": list(issue.resolution_lines),
                "line_count": len(issue.lines),
                "grounded_line_count": sum(line.grounded for line in issue.lines),
                "reviewed_line_count": sum(line.reviewed for line in issue.lines),
            }
            for issue in rows
        ],
        "summary": {
            "issues": len(rows),
            "open": sum(issue.state == "open" for issue in rows),
            "resolved": sum(issue.state == "resolved" for issue in rows),
            "healthy": sum(issue.healthy for issue in rows),
        },
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    print("Index issues")
    for issue in rows:
        health = "healthy" if issue.healthy else "needs attention"
        print(f"- {issue.block_path}: {issue.state}, {health}")
    summary = payload["summary"]
    print(
        f"Summary: {summary['issues']} issue(s), {summary['open']} open, "
        f"{summary['resolved']} resolved."
    )
    return 0


def register_index_commands(
    subparsers: argparse._SubParsersAction,
    *,
    extra_linter_checks: Sequence[LinterCheck] = (),
    support_reference_resolver: Callable[[str], bool] | None = None,
    review_reference_resolver: Callable[[str, str], bool] | None = None,
    line_manifest_relationship_projector_factory: Callable[..., Callable]
    | None = None,
    line_manifest_materializer: Callable[[dict[str, object]], dict[str, object]]
    | None = None,
    poi_catalog: POICatalog | None = None,
) -> None:
    index_parser = subparsers.add_parser(
        "index",
        help="Index knowledge surface operations.",
    )
    index_subparsers = index_parser.add_subparsers(dest="index_command")

    line_parser = index_subparsers.add_parser(
        "line",
        help="Inspect parsed Index lines and their application relationships.",
    )
    line_subparsers = line_parser.add_subparsers(
        dest="index_line_command", required=True
    )
    manifest_parser = line_subparsers.add_parser(
        "manifest",
        help="Build a normalized volatile line-centered context manifest.",
    )
    manifest_subparsers = manifest_parser.add_subparsers(
        dest="index_line_manifest_command", required=True
    )
    manifest_show_parser = manifest_subparsers.add_parser(
        "show",
        help="Print a line manifest without writing it.",
    )
    _add_line_manifest_arguments(manifest_show_parser)
    manifest_show_parser.set_defaults(
        handler=_cmd_line_manifest_show,
        _line_manifest_relationship_projector_factory=line_manifest_relationship_projector_factory,
    )
    manifest_materialize_parser = manifest_subparsers.add_parser(
        "materialize",
        help="Write a line manifest through the configured volatile provider.",
    )
    _add_line_manifest_arguments(manifest_materialize_parser)
    manifest_materialize_parser.set_defaults(
        handler=_cmd_line_manifest_materialize,
        _line_manifest_relationship_projector_factory=line_manifest_relationship_projector_factory,
        _line_manifest_materializer=line_manifest_materializer,
    )

    issues_parser = index_subparsers.add_parser(
        "issues",
        help="List Issue.Blocks with computed open or resolved standing.",
    )
    issues_parser.add_argument(
        "--depot",
        action="append",
        required=True,
        help="Index depot containing issues/. Repeat for multiple depots.",
    )
    issues_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON output.",
    )
    issues_parser.set_defaults(
        handler=_cmd_issues,
        _support_reference_resolver=support_reference_resolver,
        _review_reference_resolver=review_reference_resolver,
    )

    blocks_parser = index_subparsers.add_parser(
        "blocks",
        help="List concept blocks with grounding statistics.",
        description=(
            "Query the parsed index model: one row per concept block with its "
            "Grounding.Density (unique resolvable support references / kernel lines) "
            "and grounded-line coverage. `--sort gr-density` returns the "
            "grounding/enrichment worklist."
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
    blocks_parser.set_defaults(
        handler=_cmd_blocks,
        _support_reference_resolver=support_reference_resolver,
    )

    linter_parser = index_subparsers.add_parser(
        "linter",
        help="Lint Agentos Index depot surfaces.",
        description=(
            "Lint explicit Agentos index and appendix files or directories, "
            "or derive chapter, appendix, agendix, and issues surfaces from depot roots."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  agentos index linter --depot skills/agentos-pkg\n"
            "  agentos index linter --index skills/agentos-pkg/design "
            "--appendix skills/agentos-pkg/appendix\n"
            "  agentos index linter --index skills/agentos-pkg/000-INDEX.md --json\n\n"
            "Finding codes resolve through registered Package.Skill POI catalogs.\n"
            "Use `agentos poi explain <class>` for authoritative documentation."
        ),
    )
    linter_parser.add_argument(
        "--depot",
        action="append",
        default=[],
        help=(
            "Depot root to derive index chapter, appendix, agendix, and issues surfaces "
            "from. Repeat to lint multiple depots."
        ),
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
        "--show-passed",
        action="store_true",
        help="Print each check that completed successfully in text output.",
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
        "--anchor",
        action="append",
        default=[],
        help=(
            "Lint only Index lines carrying this anchor. Repeatable; optional ^ is "
            "accepted and every requested anchor must exist."
        ),
    )
    linter_parser.add_argument(
        "--warn-unlinked",
        action="store_true",
        help="Alias for --coverage line.",
    )
    add_check_selection_args(linter_parser, unit="check")
    linter_parser.set_defaults(
        handler=_cmd_linter,
        _extra_linter_checks=tuple(extra_linter_checks),
        _poi_catalog=poi_catalog,
    )
