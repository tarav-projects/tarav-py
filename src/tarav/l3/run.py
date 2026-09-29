"""General configured Python runner CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from tarav.l1.python_env import (
    CurrentRunnerConfigurator,
    run_file,
    run_source,
)
from tarav.l2.project.runner import ProjectRunnerConfigurator


def _run(args: argparse.Namespace) -> int:
    configurator = (
        CurrentRunnerConfigurator()
        if args.project is None
        else ProjectRunnerConfigurator.from_path(args.project)
    )
    configuration = configurator.configure()
    if args.src is not None:
        return run_source(
            args.src,
            configuration=configuration,
            arguments=args.arguments,
        )
    return run_file(
        args.file,
        configuration=configuration,
        arguments=args.arguments,
    )


def register_run_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "run",
        help="Run explicit Python with current or Project configuration.",
    )
    parser.add_argument(
        "--project",
        type=Path,
        nargs="?",
        const=Path("."),
        help="Use the enclosing Project configuration; optionally start discovery at PATH.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--file",
        metavar="PATH",
        help="Script to run; - reads the script from standard input.",
    )
    source.add_argument("--src", metavar="SOURCE", help="Source to run directly.")
    parser.add_argument(
        "arguments",
        nargs="*",
        metavar="ARG",
        help="Arguments passed to the script, after a -- separator.",
    )
    parser.set_defaults(handler=_run)


__all__ = ["register_run_command"]
