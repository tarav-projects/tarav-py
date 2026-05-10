from __future__ import annotations

import argparse
import sys
from typing import Sequence

from agentos import __version__
from agentos.agent import register_agent_commands
from agentos._core.errors import CliError
from agentos.canvas import register_canvas_commands
from agentos.chatlas import register_chatlas_commands
from agentos.codex import register_codex_commands
from agentos.forum import register_forum_commands
from agentos.index.commands import register_index_commands
from agentos.mdblocks.commands import register_mdblocks_commands
from agentos.mission import register_mission_commands
from agentos.prefix.commands import register_prefix_commands
from agentos.project import register_project_commands
from agentos.refs import register_refs_commands
from agentos.skills import register_skills_commands
from agentos.system import register_system_commands
from agentos.tara_tapes import register_tara_tapes_commands
from agentos.utils import register_utils_commands


def register_stdlib_commands(subparsers: argparse._SubParsersAction) -> None:
    stdlib_parser = subparsers.add_parser(
        "stdlib",
        help="Standard-library primitives used by higher-level Agentos surfaces.",
    )
    stdlib_subparsers = stdlib_parser.add_subparsers(
        dest="stdlib_command",
        required=True,
    )
    register_mdblocks_commands(stdlib_subparsers)
    register_prefix_commands(stdlib_subparsers)
    register_refs_commands(stdlib_subparsers)
    register_utils_commands(stdlib_subparsers)


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
    register_agent_commands(subparsers)
    register_canvas_commands(subparsers)
    register_codex_commands(subparsers)
    register_project_commands(subparsers)
    register_system_commands(subparsers)
    register_chatlas_commands(subparsers)
    register_forum_commands(subparsers)
    register_tara_tapes_commands(subparsers)
    register_stdlib_commands(subparsers)
    register_skills_commands(subparsers)
    register_index_commands(subparsers)
    register_mission_commands(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        argv_list = list(argv) if argv is not None else sys.argv[1:]
        args = parser.parse_args(argv_list)
        args._agentos_argv = argv_list
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
