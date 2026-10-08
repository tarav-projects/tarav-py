"""CLI-only presentation helpers for structured SKW results."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any

from tarav.l1.poi.rendering import (
    DEFAULT_POI_RENDERER, JSON_LINES_POI_RENDERER, POISelection, renderer,
)


def add_output_mode(parser: argparse.ArgumentParser) -> None:
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--rendered",
        dest="output_mode",
        action="store_const",
        const="rendered",
        help="Print a concise human-readable view (default).",
    )
    modes.add_argument(
        "--json",
        dest="output_mode",
        action="store_const",
        const="json",
        help="Print the complete structured result as JSON.",
    )
    parser.set_defaults(output_mode="rendered")


def emit(
    args: argparse.Namespace,
    result: Any,
    renderer: Callable[[Any], str],
) -> None:
    if args.output_mode == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    rendered = renderer(result)
    print(rendered, end="" if rendered.endswith("\n") else "\n")


def emit_error(args: argparse.Namespace, message: str) -> None:
    if args.output_mode == "json":
        print(json.dumps({"error": message}, ensure_ascii=False))
    else:
        print(f"error: {message}", file=sys.stderr)


def _details(value: dict[str, Any], *, skip: tuple[str, ...] = ()) -> str:
    return "  ".join(
        f"{key}={json.dumps(item, ensure_ascii=False)}"
        for key, item in value.items()
        if key not in skip and item not in (None, "", [], {})
    )


def render_document_findings(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "No findings."
    rows = [f"Findings: {len(findings)}"]
    for finding in findings:
        detail = _details(finding, skip=("kind",))
        rows.append(f"  {finding.get('kind', 'unknown')}" + (f"  {detail}" if detail else ""))
    return "\n".join(rows)


def render_document_result(command: str, result: Any) -> str:
    if command == "lint":
        return render_document_findings(result)
    if command == "compile":
        status = "written" if result["written"] else "not written"
        return f"Product: {status}\n{render_document_findings(result['findings'])}"
    if command == "prepare":
        rows = [
            f"Generation prepared: {result['id']}",
            f"source: {result['source']}",
            f"block: {result['block']}",
            f"context: {len(result.get('context') or [])} entries",
        ]
        if result.get("chat"):
            rows.append(f"chat: {result['chat']}")
        rows.extend(("", "Instructions:", "\n".join(result["instructions"])))
        return "\n".join(rows)
    if command == "record":
        return "\n".join((
            f"Generation recorded: {result['id']}",
            f"source: {result['source']}",
            f"block: {result['block']}",
            f"output hash: {result['output_hash']}",
        ))
    if command == "produce":
        return f"Produced {result['block']}:\n" + "\n".join(result['content'])
    if command == "observe-context":
        return "\n".join((
            f"Context observed: {result['block']}",
            f"context hash: {result['context_hash']}",
        ))
    raise ValueError(f"No document renderer for {command}")


def render_document_context(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "No context entries."
    rows = []
    for entry in entries:
        index = entry.get("index", "?")
        kind = entry.get("type") or "unknown"
        status = entry.get("status") or "unknown"
        target = entry.get("path")
        row = f"[{index}] {kind}  {status}"
        if target:
            row += f"  {target}"
        if entry.get("object_index"):
            row += f"  index: {entry['object_index']}"
        rows.append(row)
        if entry.get("finding"):
            rows.append(f"    {entry['finding']}")
    return "\n".join(rows)


def render_skill_listing(result: dict[str, Any]) -> str:
    rows = []
    for item in result["items"]:
        if "source" in item:
            rows.append(f"{item['source']}  {item['path']}")
        else:
            rows.append(f"{item['block']}  {item['type']}")
    if not rows:
        rows.append("No items.")
    shown = len(result["items"])
    rows.append(f"\nShowing {shown} of {result['total']}.")
    if result.get("next_offset") is not None:
        rows.append(f"Next offset: {result['next_offset']}")
    return "\n".join(rows)


def render_skill_block(result: dict[str, Any]) -> str:
    block = result["block"]
    record_type = block.get('type', '<unknown>')
    if isinstance(record_type, dict):
        record_type = record_type.get('label', record_type.get('uuid', '<unknown>'))
    rows = [
        f"{block['label']}  {record_type}",
        f"id: {block['id']}",
        f"source: {result['source']}",
        f"output: {result['output']}",
    ]
    annotations = block.get("annotations") or []
    if annotations:
        rows.append(f"annotations: {len(annotations)}")
    content = block.get("content")
    if isinstance(content, list):
        rows.extend(("", "\n".join(str(line) for line in content)))
    elif content is None:
        rows.append("content status: not recorded")
    return "\n".join(rows)


def render_loading_context(result: dict[str, Any]) -> str:
    parents = result.get("parents") or []
    paths = result.get("paths") or []
    diagnostics = result.get("diagnostics") or []
    rows = [
        f"block: {result['block']}",
        f"parents: {', '.join(parents) if parents else 'none'}",
        f"paths: {len(paths)} shown of {result['path_count']}",
    ]
    for state in paths:
        path = " -> ".join(state.get("path") or []) or "(empty)"
        rows.append(f"  {path}")
        inlined = state.get("inlined") or []
        referenced = state.get("referenced") or []
        if inlined:
            rows.append(f"    inlined: {', '.join(inlined)}")
        if referenced:
            rows.append(f"    referenced: {', '.join(referenced)}")
    rows.append(f"diagnostics: {len(diagnostics)}")
    for diagnostic in diagnostics:
        details = [
            f"{key}={value}"
            for key, value in diagnostic.items()
            if key != "code"
        ]
        suffix = f"  {'  '.join(details)}" if details else ""
        rows.append(f"  {diagnostic.get('code', 'unknown')}{suffix}")
    return "\n".join(rows)


# tarav.breadcrumb cbdad46c901e98a6e0cd55696e3cebc0712f8b25281094227a47d13f5c9ae1c7
def render_poi_report(result: dict[str, Any], *, operation: str,
                      renderer_name: str = DEFAULT_POI_RENDERER,
                      level: str = "line") -> str:
    selection = POISelection.from_collector_report(result, title=operation)
    rendered = renderer(renderer_name).render(selection, level=level)
    store_observations = result.get("store_findings") or []
    if store_observations and renderer_name == DEFAULT_POI_RENDERER:
        rendered += f"\nblessing-store observations: {len(store_observations)}"
    return rendered


def render_skill_operation(operation: str, result: dict[str, Any], *,
                           renderer_name: str = DEFAULT_POI_RENDERER,
                           level: str = "line") -> str:
    if operation in {"check", "build"}:
        return render_poi_report(result, operation=operation,
                                 renderer_name=renderer_name, level=level)
    if operation == "deploy":
        if renderer_name == JSON_LINES_POI_RENDERER:
            return "\n".join((
                json.dumps({"kind": "deployment", "destination": result["destination"],
                            "files": len(result.get("files") or []),
                            "dependencies": len(result.get("dependencies") or [])}),
                render_poi_report(result["findings"], operation="deploy check",
                                  renderer_name=renderer_name, level=level),
            ))
        rows = [
            f"deployed: {result['destination']}",
            f"files: {len(result.get('files') or [])}",
            f"consumer dependencies: {len(result.get('dependencies') or [])}",
            "",
            render_poi_report(result["findings"], operation="deploy check",
                              renderer_name=renderer_name, level=level),
        ]
        return "\n".join(rows)
    raise ValueError(f"No skill operation renderer for {operation}")


def render_poi(result: dict[str, Any], *,
               renderer_name: str = DEFAULT_POI_RENDERER,
               level: str = "record") -> str:
    selection = POISelection.from_collector_report(
        {"total": 1, "matching": 1, "items": [result]}, title="POI")
    return renderer(renderer_name).render(selection, level=level)


def render_blessing_record(result: dict[str, Any]) -> str:
    if result["type"] == "Tarav.Blessings.Record":
        return "\n".join((
            f"Blessing recorded: {result['id']}",
            f"POI: {result['poi']['id']}",
            f"created: {result['created_at']}",
            f"support: {len(result.get('support') or [])} records",
        ))
    return "\n".join((
        f"Blessing assessment recorded: {result['id']}",
        f"blessing: {result['blessing']}",
        f"assertion: {result['assertion']}",
        f"score: {result['score']}",
        f"created: {result['created_at']}",
    ))


__all__ = [
    "add_output_mode",
    "emit",
    "emit_error",
    "render_blessing_record",
    "render_document_context",
    "render_document_findings",
    "render_document_result",
    "render_loading_context",
    "render_poi",
    "render_poi_report",
    "render_skill_block",
    "render_skill_listing",
    "render_skill_operation",
]
