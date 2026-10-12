"""Project checks and status CLI: run a Project's checks, alone or with its actions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l1.checks import CheckResult
from tarav.l1.poi.rendering import (
    DEFAULT_POI_RENDERER, POISelection, renderer, renderers,
)


def _progress(result: CheckResult) -> None:
    if sys.stderr.isatty():
        print(f"{type(result.check).__name__}: {result.status}", file=sys.stderr, flush=True)


# tarav.breadcrumb a671fcec806bcecf6adccaf70a7f2c991f04b2685ea24f7056aa3cf53f820f8e
# tarav.breadcrumb 31d6a87727d93d79dc92f3804e9916b37f4a8d7639862d3ef2fe9144dc778ee1
def report_project_checks(
    project, *, json_output: bool = False, by: str = "type", sort: str = "run",
    limit: int = 20, offset: int = 0, poi_type: str | None = None,
    check: str | None = None, renderer_name: str = DEFAULT_POI_RENDERER,
    level: str = "line",
) -> int:
    """Run a Project's checks and show a bounded grouped report. Nothing else happens."""
    try:
        run = _retained(project, project.checks.run(on_result=_progress))
        # tarav.breadcrumb ad61e17278a7f87bdbe6bba00b7195dd5389a8f9423618314b32ae8fa446c9e2
    except NotImplementedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = run.report(by=by, sort=sort, limit=limit, offset=offset, type=poi_type,
                        check=check, detail=level == "record")
    if json_output:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(renderer(renderer_name).render(POISelection.from_check_report(report), level=level))
    return 0 if run.clean() else 1


# tarav.breadcrumb 7231b58f634d9c6ef60ff8b772ffec1f46a707b47b9e3fc130252f6d89fec78e
def report_project_status(
    project, *, json_output: bool = False, by: str = "type", sort: str = "run",
    limit: int = 20, offset: int = 0, poi_type: str | None = None,
    check: str | None = None, renderer_name: str = DEFAULT_POI_RENDERER,
    level: str = "line",
) -> int:
    """Run a Project's checks, hand the results to its actions, and show both.

    The Project does the work; this only presents it. Exit 0 says every check
    completed and every finding left is blessed.
    """
    from tarav.l1.actions.pois import POIActions

    try:
        status = project.status(on_result=_progress)
    except NotImplementedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    run = _retained(project, status.run())
    standing = POIActions().standing
    report = run.report(by=by, sort=sort, limit=limit, offset=offset, type=poi_type,
                        check=check, detail=level == "record", label=standing)
    acted = status.acted()
    acted = {**{key: value for key, value in acted.items() if key != "signals"},
             "closed": [signal.as_dict(detail=True) for signal in acted["signals"]]}
    if json_output:
        print(json.dumps({**report, "actions": acted}, indent=2, default=str))
    else:
        print(renderer(renderer_name).render(POISelection.from_check_report(report), level=level))
        print(_actions_text(acted))
    settled = (all(result.status == "completed" for result in run.results)
               and all(standing(poi) == "blessed" for poi in run.findings()))
    return 0 if settled else 1


def _code(args: argparse.Namespace, function: str) -> str:
    options = {
        "json_output": args.json, "by": args.by, "sort": args.sort,
        "limit": args.limit, "offset": args.offset, "poi_type": args.poi_type,
        "check": args.check_type, "renderer_name": args.renderer, "level": args.level,
    }
    return (
        f"from tarav.l3.check import {function}\n"
        f"raise SystemExit({function}(project, **{options!r}))\n"
    )


def _in_harness(args: argparse.Namespace, function: str, command: str) -> int:
    if args.project is None:
        raise CliError(f"{command} needs --project [PATH]")
    from tarav.l3.project.harness import run

    return run(path=args.project, code=_code(args, function))


# tarav.breadcrumb 1778a37c1707becb0bed583cc5d2ee8f8a4b3047975fb3b90d1c61a0a8065481
def _check(args: argparse.Namespace) -> int:
    return _in_harness(args, "report_project_checks", "tarav check")


def _status(args: argparse.Namespace) -> int:
    return _in_harness(args, "report_project_status", "tarav project status")


def _report_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        type=Path,
        nargs="?",
        const=Path("."),
        help="Search this directory and parents for a Project; optionally start at PATH.",
    )
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    parser.add_argument("--by", choices=("type", "check", "identity"),
                        default="type", help="Group POIs by this field (default: type).")
    parser.add_argument("--sort", choices=("run", "count"), default="run",
                        help="Sort groups by first occurrence or descending count.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum groups to show.")
    parser.add_argument("--offset", type=int, default=0, help="First group to show.")
    # tarav.breadcrumb 1c56bfc2a3f025dba4e39391246e2c9ff6b82badb41849082dabe55687cf7e92
    parser.add_argument("--type", dest="poi_type", help="Show this POI Type and its subtypes.")
    parser.add_argument("--check", dest="check_type", help="Filter by exact Check Type name.")
    parser.add_argument("--renderer", choices=tuple(item.name for item in renderers()),
                        default=DEFAULT_POI_RENDERER, help="Named POI renderer.")
    parser.add_argument("--level", choices=("line", "record", "context"), default="line",
                        help="POI detail level for rendered output.")


def register_check_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "check",
        help="Run a Project's checks in its harness and report the POIs. "
             "It does not touch the Project's actions; `tarav project status` does.",
        epilog=(
            "examples:\n"
            "  tarav check --project\n"
            "  tarav check --project /path/to/project --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _report_arguments(parser)
    parser.set_defaults(handler=_check)


# tarav.breadcrumb 09b54769f85d6baa3ad93af7baa6fa6cb7c4442748b47ca9f757c89892aa7322
def register_status_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "status",
        help="Run a Project's checks and update its actions from the results: open the "
             "action of each new POI, close those whose POI is gone. Run it as often "
             "as needed.",
        epilog=(
            "examples:\n"
            "  tarav project status --project\n"
            "  tarav project status --project /path/to/project --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _report_arguments(parser)
    parser.set_defaults(handler=_status)


def _retained(project, run):
    """Keep the reported POIs so `tarav context --id` can open them afterwards."""
    from tarav.l1.poi.reporting import ReportedPOIStore

    try:
        identity = {"id": str(project.id), "name": project.name, "root": str(project.root)}
    except Exception:
        return run
    ReportedPOIStore().retain(run.pois(), project=identity)
    return run


def _actions_text(acted: dict[str, object]) -> str:
    lines = [f"POI actions: {acted['actions']} raised now in {len(acted['projects'])} "
             f"Project(s); {acted['opened']} opened, "
             f"{acted['reopened']} reopened, {acted['gone']} closed as gone. "
             "List them with `tarav action list --project`."]
    lines.extend(f"  gone: {signal['message']}" for signal in acted["closed"])
    return "\n".join(lines)


__all__ = ["register_check_command", "register_status_command", "report_project_checks",
           "report_project_status"]
