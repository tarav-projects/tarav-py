"""Public CLI for the Python environment that runs Tarav."""

from __future__ import annotations

import argparse
import json
import platform

from .core import environment_root, interpreter


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


# tarav.breadcrumb 301a46f1f2fea8453e61253f9beb750a7d61cc60f73e3cfac6553f075fa34742
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

__all__ = ["register_python_commands"]
