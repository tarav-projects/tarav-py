"""Selection-independent, named presentations of POIs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import json
import string
from typing import Literal

from .primitives import POI, POICollector

POILevel = Literal["line", "record"]
DEFAULT_POI_RENDERER = "Tarav.POI.Default.Renderer"
JSON_LINES_POI_RENDERER = "Tarav.POI.JsonLines.Renderer"


class POIRenderError(ValueError):
    """A renderer name, level or result is invalid."""


@dataclass(frozen=True, slots=True)
# tarav.breadcrumb ef2e7d65f93f
class POISelection:
    """An already selected page; renderers cannot filter or page it."""

    source: str
    items: tuple[Mapping[str, object], ...]
    total: int
    matching: int
    next_offset: int | None = None
    title: str = "POIs"
    summary: Mapping[str, object] | None = None
    matching_pois: int | None = None
    filters: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    # tarav.breadcrumb c99138a07b28
    def from_check_report(cls, report: Mapping[str, object]) -> POISelection:
        summary = report["summary"]
        if not isinstance(summary, Mapping):
            raise TypeError("Check report summary must be a mapping")
        return cls(
            "check", tuple(report["items"]), int(summary["pois"]),
            int(report["matching"]), report.get("next_offset"), "Check POIs", summary,
            matching_pois=int(report["matching_pois"]),
            filters=report.get("filters") or {},
        )

    @classmethod
    def from_collector_report(
        cls, report: Mapping[str, object], *, title: str = "POIs",
    ) -> POISelection:
        items = tuple(report.get("items") or ())
        return cls(
            "collector", items, int(report["total"]), int(report["matching"]),
            report.get("next_offset"), title,
        )

    @classmethod
    def from_pois(cls, pois: tuple[POI, ...] | list[POI], *, title: str = "POIs") -> POISelection:
        collector = POICollector()
        for poi in pois:
            collector.emit(poi)
        return cls.from_collector_report(collector.report(limit=max(1, len(pois))), title=title)


RenderHandler = Callable[[POISelection, POILevel], str]


@dataclass(frozen=True, slots=True)
class POIRenderer:
    name: str
    media_type: str
    levels: frozenset[POILevel]
    handler: RenderHandler

    def render(self, selection: POISelection, *, level: POILevel = "line") -> str:
        if level not in self.levels:
            raise POIRenderError(f"{self.name} does not support level {level}")
        content = self.handler(selection, level)
        if not isinstance(content, str):
            raise POIRenderError(f"{self.name} did not return text")
        return content


@dataclass(slots=True)
class POIRendererRegistry:
    _items: dict[str, POIRenderer] = field(default_factory=dict)

    def register(self, renderer: POIRenderer) -> None:
        if not renderer.name or renderer.name in self._items:
            raise POIRenderError(f"Invalid or duplicate POI renderer: {renderer.name}")
        self._items[renderer.name] = renderer

    def renderer(self, name: str) -> POIRenderer:
        try:
            return self._items[name]
        except KeyError as exc:
            raise POIRenderError(f"Unknown POI renderer: {name}") from exc

    def renderers(self) -> tuple[POIRenderer, ...]:
        return tuple(self._items.values())


def _address(row: Mapping[str, object]) -> str:
    value = row.get("id") or row.get("key") or row.get("type")
    if value is None:
        raise POIRenderError("POI row has no identifier or Type")
    address = str(value)
    if row.get("index") is not None:
        address += f":{row['index']}"
    return address


def _short_address(address: str) -> str:
    return address[:12] if len(address) == 64 and all(
        character in string.hexdigits for character in address
    ) else address


def check_header(summary: Mapping[str, object], *, pois: bool = True) -> list[str]:
    """What ran, in a line; then only what needs saying: checks that did not complete, suites left out."""
    ran, incomplete = summary["checks"], summary["incomplete"]
    lines = [f"{ran} checks ran, " + ("all completed" if not incomplete
                                      else f"{incomplete} did not complete")
             + (f". {summary['pois']} POIs." if pois else ".")]
    for name, data in (summary.get("by_check") or {}).items():
        unfinished = {status: count for status, count in data["by_status"].items()
                      if status != "completed"}
        if unfinished:
            lines.append(f"  did not complete: {name} (" + ", ".join(
                f"{count} {status}" for status, count in unfinished.items()) + ")")
    not_run = sorted({item.get("name") or item.get("type") or "?"
                      for item in summary.get("not_run") or ()})
    if not_run:
        lines.append(f"Not run: {', '.join(not_run)}. Run everything with --all.")
    return lines


def _text(selection: POISelection, level: POILevel) -> str:
    summary = selection.summary
    if selection.source == "check" and summary is not None:
        lines = check_header(summary)
    else:
        lines = [f"{selection.title}: {selection.total} POIs",
                 f"showing: {len(selection.items)} of {selection.matching} matching"]
    if selection.items:
        lines.append("")
    for row in selection.items:
        address = _address(row)
        if selection.source == "check":
            line = f"  {row['key']}: {row['pois']} POIs from {row['checks']} checks"
            if row.get("example"):
                line += f" — {row['example']}"
            if row.get("id"):
                line += f" [{str(row['id'])[:12]}]"
        else:
            line = (f"  {row['type']}  {_short_address(address)}"
                    f"  {row.get('message') or row.get('summary') or ''}")
        lines.append(line)
        if level == "record":
            detail = row.get("example_poi") if selection.source == "check" else row
            lines.append("    " + json.dumps(detail or row, ensure_ascii=False, default=str))
    if summary is not None and selection.source == "check":
        if selection.filters:
            criteria = ", ".join(f"{key}={value}" for key, value in selection.filters.items())
            lines.append(f"Showing {selection.matching_pois} of {selection.total} POIs matching {criteria}")
    if selection.next_offset is not None:
        lines.append(f"Next offset: {selection.next_offset}")
    return "\n".join(lines)


def _json_lines(selection: POISelection, level: POILevel) -> str:
    rows: list[dict[str, object]] = [{
        "kind": "poi-selection", "title": selection.title, "total": selection.total,
        "matching": selection.matching, "shown": len(selection.items),
        "next_offset": selection.next_offset, "level": level,
    }]
    if selection.source == "check":
        rows[0]["matching_pois"] = selection.matching_pois
        rows[0]["filters"] = dict(selection.filters)
    for item in selection.items:
        row: dict[str, object] = {"kind": "poi", "address": _address(item), **item}
        if level == "line":
            row["summary"] = item.get("message") or item.get("summary") or item.get("example")
            row = {key: row[key] for key in ("kind", "address", "id", "type", "summary")
                   if key in row}
        rows.append(row)
    return "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows)


_REGISTRY = POIRendererRegistry()
_REGISTRY.register(POIRenderer(DEFAULT_POI_RENDERER, "text/plain",
                               frozenset(("line", "record")), _text))
_REGISTRY.register(POIRenderer(JSON_LINES_POI_RENDERER, "application/x-ndjson",
                               frozenset(("line", "record")), _json_lines))


def renderer(name: str = DEFAULT_POI_RENDERER) -> POIRenderer:
    return _REGISTRY.renderer(name)


def register_renderer(value: POIRenderer) -> None:
    _REGISTRY.register(value)


def renderers() -> tuple[POIRenderer, ...]:
    return _REGISTRY.renderers()
