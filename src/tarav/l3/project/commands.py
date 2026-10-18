"""Explicit adapters for Project-local harness operations."""

import argparse
import json
from pathlib import Path

from tarav.l2.project.harness import ProjectHarness
from tarav.l1.project.index import observe_project


# tarav.breadcrumb c8dbdc6986b7
def _inspect(args):
    harness = ProjectHarness.from_path(path=args.project)
    result = harness.inspect()
    observe_project(harness.root)
    print(json.dumps(result, indent=2))
    return 0


def _scaffold(args):
    harness = ProjectHarness.scaffold(
        path=args.project,
        package=args.package,
        class_name=args.class_name,
        tarav_source=args.tarav_source,
        adopt=args.adopt,
    )
    observe_project(harness.root)
    print(json.dumps(harness.inspect(), indent=2))
    return 0


def _sync(args):
    harness = ProjectHarness.from_path(path=args.project)
    harness.sync(python=args.python)
    observe_project(harness.root)
    return 0


# tarav.breadcrumb cda75bb67890
def register_harness_commands(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "harness",
        help="Inspect, scaffold and sync a Project-local Python harness.",
    )
    operations = parser.add_subparsers(dest="harness_command", required=True)
    for operation, handler in (
        ("inspect", _inspect),
        ("scaffold", _scaffold),
        ("sync", _sync),
    ):
        child = operations.add_parser(operation)
        child.add_argument(
            "--project", type=Path, nargs="?", const=Path("."), default=Path(".")
        )
        child.set_defaults(handler=handler)
        if operation == "scaffold":
            child.add_argument("--package", required=True)
            child.add_argument("--class-name", default="MyProject")
            child.add_argument("--tarav-source", type=Path, required=True)
            child.add_argument(
                "--adopt",
                action="store_true",
                help="Explicitly retype an existing base/untyped marker; preserve its identity and metadata.",
            )
        elif operation == "sync":
            child.add_argument(
                "--python",
                help="Interpreter for a new environment; existing environments are preserved.",
            )
