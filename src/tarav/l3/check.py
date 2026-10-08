"""Project checks CLI: run a Project's checks namespace in its harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l1.checks import CheckResult, render_check_run


# tarav.breadcrumb a671fcec806bcecf6adccaf70a7f2c991f04b2685ea24f7056aa3cf53f820f8e
def report_project_checks(
    project, *, json_output: bool = False, by: str = "type", sort: str = "run",
    limit: int = 20, offset: int = 0, poi_type: str | None = None,
    code: str | None = None, check: str | None = None,
) -> int:
    """Run a Project's suite and show a bounded grouped report."""
    def progress(result: CheckResult) -> None:
        if sys.stderr.isatty():
            print(f"{type(result.check).__name__}: {result.status}", file=sys.stderr,
                  flush=True)

    try:
        run = project.checks.run(on_result=progress)
        # tarav.breadcrumb ad61e17278a7f87bdbe6bba00b7195dd5389a8f9423618314b32ae8fa446c9e2
    except NotImplementedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = run.report(by=by, sort=sort, limit=limit, offset=offset,
                        type=poi_type, code=code, check=check)
    if json_output:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render_check_run(report))
    return 0 if run.clean() else 1


def _code(args: argparse.Namespace) -> str:
    options = {
        "json_output": args.json, "by": args.by, "sort": args.sort,
        "limit": args.limit, "offset": args.offset, "poi_type": args.poi_type,
        "code": args.code, "check": args.check_type,
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
    parser.add_argument("--by", choices=("type", "code", "check", "identity"),
                        default="type", help="Group POIs by this field (default: type).")
    parser.add_argument("--sort", choices=("run", "count"), default="run",
                        help="Sort groups by first occurrence or descending count.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum groups to show.")
    parser.add_argument("--offset", type=int, default=0, help="First group to show.")
    parser.add_argument("--type", dest="poi_type", help="Filter by exact POI Type name.")
    parser.add_argument("--code", help="Filter by exact POI code.")
    parser.add_argument("--check", dest="check_type", help="Filter by exact Check Type name.")
    parser.set_defaults(handler=_check)


__all__ = ["register_check_command", "report_project_checks"]
