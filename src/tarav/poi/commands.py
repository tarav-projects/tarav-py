# $kw: --from POI.System
"""CLI adapter for shared POI discovery acts."""

from __future__ import annotations

import argparse
import json
from typing import Any, Protocol

from tarav._core.errors import CliError
from tarav.wayfinder import (
    Wayfinder,
    WayfinderError,
    WayfinderReference,
    WayfinderResolutionPOI,
    parse_reference,
)

from .catalog import POICatalog, POICatalogError
from .model import reference_sugar, tarav_poi_class_reference


class _RelatedResolver(Protocol):
    def resolve(
        self,
        reference: WayfinderReference,
        *,
        projection: str,
        max_depth: int,
    ) -> Any: ...


def _cmd_explain(
    args: argparse.Namespace,
    *,
    catalog: POICatalog | None,
    wayfinder: Wayfinder,
    related_resolver: _RelatedResolver | None,
) -> int:
    try:
        reference = _class_reference(args.class_name, catalog)
        result = wayfinder.resolve(reference)
    except (POICatalogError, WayfinderError) as exc:
        raise CliError(str(exc)) from exc

    related = None
    if not isinstance(result, WayfinderResolutionPOI) and args.related is not None:
        if related_resolver is None:
            raise CliError("related-surface resolution is not configured")
        related = related_resolver.resolve(
            reference,
            projection=args.related,
            max_depth=args.max_depth,
        )

    if args.json:
        payload = result.as_dict()
        if related is not None:
            payload["related"] = related.as_dict()
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif isinstance(result, WayfinderResolutionPOI):
        print(f"POI class unresolved: {reference_sugar(reference)}")
        print(result.message)
    else:
        target = result.target
        print(f"POI class: {reference_sugar(reference)}")
        print(f"Source: {target['path']}:{target['start_line']}-{target['end_line']}")
        print()
        print(target["content"])
        if related is not None:
            for node in related.nodes[1:]:
                print()
                print(f"Related: {reference_sugar(node.reference)}")
                print(node.target.get("content", ""))
            for diagnostic in related.diagnostics:
                print()
                print(
                    f"Related unresolved: {reference_sugar(diagnostic.reference)} "
                    f"- {diagnostic.message}"
                )
    return 1 if isinstance(result, WayfinderResolutionPOI) else 0


def _class_reference(
    value: str,
    catalog: POICatalog | None,
) -> WayfinderReference:
    registered = catalog.get(value) if catalog is not None else None
    if registered is not None:
        return registered
    if "://" in value or value.lstrip().startswith("{"):
        return parse_reference(value)
    return tarav_poi_class_reference(value)


def register_poi_commands(
    subparsers: argparse._SubParsersAction,
    *,
    catalog: POICatalog | None = None,
    wayfinder: Wayfinder,
    related_resolver: _RelatedResolver | None = None,
) -> None:
    parser = subparsers.add_parser(
        "poi",
        help="Resolve and inspect shared POI classes.",
    )
    commands = parser.add_subparsers(dest="poi_command", required=True)
    explain = commands.add_parser(
        "explain",
        help="Resolve and present a POI class documentation block.",
    )
    explain.add_argument(
        "--class",
        dest="class_name",
        required=True,
        help="Finding code, managed reference, or canonical reference JSON.",
    )
    explain.add_argument(
        "--related",
        choices=("direct", "reachable"),
        help="Also resolve explicit directly related or bounded reachable surfaces.",
    )
    explain.add_argument(
        "--max-depth",
        type=int,
        default=8,
        help="Maximum traversal depth with --related reachable (default: 8).",
    )
    explain.add_argument(
        "--json",
        action="store_true",
        help="Emit the complete structured Wayfinder resolution.",
    )
    explain.set_defaults(
        handler=lambda args: _cmd_explain(
            args,
            catalog=catalog,
            wayfinder=wayfinder,
            related_resolver=related_resolver,
        )
    )


__all__ = ["register_poi_commands"]
