from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.json_input import load_json_object_arg

from .core import AnchoryDepot, AnchoryEntry, AnchoryError
from .core import AnchorySourceMatch, scan_anchory_source


def _depot(args: argparse.Namespace) -> AnchoryDepot:
    return AnchoryDepot(Path(args.depot))


def _entry_payload(depot: AnchoryDepot, entry: AnchoryEntry) -> dict[str, object]:
    return {
        "depot": str(depot.root),
        "anchor": entry.anchor,
        "record": entry.record,
    }


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _record_arg(args: argparse.Namespace) -> dict[str, object]:
    return load_json_object_arg(
        args.record_json,
        args.record_file,
        field_name="record",
    )


def _cmd_register(args: argparse.Namespace) -> int:
    depot = _depot(args)
    try:
        entry = depot.register(args.anchor, _record_arg(args))
    except AnchoryError as exc:
        raise CliError(str(exc)) from exc
    _print_json(_entry_payload(depot, entry))
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    depot = _depot(args)
    try:
        record = depot.resolve(args.anchor)
    except AnchoryError as exc:
        raise CliError(str(exc)) from exc
    if record is None:
        raise CliError(f"anchor does not exist: {args.anchor}")
    _print_json(_entry_payload(depot, AnchoryEntry(anchor=args.anchor, record=record)))
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    depot = _depot(args)
    try:
        entries = depot.query(prefix=args.prefix)
    except AnchoryError as exc:
        raise CliError(str(exc)) from exc
    _print_json(
        {
            "depot": str(depot.root),
            "count": len(entries),
            "entries": [
                {"anchor": entry.anchor, "record": entry.record} for entry in entries
            ],
        }
    )
    return 0


def _cmd_amend(args: argparse.Namespace) -> int:
    depot = _depot(args)
    try:
        entry = depot.amend(args.anchor, _record_arg(args))
    except AnchoryError as exc:
        raise CliError(str(exc)) from exc
    _print_json(_entry_payload(depot, entry))
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    depot = _depot(args)
    result = depot.check()
    _print_json(
        {
            "depot": str(depot.root),
            "status": "ok" if result.ok else "error",
            "findings": [
                {
                    "code": finding.code,
                    "path": finding.path,
                    "message": finding.message,
                    **({"anchor": finding.anchor} if finding.anchor is not None else {}),
                }
                for finding in result.findings
            ],
        }
    )
    return 0 if result.ok else 1


def _scan_payload(
    *,
    depot: AnchoryDepot,
    src_file: Path,
    regex: str,
    matches: tuple[AnchorySourceMatch, ...],
) -> dict[str, object]:
    return {
        "depot": str(depot.root),
        "src_file": str(src_file),
        "regex": regex,
        "count": len(matches),
        "matches": [
            {
                "anchor": match.anchor,
                "line": match.line,
                "column": match.column,
                "start": match.start,
                "end": match.end,
                "record": depot.resolve(match.anchor),
            }
            for match in matches
        ],
    }


def _print_scan_human(payload: dict[str, object]) -> None:
    print("Anchory scan")
    print(f"depot: {payload['depot']}")
    print(f"source: {payload['src_file']}")
    print(f"regex: {payload['regex']}")
    print(f"{payload['count']} match(es)")
    for match in payload["matches"]:  # type: ignore[index]
        print(
            f"- {match['anchor']} @ line {match['line']}, "  # type: ignore[index]
            f"column {match['column']}"  # type: ignore[index]
        )
        record = match["record"]  # type: ignore[index]
        if record is None:
            print("  record: missing")
        else:
            print(f"  record: {json.dumps(record, sort_keys=True)}")


def _cmd_scan(args: argparse.Namespace) -> int:
    depot = _depot(args)
    src_file = Path(args.src_file).expanduser().resolve()
    try:
        text = src_file.read_text(encoding="utf-8")
        matches = scan_anchory_source(text, args.regex)
        payload = _scan_payload(
            depot=depot,
            src_file=src_file,
            regex=args.regex,
            matches=matches,
        )
    except (OSError, AnchoryError) as exc:
        raise CliError(str(exc)) from exc
    if args.json:
        _print_json(payload)
    else:
        _print_scan_human(payload)
    return 0


def _add_depot_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--depot",
        required=True,
        help="Exact Anchory depot root.",
    )


def _add_anchor_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--anchor", required=True, help="Anchor key.")


def _add_record_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--record-json", help="Record as a JSON object.")
    group.add_argument("--record-file", help="Path to a JSON record file.")


def register_anchory_commands(subparsers: argparse._SubParsersAction) -> None:
    anchory_parser = subparsers.add_parser(
        "anchory",
        help="Depot-scoped stable anchor dictionaries.",
    )
    anchory_subparsers = anchory_parser.add_subparsers(
        dest="anchory_command",
        required=True,
    )

    register_parser = anchory_subparsers.add_parser("register", help="Register an anchor.")
    _add_depot_argument(register_parser)
    _add_anchor_argument(register_parser)
    _add_record_arguments(register_parser)
    register_parser.set_defaults(handler=_cmd_register)

    resolve_parser = anchory_subparsers.add_parser("resolve", help="Resolve an anchor.")
    _add_depot_argument(resolve_parser)
    _add_anchor_argument(resolve_parser)
    resolve_parser.set_defaults(handler=_cmd_resolve)

    query_parser = anchory_subparsers.add_parser("query", help="Query anchors.")
    _add_depot_argument(query_parser)
    query_parser.add_argument("--prefix", help="Only return anchors with this prefix.")
    query_parser.set_defaults(handler=_cmd_query)

    amend_parser = anchory_subparsers.add_parser("amend", help="Amend an existing anchor.")
    _add_depot_argument(amend_parser)
    _add_anchor_argument(amend_parser)
    _add_record_arguments(amend_parser)
    amend_parser.set_defaults(handler=_cmd_amend)

    check_parser = anchory_subparsers.add_parser("check", help="Check depot structure.")
    _add_depot_argument(check_parser)
    check_parser.set_defaults(handler=_cmd_check)

    scan_parser = anchory_subparsers.add_parser(
        "scan",
        help="Scan a source file for anchors and resolve them.",
    )
    _add_depot_argument(scan_parser)
    scan_parser.add_argument(
        "--src-file",
        required=True,
        help="Text file to scan for anchor candidates.",
    )
    scan_parser.add_argument(
        "--regex",
        required=True,
        help="Python regex used to extract anchors.",
    )
    scan_parser.add_argument(
        "--json",
        action="store_true",
        help="Print deterministic JSON instead of human-friendly output.",
    )
    scan_parser.set_defaults(handler=_cmd_scan)
