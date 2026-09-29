"""Public CLI for the Python environment that runs Tarav."""

from __future__ import annotations

import argparse
import json
import platform

from .core import environment_root, interpreter, run_file, run_source


def _cmd_path(args: argparse.Namespace) -> int:
    if args.json:
        print(
            json.dumps(
                {
                    "status": "ok",
                    "command": "tarav python path",
                    "interpreter": str(interpreter()),
                    "prefix": str(environment_root()),
                    "version": platform.python_version(),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(interpreter())
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    if args.src is not None:
        return run_source(args.src, args.arguments)
    return run_file(args.file, args.arguments)


def register_python_commands(subparsers: argparse._SubParsersAction) -> None:
    python = subparsers.add_parser(
        "python",
        help="Use the Python environment that runs Tarav.",
    )
    commands = python.add_subparsers(dest="python_command", required=True)

    path = commands.add_parser(
        "path",
        help="Print the interpreter running Tarav.",
    )
    path.add_argument("--json", action="store_true", help="Print structured JSON.")
    path.set_defaults(handler=_cmd_path)

    runner = commands.add_parser(
        "run",
        help="Run a script with the Tarav interpreter.",
        description=(
            "Run a script with the interpreter that runs Tarav, so the script "
            "can import Tarav without installing it. Arguments for the script "
            "itself follow a -- separator."
        ),
        epilog=(
            "examples:\n"
            "  tarav python run --file probe.py\n"
            "  tarav python run --file probe.py -- --limit 5\n"
            '  tarav python run --src "import tarav; print(tarav.__version__)"\n'
            "  tarav python run --file - <<'PY'\n"
            "  import tarav\n"
            "  PY"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    script = runner.add_mutually_exclusive_group(required=True)
    script.add_argument(
        "--file",
        metavar="PATH",
        help="Script to run; - reads the script from standard input.",
    )
    script.add_argument(
        "--src",
        metavar="SOURCE",
        help="Source to run directly.",
    )
    runner.add_argument(
        "arguments",
        nargs="*",
        metavar="ARG",
        help="Arguments passed to the script, after a -- separator.",
    )
    runner.set_defaults(handler=_cmd_run)


__all__ = ["register_python_commands"]
