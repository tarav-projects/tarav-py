"""POI tracking CLI: read a Project's track records, filtered by axis values."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l1.poi.rendering import renderer, renderers
from tarav.l1.poi_tracking import TrackingError
from tarav.l1.poi_tracking.views import TRACKING_POI_RENDERER, tracking_selection


def project_root(start: Path) -> Path:
    """The nearest folder at or above `start` that holds a Project marker."""
    origin = Path(start).expanduser().resolve()
    for folder in (origin, *origin.parents):
        if (folder / ".tarav" / "project.json").is_file():
            return folder
    raise CliError(f"No Tarav Project at or above {origin}")


def _axes(values: list[str]) -> dict[str, str]:
    selected = {}
    for item in values:
        key, separator, value = item.partition("=")
        if not separator or not key or not value:
            raise CliError("--axis must use KEY=VALUE")
        selected[key] = value
    return selected


def _list(args: argparse.Namespace) -> int:
    if args.project is None:
        raise CliError("tarav poi tracking list needs --project [PATH]")
    from tarav.l2.project.tracking import open_tracker

    tracker = open_tracker(project_root(args.project))
    try:
        report = tracker.report(axes=_axes(args.axis), poi_type=args.poi_type,
                                check=args.check_type, offset=args.offset, limit=args.limit)
    except (TrackingError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(renderer(args.renderer).render(tracking_selection(report), level=args.level))
    return 0


def register_poi_command(subparsers: argparse._SubParsersAction) -> None:
    poi = subparsers.add_parser("poi", help="Work with points of interest across runs.")
    tracking = poi.add_subparsers(dest="poi_command").add_parser(
        "tracking", help="The Project's durable record of tracked POIs.")
    parser = tracking.add_subparsers(dest="tracking_command").add_parser(
        "list",
        help="List track records; every axis of each record's status is shown.",
        epilog=(
            "examples:\n"
            "  tarav poi tracking list --project\n"
            "  tarav poi tracking list --project --axis observation=passed\n"
            "  tarav poi tracking list --project --axis observation=active "
            "--axis blessing=unblessed\n\n"
            "`tarav check --project` writes the records in the Project's\n"
            ".tarav/poi-tracking/. A status is a set of axes, never one value;\n"
            "repeat --axis to require several. Open one record with\n"
            "`tarav context --id <poi-id> --view tracked-poi`."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--project", type=Path, nargs="?", const=Path("."),
                        help="Search this directory and parents for a Project; "
                             "optionally start at PATH.")
    parser.add_argument("--axis", action="append", default=[], metavar="KEY=VALUE",
                        help="Keep records whose axis KEY has VALUE; repeatable.")
    parser.add_argument("--type", dest="poi_type", help="Filter by exact POI Type name.")
    parser.add_argument("--check", dest="check_type", help="Filter by exact Check Type name.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum records to show.")
    parser.add_argument("--offset", type=int, default=0, help="First record to show.")
    parser.add_argument("--renderer", choices=tuple(item.name for item in renderers()),
                        default=TRACKING_POI_RENDERER, help="Named POI renderer.")
    parser.add_argument("--level", choices=("line", "record", "context"), default="line",
                        help="POI detail level for rendered output.")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    parser.set_defaults(handler=_list)


__all__ = ["project_root", "register_poi_command"]
