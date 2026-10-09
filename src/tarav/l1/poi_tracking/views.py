"""Reading track records: a named POI renderer, a Context view and its resolver."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator, Mapping
from copy import deepcopy
from pathlib import Path

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.context import ContextBuilder, ContextFolder
from tarav.l1.context.query import ContextCandidate, IdentityContextQuery
from tarav.l1.poi import POIDetails
from tarav.l1.poi.rendering import (
    POILevel, POIRenderer, POISelection, register_renderer,
)
from tarav.l1.poi.reporting import REPORTED_POI_VIEW, ReportedPOIStore, context_instruction
from tarav.l1.search import SearchEngine, SearchHit, SearchQuery

from . import (
    POI_TRACKING_WORKFLOW_SHIP, TRACKED_POI_VIEW, TrackRecord, TrackRecordStore, status_vector,
)

TRACKING_POI_RENDERER = "Tarav.POI.Tracking.Renderer"
PROJECT_STORE_PATH = Path(".tarav") / "poi-tracking"


def tracking_selection(report: Mapping[str, object]) -> POISelection:
    """A tracker report as an already selected page for any named renderer."""
    items = tuple(report["items"])
    return POISelection(
        "tracking", items, int(report["total"]), int(report["matching"]),
        report.get("next_offset"), next((str(row["id"]) for row in items), None),
        "Tracked POIs", {"by_axis": report.get("by_axis") or {}}, TRACKED_POI_VIEW,
    )


# tarav.breadcrumb 2179a3248b0cabbbf74edc7d0dcd0c7c86d75f62884877f4690e48d0d9e20a37
def _tracking_text(selection: POISelection, level: POILevel) -> str:
    """One line per POI with its whole status vector; no axis is singled out."""
    lines = [f"{selection.title}: {selection.total} POIs, showing {len(selection.items)} "
             f"of {selection.matching} matching"]
    for key, values in ((selection.summary or {}).get("by_axis") or {}).items():
        lines.append(f"  {key}: " + ", ".join(f"{value} {count}" for value, count in values.items()))
    if selection.total:
        lines.extend(("", *context_instruction(selection.example_id,
                                               view=selection.context_view), ""))
    for row in selection.items:
        identifier = str(row.get("id") or row.get("key") or row.get("type"))
        vector = " ".join(f"{key}={value}" for key, value in (row.get("axes") or {}).items())
        text = row.get("message") or row.get("example") or ""
        lines.append("  " + "  ".join(part for part in (
            str(row.get("type") or row.get("key")), f"[{identifier[:12]}]", vector, str(text),
        ) if part))
        if level == "record":
            lines.append("    " + json.dumps(row.get("record") or row, ensure_ascii=False,
                                             default=str))
        elif level == "context" and (row.get("id") or selection.example_id):
            lines.append(f"    tarav context --id {row.get('id') or selection.example_id} "
                         f"--view {selection.context_view}")
    if selection.next_offset is not None:
        lines.append(f"Next offset: {selection.next_offset}")
    return "\n".join(lines)


register_renderer(POIRenderer(TRACKING_POI_RENDERER, "text/plain",
                              frozenset(("line", "record", "context")), _tracking_text))


def _value(content: object) -> POIDetails:
    return POIDetails.records.from_record(
        {"type": entity(POIDetails).name, "value": deepcopy(content)})


class TrackedPOIContext(ContextFolder):
    """What a Project has recorded about one POI across check runs."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("14c5781e-1436-47c1-b8a5-8091ecb2cc7b"),
                          name="Tarav.POI.Tracking.Context",
                          workflow=POI_TRACKING_WORKFLOW_SHIP)

    @classmethod
    def for_subject(cls, subject):
        if not isinstance(subject, TrackRecord):
            raise TypeError(f"{TRACKED_POI_VIEW} supports only track records")
        record = subject.record

        def populate(builder: ContextBuilder) -> None:
            builder.add("status", opener=lambda: _value(status_vector(record)),
                        description="The current value of every axis. Read all of them: "
                                    "no single axis is the status.")
            builder.add("poi", opener=lambda: _value(record["poi"]),
                        description="The POI as it was last raised.")
            builder.add("check", opener=lambda: _value(record["check"]),
                        description="The owning check and its identity across runs; without "
                                    "an identity the POI can never read as passed.")
            builder.add("axes", opener=lambda: _value(record["axes"]),
                        description="Every axis: owner workflow, value, since when, and "
                                    "each change with what made it.")
            builder.add("reported", opener=lambda: _value(
                [f"tarav context --id {record['poi_id']} --view {REPORTED_POI_VIEW}",
                 "Opens the POI as last reported on this machine, with what its Type "
                 "asks you to read and what you may do. Absent when it was not in the "
                 "last report."]),
                description="The command that opens the reported POI and its guidance.")

        return cls(subject, populate)


def known_store_roots() -> list[Path]:
    """Tracking stores reachable from here: enclosing Projects and Projects checked before."""
    roots: list[Path] = []
    for folder in (Path.cwd(), *Path.cwd().parents):
        roots.append(folder / PROJECT_STORE_PATH)
    for report in ReportedPOIStore().reports():
        root = (report.get("project") or {}).get("root")
        if root:
            roots.append(Path(str(root)) / PROJECT_STORE_PATH)
    return list(dict.fromkeys(root for root in roots if root.is_dir()))


class TrackRecordResolver(SearchEngine):
    """Find a track record by POI identity, for queries that ask for the tracked view.

    Answering only that view keeps the general Context of a POI identifier
    unambiguous: the reported POI stays its single subject.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7aa22196-7e69-483f-8a63-cdc6fc125f37"),
                          name="Tarav.POI.Tracking.Resolver",
                          workflow=POI_TRACKING_WORKFLOW_SHIP)

    def __init__(self, roots: Callable[[], Iterable[Path]] = known_store_roots) -> None:
        self._roots = roots

    class Search(SearchEngine.Search):
        def accepts(self, query: SearchQuery) -> bool:
            return (isinstance(query, IdentityContextQuery)
                    and query.view == TRACKED_POI_VIEW
                    and len(query.identifier) >= 2
                    and all(char in "0123456789abcdef" for char in query.identifier))

        def _iter_hits(self, query: IdentityContextQuery) -> Iterator[SearchHit]:
            for root in self.obj._roots():
                for record in TrackRecordStore(root).find(query.identifier):
                    yield SearchHit(ContextCandidate(
                        TrackRecord.records.from_record(record), record["poi_id"],
                        f"{record['poi'].get('message')} [{record['poi'].get('type')}]"))


__all__ = [
    "PROJECT_STORE_PATH",
    "TRACKING_POI_RENDERER",
    "TrackRecordResolver",
    "TrackedPOIContext",
    "known_store_roots",
    "tracking_selection",
]
