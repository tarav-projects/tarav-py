"""Project checks CLI: run a Project's checks namespace in its harness."""

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
import tarav.l1.poi_tracking.views  # noqa: F401  registers the tracking renderer


# tarav.breadcrumb a671fcec806bcecf6adccaf70a7f2c991f04b2685ea24f7056aa3cf53f820f8e
# tarav.breadcrumb 31d6a87727d93d79dc92f3804e9916b37f4a8d7639862d3ef2fe9144dc778ee1
def report_project_checks(
    project, *, json_output: bool = False, by: str = "type", sort: str = "run",
    limit: int = 20, offset: int = 0, poi_type: str | None = None,
    check: str | None = None, renderer_name: str = DEFAULT_POI_RENDERER,
    level: str = "line", tracking: str = "write",
) -> int:
    """Run a Project's suite and show a bounded grouped report."""
    def progress(result: CheckResult) -> None:
        if sys.stderr.isatty():
            print(f"{type(result.check).__name__}: {result.status}", file=sys.stderr,
                  flush=True)

    try:
        run = _retained(project, project.checks.run(on_result=progress))
        # tarav.breadcrumb ad61e17278a7f87bdbe6bba00b7195dd5389a8f9423618314b32ae8fa446c9e2
    except NotImplementedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = run.report(by=by, sort=sort, limit=limit, offset=offset,
                        type=poi_type, check=check, detail=level == "record")
    tracked = _tracked(project, run) if tracking == "write" else None
    if json_output:
        print(json.dumps({**report, "tracking": tracked}, indent=2, default=str))
    else:
        print(renderer(renderer_name).render(POISelection.from_check_report(report), level=level))
        if tracked is not None:
            print(_tracking_line(tracked))
    return 0 if run.clean() else 1


def _code(args: argparse.Namespace) -> str:
    options = {
        "json_output": args.json, "by": args.by, "sort": args.sort,
        "limit": args.limit, "offset": args.offset, "poi_type": args.poi_type,
        "check": args.check_type, "renderer_name": args.renderer, "level": args.level,
        "tracking": args.tracking,
    }
    return (
        "from tarav.l3.check import report_project_checks\n"
        f"raise SystemExit(report_project_checks(project, **{options!r}))\n"
    )


# tarav.breadcrumb 1778a37c1707becb0bed583cc5d2ee8f8a4b3047975fb3b90d1c61a0a8065481
def _check(args: argparse.Namespace) -> int:
    if args.project is None:
        raise CliError("tarav check needs --project [PATH]")
    from tarav.l3.project.harness import run

    return run(path=args.project, code=_code(args))


def register_check_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "check",
        help="Run a Project's checks (its checks() method) in its harness.",
        epilog=(
            "examples:\n"
            "  tarav check --project\n"
            "  tarav check --project /path/to/project --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
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
    parser.add_argument("--type", dest="poi_type", help="Filter by exact POI Type name.")
    parser.add_argument("--check", dest="check_type", help="Filter by exact Check Type name.")
    parser.add_argument("--renderer", choices=tuple(item.name for item in renderers()),
                        default=DEFAULT_POI_RENDERER, help="Named POI renderer.")
    parser.add_argument("--level", choices=("line", "record", "context"), default="line",
                        help="POI detail level for rendered output.")
    parser.add_argument("--tracking", choices=("write", "skip"), default="write",
                        help="Record this run in the Project's POI tracking store "
                             "(.tarav/poi-tracking/), or leave the store untouched.")
    parser.set_defaults(handler=_check)


def _retained(project, run):
    """Keep the reported POIs so `tarav context --id` can open them afterwards."""
    from tarav.l1.poi.reporting import ReportedPOIStore

    try:
        identity = {"id": str(project.id), "name": project.name, "root": str(project.root)}
    except Exception:
        return run
    ReportedPOIStore().retain(run.pois(), project=identity)
    return run


# tarav.breadcrumb 0f714414fe0b5d467f093c13dbbacee44f95cc9708e21ee07ae0a693c81dc5e6
def _tracked(project, run) -> dict[str, object] | None:
    """Hand the whole run to the Project's tracker; a tracking failure never fails the check."""
    try:
        from tarav.l2.project.tracking import open_tracker

        return run.track(into=open_tracker(project), whole=True)
    except Exception as exc:
        print(f"POI tracking was not written: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None


def _tracking_line(tracked: dict[str, object]) -> str:
    axes = "; ".join(
        f"{key}: " + ", ".join(f"{value} {count}" for value, count in values.items())
        for key, values in tracked["by_axis"].items())
    return (f"POI tracking: {tracked['records']} records ({axes}); "
            f"{tracked['created']} new, {tracked['written']} written. "
            "List them with `tarav poi tracking list --project`.")


__all__ = ["register_check_command", "report_project_checks"]
