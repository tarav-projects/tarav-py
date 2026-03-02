from __future__ import annotations

import argparse
import json

from agentos._core.errors import CliError
from agentos._core.ids import generate_uuid4_string, validate_uuid_string
from agentos.utils.tmp_folder import allocate_project_tmp_folder


def _cmd_utils_uuid(args: argparse.Namespace) -> int:
    count = int(args.count)
    if count < 1:
        raise CliError("--count must be >= 1")

    uuids = [validate_uuid_string(generate_uuid4_string()) for _ in range(count)]

    if args.json:
        payload: dict[str, object] = {
            "status": "ok",
            "command": "utils uuid",
            "count": count,
            "uuids": uuids,
        }
        if count == 1:
            payload["uuid"] = uuids[0]
        print(json.dumps(payload))
        return 0

    print("\n".join(uuids))
    return 0


def _cmd_utils_tmp_folder_new(args: argparse.Namespace) -> int:
    folder_path = allocate_project_tmp_folder(
        create=bool(args.create),
    )
    print(str(folder_path))
    return 0


def register_utils_commands(subparsers: argparse._SubParsersAction) -> None:
    utils_parser = subparsers.add_parser(
        "utils",
        help="General utility helpers for agents.",
    )
    utils_subparsers = utils_parser.add_subparsers(dest="utils_command", required=True)

    uuid_parser = utils_subparsers.add_parser(
        "uuid",
        help="Generate UUIDv4 identifiers.",
    )
    uuid_parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of UUIDs to generate.",
    )
    uuid_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON payload with generated UUIDs.",
    )
    uuid_parser.set_defaults(handler=_cmd_utils_uuid)

    tmp_folder_parser = utils_subparsers.add_parser(
        "tmp-folder",
        help="Create temporary folders under .agentos/tmp.",
    )
    tmp_folder_subparsers = tmp_folder_parser.add_subparsers(
        dest="utils_tmp_folder_command",
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
    tmp_folder_new_parser.set_defaults(handler=_cmd_utils_tmp_folder_new)
