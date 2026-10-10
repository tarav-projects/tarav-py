"""Selection-independent, named presentations of POIs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import json
import string
from typing import Literal

from .primitives import POI, POICollector
from .reporting import REPORTED_POI_VIEW, context_instruction

POILevel = Literal["line", "record", "context"]
DEFAULT_POI_RENDERER = "Tarav.POI.Default.Renderer"
JSON_LINES_POI_RENDERER = "Tarav.POI.JsonLines.Renderer"


class POIRenderError(ValueError):
    """A renderer name, level or result is invalid."""


@dataclass(frozen=True, slots=True)
# tarav.breadcrumb ef2e7d65f93f837cebcf2f4ff40ef8b4c95a742675cf2a3e309ad7bb6204c519
class POISelection:
    """An already selected page; renderers cannot filter or page it."""

    source: str
    items: tuple[Mapping[str, object], ...]
    total: int
    matching: int
    next_offset: int | None = None
    example_id: str | None = None
    title: str = "POIs"
    summary: Mapping[str, object] | None = None
    context_view: str = REPORTED_POI_VIEW
    matching_pois: int | None = None
    filters: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    # tarav.breadcrumb c99138a07b283e9b2a371bd4e3b7f82c5c3d0f277b0ac73d16e3003ca37b1c70
    def from_check_report(cls, report: Mapping[str, object]) -> POISelection:
        summary = report["summary"]
        if not isinstance(summary, Mapping):
            raise TypeError("Check report summary must be a mapping")
        return cls(
            "check", tuple(report["items"]), int(summary["pois"]),
            int(report["matching"]), report.get("next_offset"),
            report.get("context_example"), "Check POIs", summary,
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
            report.get("next_offset"),
            next((str(row["id"]) for row in items if row.get("id")), None), title,
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


def _text(selection: POISelection, level: POILevel) -> str:
    summary = selection.summary
    if selection.source == "check" and summary is not None:
        lines = [f"{summary['checks']} checks, {summary['incomplete']} incomplete, "
                 f"{summary['pois']} POIs"]
    else:
        lines = [f"{selection.title}: {selection.total} POIs",
                 f"showing: {len(selection.items)} of {selection.matching} matching"]
    if selection.total:
        lines.extend(("", *context_instruction(selection.example_id,
                                               view=selection.context_view), ""))
    for row in selection.items:
        address = _address(row)
        if selection.source == "check":
            line = (f"  {row['key']}: {row['pois']} POIs from {row['checks']} checks "
                    f"({row['open']} open, {row['blessed']} blessed"
                    + (f", {row['dismissed']} dismissed" if row.get("dismissed") else "") + ")")
            if row.get("example"):
                line += f" — {row['example']}"
            if row.get("id"):
                line += f" [{str(row['id'])[:12]}]"
        else:
            standing = (" ".join(f"{key}={value}" for key, value in row["axes"].items())
                        if row.get("axes")
                        else (row.get("blessing") or {}).get("status", "unblessed"))
            line = (f"  {row['type']}  {_short_address(address)}  {standing}"
                    f"  {row.get('message') or row.get('summary') or ''}")
        lines.append(line)
        if level == "record":
            detail = row.get("example_poi") if selection.source == "check" else row
            lines.append("    " + json.dumps(detail or row, ensure_ascii=False, default=str))
        elif level == "context":
            identifier = row.get("id") or selection.example_id
            if identifier:
                lines.append(f"    tarav context --id {identifier} --view {selection.context_view}")
    if summary is not None and selection.source == "check":
        if selection.filters:
            criteria = ", ".join(f"{key}={value}" for key, value in selection.filters.items())
            lines.append(f"Showing {selection.matching_pois} of {selection.total} POIs matching {criteria}")
        else:
            by_check = summary.get("by_check") or {}
            by_type = summary.get("by_type") or {}
            lines.append("Checks by type: " + (", ".join(
                f"{name} {data['runs']} ({data['by_status']})"
                for name, data in by_check.items()) or "none"))
            lines.append("POIs by type: " + (", ".join(
                f"{name} {count}" for name, count in by_type.items()) or "none"))
    if selection.next_offset is not None:
        lines.append(f"Next offset: {selection.next_offset}")
    return "\n".join(lines)


def _json_lines(selection: POISelection, level: POILevel) -> str:
    rows: list[dict[str, object]] = [{
        "kind": "poi-selection", "title": selection.title, "total": selection.total,
        "matching": selection.matching, "shown": len(selection.items),
        "next_offset": selection.next_offset, "level": level,
        "context_instruction": (context_instruction(selection.example_id,
                                                    view=selection.context_view)
                                if selection.total else []),
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
        elif level == "context":
            identifier = item.get("id") or selection.example_id
            row = {"kind": "poi", "address": _address(item),
                   "context_command": (f"tarav context --id {identifier} "
                                       f"--view {selection.context_view}"
                                       if identifier else None)}
        rows.append(row)
    return "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows)


_REGISTRY = POIRendererRegistry()
_REGISTRY.register(POIRenderer(DEFAULT_POI_RENDERER, "text/plain",
                               frozenset(("line", "record", "context")), _text))
_REGISTRY.register(POIRenderer(JSON_LINES_POI_RENDERER, "application/x-ndjson",
                               frozenset(("line", "record", "context")), _json_lines))


def renderer(name: str = DEFAULT_POI_RENDERER) -> POIRenderer:
    return _REGISTRY.renderer(name)


def register_renderer(value: POIRenderer) -> None:
    _REGISTRY.register(value)


def renderers() -> tuple[POIRenderer, ...]:
    return _REGISTRY.renderers()
