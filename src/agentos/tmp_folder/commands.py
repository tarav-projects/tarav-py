from __future__ import annotations

import argparse
from pathlib import Path
from uuid import uuid4

from agentos._core.errors import CliError
from agentos._core.project import project_agentos_dir, require_agentos_project_root


def _cmd_tmp_folder_new(args: argparse.Namespace) -> int:
    project_root = require_agentos_project_root(Path.cwd())
    tmp_root = project_agentos_dir(project_root) / "tmp"

    max_attempts = 32
    folder_path: Path | None = None
    for _ in range(max_attempts):
        candidate = (tmp_root / f"tmp-{uuid4().hex}").resolve()
        if args.create:
            try:
                candidate.mkdir(parents=True, exist_ok=False)
                folder_path = candidate
                break
            except FileExistsError:
                continue
        elif not candidate.exists():
            folder_path = candidate
            break

    if folder_path is None:
        raise CliError(f"unable to allocate unique tmp-folder path under: {tmp_root}")

    print(str(folder_path))
    return 0


def register_tmp_folder_commands(subparsers: argparse._SubParsersAction) -> None:
    tmp_folder_parser = subparsers.add_parser(
        "tmp-folder",
        help="Create temporary folders under .agentos/tmp.",
    )
    tmp_folder_subparsers = tmp_folder_parser.add_subparsers(
        dest="tmp_folder_command",
        required=True,
    )

    tmp_folder_new_parser = tmp_folder_subparsers.add_parser(
        "new",
        help="Generate a random tmp-folder path under .agentos/tmp.",
    )
    tmp_folder_new_parser.add_argument(
        "--create",
        action="store_true",
        help="Create the generated folder. By default only prints the path.",
    )
    tmp_folder_new_parser.set_defaults(handler=_cmd_tmp_folder_new)
