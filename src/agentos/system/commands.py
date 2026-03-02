from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

from agentos import __version__
from agentos._core.project import (
    SCOPE_VALUES,
    find_agentos_project_root,
    global_storage_paths,
    local_storage_paths,
    resolve_scope_storage_paths,
)
from agentos.utils.skills import list_skill_names, resolve_project_root, skills_dir


def _serialize_path_map(payload: dict[str, Path]) -> dict[str, str]:
    return {name: str(path) for name, path in payload.items()}


def _cmd_doctor(args: argparse.Namespace) -> int:
    cwd = Path.cwd().resolve()
    project_root = find_agentos_project_root(cwd)
    inside_project = project_root is not None

    effective_scope, effective_paths, effective_project_root = resolve_scope_storage_paths(
        args.scope,
        start_path=cwd,
    )
    effective_agentos_dir = effective_paths["agentos_dir"]

    project_paths: dict[str, str] | None = None
    if project_root is not None:
        project_paths = _serialize_path_map(local_storage_paths(project_root))

    data = {
        "agentos_version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cwd": str(cwd),
        "inside_agentos_project": inside_project,
        "project_root": str(project_root) if project_root is not None else None,
        "project_paths": project_paths,
        "global_paths": _serialize_path_map(global_storage_paths()),
        "requested_scope": args.scope,
        "effective_scope": effective_scope,
        "effective_agentos_dir": str(effective_agentos_dir),
        "effective_tapes_dir": str(effective_paths["tapes"]),
        "effective_indexes_dir": str(effective_paths["indexes"]),
        "effective_tmp_dir": str(effective_paths["tmp"]),
        "effective_project_root": (
            str(effective_project_root) if effective_project_root is not None else None
        ),
        "package_project_root": str(resolve_project_root()),
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
    doctor_parser.add_argument(
        "--scope",
        choices=list(SCOPE_VALUES),
        default="auto",
        help="Resolve effective storage paths for this scope (default: auto).",
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
