from __future__ import annotations

import argparse
import json
from uuid import UUID, uuid4

from agentos._core.errors import CliError


def _generate_uuid4() -> str:
    return str(uuid4())


def _validate_generated_uuid(value: str) -> str:
    # Defensive validation: guarantees canonical UUID string output.
    parsed = UUID(value)
    return str(parsed)


def _cmd_utils_uuid(args: argparse.Namespace) -> int:
    count = int(args.count)
    if count < 1:
        raise CliError("--count must be >= 1")

    uuids = [_validate_generated_uuid(_generate_uuid4()) for _ in range(count)]

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
