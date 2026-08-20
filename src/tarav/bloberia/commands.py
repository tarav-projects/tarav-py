# $kw: ^bloberia-commands --from Agentos.Bloberia --from POI.System --from POI.Linter --note [DF] thin argparse handlers over the importable BloberiaDepot and common POI report contracts ^c20260724-31u --supp POI migration execution ^c20260729-49u
"""The CLI surface, one subcommand per depot verb.

`get --id` and `edit --id` are gone rather than reimplemented. The store mints no
identity, so an id flag could only address a record through bloberia's private filename —
the one handle the contract keeps out of a consumer's hands. Both are recovered as
queries: a record with an identity of its own is found by naming that field.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from tarav._core.errors import CliError
from tarav._core.json_input import load_json_arg, load_json_object_arg

from .core import BloberiaCheckResult, BloberiaDepot, BloberiaError


class BloberiaCheckReport(Protocol):
    def as_dict(self) -> dict[str, object]: ...


BloberiaCheckReportBuilder = Callable[
    [BloberiaCheckResult, Path], BloberiaCheckReport
]


def _depot(args: argparse.Namespace) -> BloberiaDepot:
    return BloberiaDepot(Path(args.depot))


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _cargo_arg(args: argparse.Namespace) -> object:
    return load_json_arg(args.cargo_json, args.cargo_file, field_name="cargo")


def _query_arg(args: argparse.Namespace) -> dict[str, object]:
    return load_json_object_arg(args.query_json, args.query_file, field_name="query")


def _cmd_insert(args: argparse.Namespace) -> int:
    depot = _depot(args)
    try:
        depot.insert(_cargo_arg(args), namespace=args.namespace)
    except BloberiaError as exc:
        raise CliError(str(exc)) from exc
    _print_json({"depot": str(depot.root), "inserted": 1})
    return 0


def _cmd_first(args: argparse.Namespace) -> int:
    depot = _depot(args)
    try:
        cargo = depot.first(_query_arg(args), namespace=args.namespace)
    except BloberiaError as exc:
        raise CliError(str(exc)) from exc
    _print_json({"depot": str(depot.root), "found": cargo is not None, "record": cargo})
    return 0


def _cmd_all(args: argparse.Namespace) -> int:
    depot = _depot(args)
    try:
        cargos = depot.all(_query_arg(args), namespace=args.namespace)
    except BloberiaError as exc:
        raise CliError(str(exc)) from exc
    _print_json(
        {"depot": str(depot.root), "count": len(cargos), "records": list(cargos)}
    )
    return 0


def _cmd_replace(args: argparse.Namespace) -> int:
    depot = _depot(args)
    try:
        replaced = depot.replace(
            _query_arg(args), _cargo_arg(args), namespace=args.namespace
        )
    except BloberiaError as exc:
        raise CliError(str(exc)) from exc
    _print_json({"depot": str(depot.root), "replaced": replaced})
    return 0


def _cmd_delete(args: argparse.Namespace) -> int:
    depot = _depot(args)
    try:
        deleted = depot.delete(_query_arg(args), namespace=args.namespace)
    except BloberiaError as exc:
        raise CliError(str(exc)) from exc
    _print_json({"depot": str(depot.root), "deleted": deleted})
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


def _add_cargo_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--cargo-json", help="The record, verbatim, as JSON.")
    group.add_argument("--cargo-file", help="Path to a JSON file holding the record.")


def _add_query_arguments(
    parser: argparse.ArgumentParser, *, required: bool = False
) -> None:
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument(
        "--query-json",
        help='Path predicates as JSON, e.g. {"line.label": {"equals": "^c1-1u"}}.',
    )
    group.add_argument("--query-file", help="Path to a query JSON file.")


def register_bloberia_commands(
    subparsers: argparse._SubParsersAction,
    *,
    check_report_builder: BloberiaCheckReportBuilder,
) -> None:
    parser = subparsers.add_parser(
        "bloberia",
        help="Depot-scoped storage for opaque JSON records.",
    )
    commands = parser.add_subparsers(dest="bloberia_command", required=True)

    insert_parser = commands.add_parser("insert", help="Store one record verbatim.")
    _add_depot_argument(insert_parser)
    _add_namespace_argument(insert_parser)
    _add_cargo_arguments(insert_parser)
    insert_parser.set_defaults(handler=_cmd_insert)

    first_parser = commands.add_parser("first", help="Read the first matching record.")
    _add_depot_argument(first_parser)
    _add_namespace_argument(first_parser)
    _add_query_arguments(first_parser, required=True)
    first_parser.set_defaults(handler=_cmd_first)

    all_parser = commands.add_parser("all", help="Read every matching record.")
    _add_depot_argument(all_parser)
    _add_namespace_argument(all_parser)
    _add_query_arguments(all_parser)
    all_parser.set_defaults(handler=_cmd_all)

    replace_parser = commands.add_parser(
        "replace", help="Overwrite every matching record with one cargo."
    )
    _add_depot_argument(replace_parser)
    _add_namespace_argument(replace_parser)
    _add_query_arguments(replace_parser, required=True)
    _add_cargo_arguments(replace_parser)
    replace_parser.set_defaults(handler=_cmd_replace)

    delete_parser = commands.add_parser("delete", help="Delete every matching record.")
    _add_depot_argument(delete_parser)
    _add_namespace_argument(delete_parser)
    _add_query_arguments(delete_parser, required=True)
    delete_parser.set_defaults(handler=_cmd_delete)

    check_parser = commands.add_parser("check", help="Check that every record parses.")
    _add_depot_argument(check_parser)
    check_parser.set_defaults(
        handler=lambda args: _cmd_check(
            args,
            report_builder=check_report_builder,
        )
    )


__all__ = ["BloberiaCheckReportBuilder", "register_bloberia_commands"]
