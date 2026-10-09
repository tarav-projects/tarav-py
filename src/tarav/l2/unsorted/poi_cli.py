"""Shared Diagram command presentation of typed POIs."""

from __future__ import annotations

# tarav.breadcrumb 14c09da82eb7c5ae0ab508ebc6c5f80a37274fefc7e6909ca90f0ae05106e840

import argparse
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l1.poi import (
    DEFAULT_POI_RENDERER,
    POI,
    POIRenderError,
    POISelection,
    renderer,
)
from tarav.l1.poi.reporting import retain_presented_pois


def add_poi_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--renderer", dest="poi_renderer", default=DEFAULT_POI_RENDERER,
        help="Registered POI renderer name.",
    )
    parser.add_argument(
        "--level", choices=("line", "record", "context"), default="line",
        help="Detail level of the POI presentation.",
    )


def render_pois(
    args: argparse.Namespace,
    pois: tuple[POI, ...] | list[POI],
    *,
    title: str,
    root: Path,
) -> str:
    if not pois:
        return ""
    selection = POISelection.from_pois(pois, title=title)
    try:
        selected = renderer(getattr(args, "poi_renderer", DEFAULT_POI_RENDERER))
        level = getattr(args, "level", "line")
        if level not in selected.levels:
            raise POIRenderError(f"{selected.name} does not support level {level}")
        retain_presented_pois(pois, kind="diagram", name=title, root=root)
        return selected.render(selection, level=level)
    except (POIRenderError, ValueError) as exc:
        raise CliError(str(exc)) from exc
