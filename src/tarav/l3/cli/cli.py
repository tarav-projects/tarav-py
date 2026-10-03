# $kw: ^agentos-cli --from Agentos.Bloberia --from Skw.Edition.History.Service --from Anchory.System --from Chatlas.Anchory --from Agentos.Hook --from Agentos.Daemon --note [DC] the umbrella CLI composes foundation command registrars with feature-owned integrations ^c20260724-31u --supp live Chatlas resolution injection authorized ^c20260725-15u --supp Anchory amendment validation authorized ^c20260730-33u --supp general hook composition authorized ^c20260811-35u --supp daemon-owned hook dispatch authorized ^c20260813-27u
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from time import perf_counter
from typing import Sequence

from tarav import __version__
from tarav.l0._core.errors import CliError
from tarav.l0._core.operational_logging import configure_operational_logging
from tarav.l3.runtime import TaravRuntime, HookRegistrar, create_runtime
from tarav.l1.cli import Command, CliWorkflow, commands_from_parser
from tarav.l1.live_help import LiveHelpArgumentParser, render_live_help


def _safe_options(
    argv: Sequence[str], root: argparse.ArgumentParser, command: Command,
) -> list[str]:
    """Record option names only; option and remainder values may be secrets."""
    known: set[str] = set()
    node = root
    known.update(option for action in node._actions for option in action.option_strings)
    for segment in command.path:
        branch = next(
            (action for action in node._actions
             if isinstance(action, argparse._SubParsersAction) and segment in action.choices),
            None,
        )
        if branch is None:
            break
        node = branch.choices[segment]
        known.update(option for action in node._actions for option in action.option_strings)
    names: list[str] = []
    for word in argv:
        if word == "--":
            break
        if word.startswith("-") and word != "-":
            name = word.split("=", 1)[0]
            if name in known and name not in names:
                names.append(name)
    return names


# tarav.breadcrumb d5c2c85ac9548726cf6c417c56b639efeda056143548f190e445113aafbb9cd1
def build_parser(
    *,
    runtime: TaravRuntime | None = None,
    hook_registrars: Sequence[HookRegistrar] = (),
) -> argparse.ArgumentParser:
    parser = LiveHelpArgumentParser(
        prog="tarav",
        description="Core CLI primitives for agentic workflows.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command")
    composed = runtime or create_runtime(hook_registrars=hook_registrars)
    composed.register_commands(subparsers)
    for command in commands_from_parser(parser):
        command.parser.set_defaults(_tarav_command=command)
        command.parser.live_help = (
            lambda command=command: render_live_help(command, composed.usage)
        )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    configure_operational_logging()
    runtime = create_runtime()
    parser = build_parser(runtime=runtime)
    started = perf_counter()
    command: Command | None = None
    exit_code: int | None = None
    try:
        argv_list = list(argv) if argv is not None else sys.argv[1:]
        args = parser.parse_args(argv_list)
        command = getattr(args, "_tarav_command", None)
        args._agentos_argv = argv_list
        handler = getattr(args, "handler", None)
        if handler is None:
            parser.print_help()
            return 0
        exit_code = int(handler(args))
        return exit_code
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        exit_code = 1
        return 1
    finally:
        if command is not None and getattr(command, "handler", None) is not None:
            runtime.usage.record(
                workflow=CliWorkflow,
                subject=command.help_subject,
                payload={
                    "exit_code": exit_code,
                    "duration_ms": round((perf_counter() - started) * 1000),
                    "cwd": str(Path.cwd()),
                    "options": _safe_options(argv_list, parser, command),
                },
            )


if __name__ == "__main__":
    raise SystemExit(main())
