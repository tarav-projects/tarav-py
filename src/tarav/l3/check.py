"""Project checks CLI: run a Project's checks() in its harness environment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l1.checks import CheckResult, check_report


def _run_one(check) -> CheckResult:
    try:
        return check.run()
    except Exception as exc:  # a crashing Check is reported, not fatal
        return CheckResult(check, status="failed", reason=f"{type(exc).__name__}: {exc}")


def _print_result(row: dict) -> None:
    print(f"{row['check']}: {row['status']} ({len(row['pois'])} POIs)", flush=True)
    if row["reason"]:
        print(f"  reason: {row['reason']}", flush=True)
    for poi in row["pois"]:
        label = poi.get("code") or poi.get("type")
        print(f"  - {label}: {poi.get('message', '')}", flush=True)


# tarav.breadcrumb a671fcec806bcecf6adccaf70a7f2c991f04b2685ea24f7056aa3cf53f820f8e
def report_project_checks(project, *, json_output: bool = False) -> int:
    """Run each of project.checks() as it arrives, print, and return the exit code.

    Text output streams one result at a time; JSON prints once at the end.
    0 when every Check completed without POIs, 1 otherwise, 2 when the
    Project declares no checks. The code informs callers; it blocks nothing.
    """
    results = []
    try:
        for check in project.checks():
            result = _run_one(check)
            results.append(result)
            if not json_output:
                _print_result(check_report([result])["results"][0])
    except NotImplementedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = check_report(results)
    if json_output:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"{report['checks']} checks, {report['incomplete']} incomplete, "
              f"{report['pois']} POIs")
    return 0 if report["incomplete"] == 0 and report["pois"] == 0 else 1


def _code(json_output: bool) -> str:
    return (
        "from tarav.l3.check import report_project_checks\n"
        f"raise SystemExit(report_project_checks(project, json_output={json_output!r}))\n"
    )


# tarav.breadcrumb 1778a37c1707becb0bed583cc5d2ee8f8a4b3047975fb3b90d1c61a0a8065481
def _check(args: argparse.Namespace) -> int:
    if args.project is None:
        raise CliError("tarav check needs --project [PATH]")
    from tarav.l3.project.harness import run

    return run(path=args.project, code=_code(args.json))


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
    parser.set_defaults(handler=_check)


__all__ = ["register_check_command", "report_project_checks"]
