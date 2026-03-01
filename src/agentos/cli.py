from __future__ import annotations

import argparse
import sys
from typing import Sequence

from agentos import __version__
from agentos._core.errors import CliError
from agentos.mdblocks.commands import register_mdblocks_commands
from agentos.prefix.commands import register_prefix_commands
from agentos.refs import register_refs_commands
from agentos.skills import register_skills_commands
from agentos.system import register_system_commands
from agentos.tape import register_tape_commands


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentos",
        description="Core CLI primitives for agentic workflows.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command")
    register_system_commands(subparsers)
    register_tape_commands(subparsers)
    register_refs_commands(subparsers)
    register_skills_commands(subparsers)
    register_prefix_commands(subparsers)
    register_mdblocks_commands(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        handler = getattr(args, "handler", None)
        if handler is None:
            parser.print_help()
            return 0
        return int(handler(args))
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
