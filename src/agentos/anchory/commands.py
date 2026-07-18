from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.json_input import load_json_object_arg

from .core import AnchoryDepot, AnchoryEntry, AnchoryError, AnchoryResolution
from .core import GLOBAL_NAMESPACE, AnchorySourceMatch, scan_anchory_source
from .registry import discover_resolve


@dataclass(frozen=True)
class _ResolvedScanMatch:
    source: AnchorySourceMatch
    resolution: AnchoryResolution | None


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
        entry = depot.register(
            _record_arg(args),
            anchor=args.anchor,
            alloc_prefix=args.alloc_prefix,
            tag=args.tag,
            namespace=args.namespace,
        )
    except AnchoryError as exc:
        raise CliError(str(exc)) from exc
    _print_json(_entry_payload(depot, entry))
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    if args.depot is not None:
        depot = _depot(args)
        try:
            resolution = depot.resolve(args.anchor, namespace=args.namespace)
        except AnchoryError as exc:
            raise CliError(str(exc)) from exc
        depot_root = depot.root
    else:
        try:
            hit = discover_resolve(args.anchor)
        except AnchoryError as exc:
            raise CliError(str(exc)) from exc
        if hit is None:
            raise CliError(
                f"anchor does not exist in any registered or global depot: {args.anchor}"
            )
        resolution, depot_root = hit
    if resolution is None:
        raise CliError(f"anchor does not exist: {args.anchor}")
    payload: dict[str, object] = {
        "depot": str(depot_root),
        "anchor": resolution.anchor,
        "namespace": resolution.namespace,
        "record": resolution.record,
    }
    if resolution.tag_mismatch:
        payload["tag_mismatch"] = True
        payload["cited_as"] = args.anchor
    if args.meta:
        meta_depot = AnchoryDepot(depot_root)
        payload["meta"] = meta_depot.namespace_meta(resolution.namespace)
    _print_json(payload)
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    depot = _depot(args)
    try:
        entries = depot.query(namespace=args.namespace, prefix=args.prefix)
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
        entry = depot.amend(args.anchor, _record_arg(args), namespace=args.namespace)
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
                    "severity": finding.severity,
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


def _resolve_scan_matches(
    depot: AnchoryDepot, matches: tuple[AnchorySourceMatch, ...]
) -> tuple[_ResolvedScanMatch, ...]:
    return tuple(
        _ResolvedScanMatch(source=match, resolution=depot.resolve(match.anchor))
        for match in matches
    )


def _scan_match_payload(match: _ResolvedScanMatch) -> dict[str, object]:
    payload: dict[str, object] = {
        "anchor": match.source.anchor,
        "line": match.source.line,
        "column": match.source.column,
        "start": match.source.start,
        "end": match.source.end,
        "record": match.resolution.record if match.resolution is not None else None,
    }
    if match.resolution is not None and match.resolution.tag_mismatch:
        payload["tag_mismatch"] = True
        payload["resolved_anchor"] = match.resolution.anchor
    return payload


def _scan_payload(
    *,
    depot: AnchoryDepot,
    src_file: Path,
    regex: str,
    matches: tuple[_ResolvedScanMatch, ...],
) -> dict[str, object]:
    return {
        "depot": str(depot.root),
        "src_file": str(src_file),
        "regex": regex,
        "count": len(matches),
        "matches": [_scan_match_payload(match) for match in matches],
    }


def _print_scan_human(
    *,
    depot: AnchoryDepot,
    src_file: Path,
    regex: str,
    matches: tuple[_ResolvedScanMatch, ...],
) -> None:
    print("Anchory scan")
    print(f"depot: {depot.root}")
    print(f"source: {src_file}")
    print(f"regex: {regex}")
    print(f"{len(matches)} match(es)")
    for match in matches:
        print(
            f"- {match.source.anchor} @ line {match.source.line}, "
            f"column {match.source.column}"
        )
        if match.resolution is None:
            print("  record: missing")
        else:
            if match.resolution.tag_mismatch:
                print(f"  tag-mismatch: stored key is {match.resolution.anchor}")
            print(f"  record: {json.dumps(match.resolution.record, sort_keys=True)}")


def _cmd_scan(args: argparse.Namespace) -> int:
    depot = _depot(args)
    src_file = Path(args.src_file).expanduser().resolve()
    try:
        text = src_file.read_text(encoding="utf-8")
        matches = _resolve_scan_matches(depot, scan_anchory_source(text, args.regex))
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
        _print_scan_human(
            depot=depot,
            src_file=src_file,
            regex=args.regex,
            matches=matches,
        )
    return 0


def _cmd_namespace_get(args: argparse.Namespace) -> int:
    depot = _depot(args)
    try:
        meta = depot.namespace_meta(args.namespace)
    except AnchoryError as exc:
        raise CliError(str(exc)) from exc
    if meta is None:
        raise CliError(f"namespace has no meta.json: {args.namespace}")
    _print_json({"depot": str(depot.root), "namespace": args.namespace, "meta": meta})
    return 0


def _cmd_namespace_set(args: argparse.Namespace) -> int:
    depot = _depot(args)
    try:
        meta = depot.write_namespace_meta(
            args.namespace,
            prefix=args.prefix,
            intention=args.intention,
            semantics=args.semantics,
        )
    except AnchoryError as exc:
        raise CliError(str(exc)) from exc
    _print_json({"depot": str(depot.root), "namespace": args.namespace, "meta": meta})
    return 0


def _add_depot_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--depot",
        required=True,
        help="Exact Anchory depot root.",
    )


def _add_anchor_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--anchor", required=True, help="Anchor key.")


def _add_register_identity_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--anchor", help="Exact anchor key.")
    group.add_argument(
        "--alloc-prefix",
        help=(
            "Caller allocation prefix (e.g. a YYYYMMDD date); anchory composes "
            "<ns-prefix><alloc-prefix>-<counter><tag?> and allocates the counter."
        ),
    )


def _add_namespace_argument(
    parser: argparse.ArgumentParser, *, default: str | None = None
) -> None:
    parser.add_argument(
        "--namespace",
        default=default,
        help="Namespace inside the depot (directory of shards with its meta.json).",
    )


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

    register_parser = anchory_subparsers.add_parser(
        "register",
        help="Register an exact anchor or atomically allocate one from a prefix.",
    )
    _add_depot_argument(register_parser)
    _add_namespace_argument(register_parser, default=GLOBAL_NAMESPACE)
    _add_register_identity_arguments(register_parser)
    register_parser.add_argument(
        "--tag",
        help="Optional single-letter key decoration appended after the counter.",
    )
    _add_record_arguments(register_parser)
    register_parser.set_defaults(handler=_cmd_register)

    resolve_parser = anchory_subparsers.add_parser(
        "resolve",
        help="Resolve an anchor; without --depot, discover via the registry.",
    )
    resolve_parser.add_argument(
        "--depot",
        help="Exact Anchory depot root; omit to search registered depots and the global depot.",
    )
    _add_namespace_argument(resolve_parser)
    _add_anchor_argument(resolve_parser)
    resolve_parser.add_argument(
        "--meta",
        action="store_true",
        help="Include the resolved namespace's meta.json in the output.",
    )
    resolve_parser.set_defaults(handler=_cmd_resolve)

    query_parser = anchory_subparsers.add_parser("query", help="Query anchors.")
    _add_depot_argument(query_parser)
    _add_namespace_argument(query_parser)
    query_parser.add_argument("--prefix", help="Only return anchors with this prefix.")
    query_parser.set_defaults(handler=_cmd_query)

    amend_parser = anchory_subparsers.add_parser("amend", help="Amend an existing anchor.")
    _add_depot_argument(amend_parser)
    _add_namespace_argument(amend_parser)
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

    namespace_parser = anchory_subparsers.add_parser(
        "namespace",
        help="Read or write a namespace's meta.json.",
    )
    namespace_subparsers = namespace_parser.add_subparsers(
        dest="anchory_namespace_command",
        required=True,
    )
    ns_get_parser = namespace_subparsers.add_parser(
        "get", help="Print a namespace's meta.json."
    )
    _add_depot_argument(ns_get_parser)
    ns_get_parser.add_argument("--namespace", required=True)
    ns_get_parser.set_defaults(handler=_cmd_namespace_get)
    ns_set_parser = namespace_subparsers.add_parser(
        "set", help="Write a namespace's meta.json."
    )
    _add_depot_argument(ns_set_parser)
    ns_set_parser.add_argument("--namespace", required=True)
    ns_set_parser.add_argument(
        "--prefix", required=True, help="Single-letter namespace key prefix."
    )
    ns_set_parser.add_argument(
        "--intention", help="What this namespace's anchors mean — the resolution fallback."
    )
    ns_set_parser.add_argument(
        "--semantics", help="Pointer to the owning system's documentation."
    )
    ns_set_parser.set_defaults(handler=_cmd_namespace_set)
