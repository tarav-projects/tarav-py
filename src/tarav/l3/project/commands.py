"""Explicit adapters for Project-local harness operations."""

import argparse
import json
from pathlib import Path

from tarav.l2.project.harness import ProjectHarness
from tarav.l3.project.harness import run


def _inspect(args):
    print(json.dumps(ProjectHarness.from_path(path=args.project).inspect(), indent=2))
    return 0


def _scaffold(args):
    harness = ProjectHarness.scaffold(
        path=args.project,
        package=args.package,
        class_name=args.class_name,
        tarav_source=args.tarav_source,
        adopt=args.adopt,
    )
    print(json.dumps(harness.inspect(), indent=2))
    return 0


def _sync(args):
    ProjectHarness.from_path(path=args.project).sync(python=args.python)
    return 0


def _run(args):
    arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    return run(path=args.project, code=args.code, file=args.file, arguments=arguments)


def register_harness_commands(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "harness",
        help="Inspect, scaffold, sync and run a Project-local Python harness.",
    )
    operations = parser.add_subparsers(dest="harness_command", required=True)
    for operation, handler in (
        ("inspect", _inspect),
        ("scaffold", _scaffold),
        ("sync", _sync),
        ("run", _run),
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
        elif operation == "run":
            source = child.add_mutually_exclusive_group()
            source.add_argument("--code")
            source.add_argument("--file", type=Path)
            child.add_argument("arguments", nargs=argparse.REMAINDER)
