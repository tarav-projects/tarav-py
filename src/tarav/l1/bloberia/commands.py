"""Public CLI adapter for the hosted Tarav.Bloberia registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l0._core.json_input import load_json_arg

from .hosted import (
    TaravBloberia,
    TaravBloberiaError,
    default_tarav_bloberia_root,
)


def _root(value: str | None) -> Path:
    return (
        Path(value).expanduser().resolve()
        if value is not None
        else default_tarav_bloberia_root()
    )


def _print(payload: object) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


def _cmd_init(args: argparse.Namespace) -> int:
    try:
        bloberia = TaravBloberia.create(_root(args.bloberia))
    except TaravBloberiaError as exc:
        raise CliError(str(exc)) from exc
    _print(
        {
            "bloberia": str(bloberia.root),
            "command": "tarav bloberia init",
            "status": "ok",
        }
    )
    return 0


def _cmd_write(args: argparse.Namespace) -> int:
    try:
        bloberia = TaravBloberia.create(_root(args.bloberia))
        record = bloberia.write(
            load_json_arg(
                args.record_json,
                args.record_file,
                field_name="record",
            )
        )
    except TaravBloberiaError as exc:
        raise CliError(str(exc)) from exc
    _print(
        {
            "bloberia": str(bloberia.root),
            "command": "tarav bloberia write",
            "record": record,
            "status": "ok",
        }
    )
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    try:
        bloberia = TaravBloberia.open(_root(args.bloberia))
        records = (
            bloberia.search(args.text) if args.text is not None else bloberia.records()
        )
    except TaravBloberiaError as exc:
        raise CliError(str(exc)) from exc
    _print(
        {
            "bloberia": str(bloberia.root),
            "command": "tarav bloberia query",
            "count": len(records),
            "records": list(records),
            "status": "ok",
        }
    )
    return 0


def _add_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--bloberia",
        help="Tarav.Bloberia root; defaults to ~/Documents/tarav/bloberia.",
    )


def register_bloberia_commands(subparsers: argparse._SubParsersAction) -> None:
    bloberia = subparsers.add_parser(
        "bloberia",
        help="Store and search arbitrary Agent-managed JSON records.",
    )
    commands = bloberia.add_subparsers(
        dest="bloberia_command",
        required=True,
    )

    init = commands.add_parser(
        "init",
        help="Initialize the Tarav.Bloberia Git repository.",
    )
    _add_root(init)
    init.set_defaults(handler=_cmd_init)

    write = commands.add_parser("write", help="Store one arbitrary JSON record.")
    source = write.add_mutually_exclusive_group(required=True)
    source.add_argument("--record-json", help="Record as JSON.")
    source.add_argument("--record-file", help="Path to a JSON file.")
    _add_root(write)
    write.set_defaults(handler=_cmd_write)

    query = commands.add_parser(
        "query",
        help="Search the complete JSON content of every record.",
    )
    query.add_argument(
        "--text",
        help="Case-insensitive text matched against all JSON content.",
    )
    _add_root(query)
    query.set_defaults(handler=_cmd_query)


__all__ = ["register_bloberia_commands"]
