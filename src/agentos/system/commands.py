from __future__ import annotations

import argparse
import json
import platform
import sys

from agentos import __version__
from agentos.skills.commands import list_skill_names, resolve_project_root, skills_dir


def _cmd_doctor(_: argparse.Namespace) -> int:
    data = {
        "agentos_version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "project_root": str(resolve_project_root()),
        "skills_dir": str(skills_dir()),
        "skills_count": len(list_skill_names()),
    }
    print(json.dumps(data, indent=2))
    return 0


def _cmd_test(args: argparse.Namespace) -> int:
    payload = {
        "status": "ok",
        "command": "test",
        "python_version": platform.python_version(),
    }

    if args.json_output:
        print(json.dumps(payload))
    else:
        print(f"agentos test OK (python {payload['python_version']})")
    return 0


def register_system_commands(subparsers: argparse._SubParsersAction) -> None:
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Print environment and project diagnostics.",
    )
    doctor_parser.set_defaults(handler=_cmd_doctor)

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
