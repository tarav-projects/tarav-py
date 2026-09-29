# $kw: --from Usage.Surface --from Agentos.Project
from __future__ import annotations

import argparse
import json
import platform


def _cmd_test(args: argparse.Namespace) -> int:
    payload = {
        "status": "ok",
        "command": "test",
        "python_version": platform.python_version(),
    }

    if args.json_output:
        print(json.dumps(payload))
    else:
        print(f"tarav test OK (python {payload['python_version']})")
    return 0


def register_system_commands(subparsers: argparse._SubParsersAction) -> None:
    test_parser = subparsers.add_parser(
        "test",
        help="Run a smoke test to verify CLI wiring.",
    )
    test_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON.",
    )
    test_parser.set_defaults(handler=_cmd_test)
