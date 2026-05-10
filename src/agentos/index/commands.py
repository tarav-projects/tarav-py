"""CLI commands for agentos index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .doctor import run_doctor


def _cmd_doctor(args: argparse.Namespace) -> int:
    report = run_doctor(root=args.root, emit_json=args.json)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        if report.get("status") == "error" and report.get("index_dir") is None:
            print(f"Error: {report['message']}")
            return 1

        issue_count = report["issue_count"]
        file_count = report["file_count"]

        if issue_count == 0:
            print(f"Index healthy: {file_count} file(s), no issues found.")
        else:
            print(
                f"Scanned {file_count} file(s): "
                f"{report['error_count']} error(s), {report['warning_count']} warning(s)"
            )
            for issue in report["issues"]:
                print(
                    f"  [{issue['severity'].upper()}] {issue['code']} "
                    f"@ {issue['path']} - {issue['message']}"
                )

    if report.get("error_count", 0) > 0:
        return 1
    return 0


def register_index_commands(subparsers: argparse._SubParsersAction) -> None:
    index_parser = subparsers.add_parser(
        "index",
        help="Index knowledge surface operations.",
    )
    index_subparsers = index_parser.add_subparsers(dest="index_command")

    doctor_parser = index_subparsers.add_parser(
        "doctor",
        help="Run health checks on notes/index/.",
    )
    doctor_parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Project root directory (default: current directory).",
    )
    doctor_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON output.",
    )
    doctor_parser.set_defaults(handler=_cmd_doctor)
