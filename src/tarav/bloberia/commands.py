# $kw: ^bloberia-commands --from Agentos.Bloberia --from POI.System --from POI.Linter --note [DF] thin argparse handlers over the importable BloberiaDepot and common POI report contracts ^c20260724-31u --supp POI migration execution ^c20260729-49u
from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from tarav._core.errors import CliError
from tarav._core.json_input import load_json_arg, load_json_object_arg

from .depot_v1 import BloberiaCheckResult, BloberiaDepot, BloberiaError, BloberiaRecord


class BloberiaCheckReport(Protocol):
    def as_dict(self) -> dict[str, object]: ...


BloberiaCheckReportBuilder = Callable[
    [BloberiaCheckResult, Path], BloberiaCheckReport
]


def _depot(args: argparse.Namespace) -> BloberiaDepot:
    return BloberiaDepot(Path(args.depot))


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _value_arg(args: argparse.Namespace) -> object:
    return load_json_arg(args.value_json, args.value_file, field_name="value")


def _record_payload(depot: BloberiaDepot, record: BloberiaRecord) -> dict[str, object]:
    return {"depot": str(depot.root), "record": record.as_dict()}


def _cmd_create(args: argparse.Namespace) -> int:
    depot = _depot(args)
    try:
        record = depot.create(_value_arg(args), namespace=args.namespace)
    except BloberiaError as exc:
        raise CliError(str(exc)) from exc
    _print_json(_record_payload(depot, record))
    return 0


def _cmd_get(args: argparse.Namespace) -> int:
    depot = _depot(args)
    try:
        record = depot.get(args.id, namespace=args.namespace)
    except BloberiaError as exc:
        raise CliError(str(exc)) from exc
    _print_json(_record_payload(depot, record))
    return 0


def _cmd_edit(args: argparse.Namespace) -> int:
    depot = _depot(args)
    try:
        record = depot.edit(args.id, _value_arg(args), namespace=args.namespace)
    except BloberiaError as exc:
        raise CliError(str(exc)) from exc
    _print_json(_record_payload(depot, record))
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    depot = _depot(args)
    query = load_json_object_arg(
        args.query_json,
        args.query_file,
        field_name="query",
    )
    try:
        records = depot.query(query, namespace=args.namespace)
    except BloberiaError as exc:
        raise CliError(str(exc)) from exc
    _print_json(
        {
            "depot": str(depot.root),
            "count": len(records),
            "records": [record.as_dict() for record in records],
        }
    )
    return 0


def _cmd_check(
    args: argparse.Namespace,
    *,
    report_builder: BloberiaCheckReportBuilder,
) -> int:
    depot = _depot(args)
    result = depot.check()
    _print_json(report_builder(result, depot.root).as_dict())
    return 0 if result.ok else 1


def _add_depot_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--depot", required=True, help="Exact Bloberia depot root.")


def _add_namespace_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--namespace",
        help=(
            "Placement-only record namespace under records/, as a relative path "
            "prefix. Omitted, reads walk every namespace and writes land at the root."
        ),
    )


def _add_record_id_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True, help="Opaque Bloberia record identity.")


def _add_value_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--value-json", help="Application value as JSON.")
    group.add_argument("--value-file", help="Path to an application-value JSON file.")


def register_bloberia_commands(
    subparsers: argparse._SubParsersAction,
    *,
    check_report_builder: BloberiaCheckReportBuilder,
) -> None:
    parser = subparsers.add_parser(
        "bloberia",
        help="Depot-scoped query:value storage for agent-associated data.",
    )
    commands = parser.add_subparsers(dest="bloberia_command", required=True)

    create_parser = commands.add_parser("create", help="Create a record.")
    _add_depot_argument(create_parser)
    _add_namespace_argument(create_parser)
    _add_value_arguments(create_parser)
    create_parser.set_defaults(handler=_cmd_create)

    get_parser = commands.add_parser("get", help="Read one record by identity.")
    _add_depot_argument(get_parser)
    _add_namespace_argument(get_parser)
    _add_record_id_argument(get_parser)
    get_parser.set_defaults(handler=_cmd_get)

    edit_parser = commands.add_parser(
        "edit", help="Atomically replace one record's application value."
    )
    _add_depot_argument(edit_parser)
    _add_namespace_argument(edit_parser)
    _add_record_id_argument(edit_parser)
    _add_value_arguments(edit_parser)
    edit_parser.set_defaults(handler=_cmd_edit)

    query_parser = commands.add_parser(
        "query", help="Select records by structural JSON subset."
    )
    _add_depot_argument(query_parser)
    _add_namespace_argument(query_parser)
    query_group = query_parser.add_mutually_exclusive_group()
    query_group.add_argument("--query-json", help="Structural query as a JSON object.")
    query_group.add_argument(
        "--query-file", help="Path to a structural-query JSON file."
    )
    query_parser.set_defaults(handler=_cmd_query)

    check_parser = commands.add_parser("check", help="Check depot structure.")
    _add_depot_argument(check_parser)
    check_parser.set_defaults(
        handler=lambda args: _cmd_check(
            args,
            report_builder=check_report_builder,
        )
    )


__all__ = ["BloberiaCheckReportBuilder", "register_bloberia_commands"]
