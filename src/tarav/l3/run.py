"""General configured Python runner CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l1.python_env import CurrentRunnerConfigurator, run_python
from tarav.l2.project.runner import ProjectRunnerConfigurator


# tarav.breadcrumb 327c61e63acb8b7e699f39d0eb3ffac13cac61e1dd52413836a84e381a15e68a
def _run(args: argparse.Namespace) -> int:
    if not args.arguments or args.arguments[0] != "--" or len(args.arguments) == 1:
        raise CliError("Expected Python arguments after -- (for example: tarav run -- script.py)")
    configurator = (
        CurrentRunnerConfigurator()
        if args.project is None
        else ProjectRunnerConfigurator.from_path(args.project)
    )
    return run_python(args.arguments[1:], configuration=configurator.configure())


def register_run_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "run",
        help="Run Python with current or Project configuration.",
        epilog=(
            "examples:\n"
            "  tarav run -- script.py --flag value\n"
            "  tarav run --project -- script.py\n"
            "  tarav run --project /path/to/project -- script.py\n"
            "  tarav run --project /path/to/project -- -c 'print(1)'"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # tarav.breadcrumb f2341073c5f386a76ab6c6b07e20d1e5befb8dce1d1e3957320b8a5a7f60c4db
    parser.add_argument(
        "--project",
        type=Path,
        nargs="?",
        const=Path("."),
        help="Search this directory and parents for a Project; optionally start at PATH.",
    )
    parser.add_argument(
        "arguments",
        nargs=argparse.REMAINDER,
        metavar="PYTHON_ARG",
        help="After --, arguments passed unchanged to Python.",
    )
    parser.set_defaults(handler=_run)


__all__ = ["register_run_command"]
