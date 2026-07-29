"""CLI adapter for shared POI discovery acts."""

from __future__ import annotations

import argparse
import json

from agentos._core.errors import CliError
from agentos.wayfinder import (
    Wayfinder,
    WayfinderError,
    WayfinderReference,
    WayfinderResolutionPOI,
    parse_reference,
)

from .catalog import POICatalog, POICatalogError
from .model import reference_sugar


def _cmd_explain(args: argparse.Namespace) -> int:
    configured_catalog: POICatalog | None = args._poi_catalog
    try:
        catalog = (
            configured_catalog
            if configured_catalog is not None
            else POICatalog.discover()
        )
        reference = _class_reference(args.class_name, catalog)
        result = Wayfinder().resolve(reference)
    except (POICatalogError, WayfinderError) as exc:
        raise CliError(str(exc)) from exc

    if args.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    elif isinstance(result, WayfinderResolutionPOI):
        print(f"POI class unresolved: {reference_sugar(reference)}")
        print(result.message)
    else:
        target = result.target
        print(f"POI class: {reference_sugar(reference)}")
        print(f"Source: {target['path']}:{target['start_line']}-{target['end_line']}")
        print()
        print(target["content"])
    return 1 if isinstance(result, WayfinderResolutionPOI) else 0


def _class_reference(value: str, catalog: POICatalog) -> WayfinderReference:
    registered = catalog.get(value)
    if registered is not None:
        return registered
    return parse_reference(value)


def register_poi_commands(
    subparsers: argparse._SubParsersAction,
    *,
    catalog: POICatalog | None = None,
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
        "class_name",
        help="Registered finding code, index:// reference, or canonical reference JSON.",
    )
    explain.add_argument(
        "--json",
        action="store_true",
        help="Emit the complete structured Wayfinder resolution.",
    )
    explain.set_defaults(handler=_cmd_explain, _poi_catalog=catalog)


__all__ = ["register_poi_commands"]
