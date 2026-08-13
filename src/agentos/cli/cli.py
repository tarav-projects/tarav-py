# $kw: ^agentos-cli --from Agentos.Bloberia --from Skw.Edition.History.Service --from Anchory.System --from Chatlas.Anchory --from Agentos.Hook --from Agentos.Daemon --note [DC] the umbrella CLI composes foundation command registrars with feature-owned integrations ^c20260724-31u --supp live Chatlas resolution injection authorized ^c20260725-15u --supp Anchory amendment validation authorized ^c20260730-33u --supp general hook composition authorized ^c20260811-35u --supp daemon-owned hook dispatch authorized ^c20260813-27u
from __future__ import annotations

import argparse
import sys
from typing import Sequence

from agentos import __version__
from agentos._core.errors import CliError
from agentos.runtime import AgentosRuntime, HookRegistrar, create_runtime


def build_parser(
    *,
    runtime: AgentosRuntime | None = None,
    hook_registrars: Sequence[HookRegistrar] = (),
) -> argparse.ArgumentParser:
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
    composed = runtime or create_runtime(hook_registrars=hook_registrars)
    composed.register_commands(subparsers)
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
