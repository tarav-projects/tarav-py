"""Project checks CLI: run a Project's checks in its harness and report the POIs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l1.checks import CheckResult, routine
from tarav.l1.poi.rendering import (
    DEFAULT_POI_RENDERER, POISelection, renderer, renderers,
)


class Progress:
    """One line that counts the checks as they finish; nothing when not on a terminal."""

    def __init__(self) -> None:
        self.count = 0
        self.live = sys.stderr.isatty()

    def __call__(self, result: CheckResult) -> None:
        self.count += 1
        if self.live:
            print(f"\r{self.count} checks ran", end="", file=sys.stderr, flush=True)

    def done(self) -> None:
        if self.live and self.count:
            print("\r" + " " * 24 + "\r", end="", file=sys.stderr, flush=True)


# tarav.breadcrumb a671fcec806bcecf6adccaf70a7f2c991f04b2685ea24f7056aa3cf53f820f8e
# tarav.breadcrumb 31d6a87727d93d79dc92f3804e9916b37f4a8d7639862d3ef2fe9144dc778ee1
def report_project_checks(
    project, *, json_output: bool = False, by: str = "type", sort: str = "run",
    limit: int = 20, offset: int = 0, poi_type: str | None = None,
    check: str | None = None, renderer_name: str = DEFAULT_POI_RENDERER,
    level: str = "line", everything: bool = False,
) -> int:
    """Run a Project's checks and show a bounded grouped report. Nothing else happens.

    Suites that are not routine are left out unless `everything` is set.
    """
    progress = Progress()
    try:
        run = project.checks.run(select=None if everything else routine, on_result=progress)
        # tarav.breadcrumb ad61e17278a7f87bdbe6bba00b7195dd5389a8f9423618314b32ae8fa446c9e2
    except NotImplementedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        progress.done()
    report = run.report(by=by, sort=sort, limit=limit, offset=offset, type=poi_type,
                        check=check, detail=level == "record")
    if json_output:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(renderer(renderer_name).render(POISelection.from_check_report(report), level=level))
    return 0 if run.clean() else 1


def in_harness(args: argparse.Namespace, *, command: str, module: str, function: str,
               options: dict) -> int:
    """Run one report function on the Project, inside the Project's harness."""
    if args.project is None:
        raise CliError(f"{command} needs --project [PATH]")
    from tarav.l3.project.harness import run

    return run(path=args.project, code=(
        f"from {module} import {function}\n"
        f"raise SystemExit({function}(project, **{options!r}))\n"))


# tarav.breadcrumb 1778a37c1707becb0bed583cc5d2ee8f8a4b3047975fb3b90d1c61a0a8065481
def _check(args: argparse.Namespace) -> int:
    return in_harness(args, command="tarav check", module="tarav.l3.check",
                      function="report_project_checks", options={
                          "json_output": args.json, "by": args.by, "sort": args.sort,
                          "limit": args.limit, "offset": args.offset,
                          "poi_type": args.poi_type, "check": args.check_type,
                          "renderer_name": args.renderer, "level": args.level,
                          "everything": args.all})


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
    parser.add_argument("--level", choices=("line", "record"), default="line",
                        help="POI detail level for rendered output.")
    parser.add_argument("--all", action="store_true",
                        help="Run every suite. Without it, suites that are not part of the "
                             "routine run are left out, such as a Project's pytest tests.")


def register_check_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "check",
        help="Run a Project's checks in its harness and report the POIs. "
             "It does not touch the Project's actions; `tarav status` does.",
        epilog=(
            "examples:\n"
            "  tarav check --project\n"
            "  tarav check --project /path/to/project --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _report_arguments(parser)
    parser.set_defaults(handler=_check)


__all__ = ["Progress", "in_harness", "register_check_command", "report_project_checks"]
