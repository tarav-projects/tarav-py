"""Agentos.Canvas core — topology model, canvas I/O, layout."""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Topology model
# ---------------------------------------------------------------------------


@dataclass
class TopologyEdge:
    from_node: str
    to_node: str
    edge_id: str


@dataclass
class Topology:
    nodes: list[str] = field(default_factory=list)
    edges: list[TopologyEdge] = field(default_factory=list)


def parse_topology(data: dict[str, Any]) -> Topology:
    """Parse a topology JSON dict into a Topology object."""
    nodes = list(data.get("nodes", []))
    edges: list[TopologyEdge] = []
    for edge in data.get("edges", []):
        edges.append(
            TopologyEdge(
                from_node=edge["from"],
                to_node=edge["to"],
                edge_id=edge["edge-id"],
            )
        )
    return Topology(nodes=nodes, edges=edges)


def topology_to_dict(topo: Topology) -> dict[str, Any]:
    """Serialize a Topology into the canonical JSON format."""
    return {
        "nodes": topo.nodes,
        "edges": [
            {"from": e.from_node, "to": e.to_node, "edge-id": e.edge_id}
            for e in topo.edges
        ],
    }


# ---------------------------------------------------------------------------
# Canvas I/O
# ---------------------------------------------------------------------------

MIN_NODE_WIDTH = 240
MAX_NODE_WIDTH = 320
MIN_NODE_HEIGHT = 140
PX_PER_CHAR = 7
PX_PER_LINE = 50


def estimate_node_size(text: str) -> tuple[int, int]:
    """Estimate canvas node dimensions from text content."""
    lines = text.split("\n")
    num_lines = len(lines)
    max_line_len = max((len(line) for line in lines), default=0)

    width = max(MIN_NODE_WIDTH, min(MAX_NODE_WIDTH, max_line_len * PX_PER_CHAR))
    height = max(MIN_NODE_HEIGHT, num_lines * PX_PER_LINE)
    return (width, height)


def make_node_text(node_id: str) -> str:
    """Generate Canvas.Inline.Note.Style text for a node."""
    return f"## {node_id}\n> node: {node_id}"


def make_edge_id() -> str:
    """Generate a short unique canvas edge id."""
    return uuid.uuid4().hex[:12]


def make_canvas_node(node_id: str, x: float, y: float, text: str | None = None) -> dict[str, Any]:
    """Build a canvas node dict at the given position, auto-sized from content."""
    if text is None:
        text = make_node_text(node_id)
    width, height = estimate_node_size(text)
    return {
        "id": node_id,
        "type": "text",
        "text": text,
        "x": int(x),
        "y": int(y),
        "width": width,
        "height": height,
    }


def resize_node(node: dict[str, Any]) -> None:
    """Resize a canvas node in-place based on its current text content."""
    text = node.get("text", "")
    width, height = estimate_node_size(text)
    node["width"] = width
    node["height"] = height


def read_canvas(path: Path) -> dict[str, Any]:
    """Read a .canvas file and return the parsed JSON."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_canvas(path: Path, canvas: dict[str, Any]) -> None:
    """Write a canvas dict to a .canvas file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(canvas, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def layout_grid(node_ids: list[str]) -> dict[str, tuple[float, float]]:
    """Simple grid layout. Returns {node_id: (x, y)}."""
    cols = max(1, math.ceil(math.sqrt(len(node_ids))))
    spacing_x = MAX_NODE_WIDTH + 80
    spacing_y = MIN_NODE_HEIGHT + 80
    positions: dict[str, tuple[float, float]] = {}
    for i, nid in enumerate(node_ids):
        col = i % cols
        row = i // cols
        positions[nid] = (col * spacing_x, row * spacing_y)
    return positions


def place_one(
    node_id: str,
    canvas: dict[str, Any],
    connected_to: list[str],
) -> tuple[float, float]:
    """Find a good position for a single new node near its neighbors."""
    existing_positions: dict[str, tuple[float, float]] = {}
    for node in canvas.get("nodes", []):
        existing_positions[node["id"]] = (node["x"], node["y"])

    # Compute centroid of connected neighbors
    neighbor_positions = [
        existing_positions[nid]
        for nid in connected_to
        if nid in existing_positions
    ]

    if not neighbor_positions:
        # No connected neighbors found — place below the lowest node
        if existing_positions:
            max_y = max(y for _, y in existing_positions.values())
            return (0.0, max_y + MIN_NODE_HEIGHT + 80)
        return (0.0, 0.0)

    cx = sum(x for x, _ in neighbor_positions) / len(neighbor_positions)
    cy = sum(y for _, y in neighbor_positions) / len(neighbor_positions)

    # Offset below centroid
    candidate = (cx, cy + MIN_NODE_HEIGHT + 80)

    # Nudge to avoid overlap
    candidate = _avoid_overlap(candidate, existing_positions)
    return candidate


def _avoid_overlap(
    pos: tuple[float, float],
    existing: dict[str, tuple[float, float]],
) -> tuple[float, float]:
    """Nudge a position to avoid overlapping existing nodes."""
    x, y = pos
    for _ in range(20):
        overlaps = False
        for ex, ey in existing.values():
            if abs(x - ex) < MAX_NODE_WIDTH + 20 and abs(y - ey) < MIN_NODE_HEIGHT + 20:
                overlaps = True
                break
        if not overlaps:
            return (x, y)
        x += MAX_NODE_WIDTH + 40
    return (x, y)


# ---------------------------------------------------------------------------
# Canvas construction
# ---------------------------------------------------------------------------


def topology_to_canvas(topo: Topology) -> dict[str, Any]:
    """Convert a Topology into a positioned .canvas JSON dict."""
    positions = layout_grid(topo.nodes)

    nodes = [make_canvas_node(nid, *positions[nid]) for nid in topo.nodes]

    edges = [
        {
            "id": make_edge_id(),
            "fromNode": e.from_node,
            "toNode": e.to_node,
            "label": e.edge_id,
        }
        for e in topo.edges
    ]

    return {"nodes": nodes, "edges": edges}


def canvas_to_topology(canvas: dict[str, Any]) -> Topology:
    """Extract topology from an existing .canvas file dict."""
    nodes: list[str] = []
    edge_card_ids: set[str] = set()

    # First pass: identify edge cards by their TID.Pair
    for node in canvas.get("nodes", []):
        text = node.get("text", "")
        lines = text.split("\n")
        is_edge_card = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("> edge:"):
                is_edge_card = True
                break
        if is_edge_card:
            edge_card_ids.add(node["id"])
        else:
            nodes.append(node["id"])

    # Second pass: extract edges
    topo_edges: list[TopologyEdge] = []
    for edge in canvas.get("edges", []):
        from_node = edge.get("fromNode", "")
        to_node = edge.get("toNode", "")
        label = edge.get("label", "")

        # Skip Card.Edge connectors (connected to edge cards)
        if from_node in edge_card_ids or to_node in edge_card_ids:
            continue

        # Labeled.Edge between two node cards
        if label and label != "*":
            topo_edges.append(
                TopologyEdge(from_node=from_node, to_node=to_node, edge_id=label)
            )

    return Topology(nodes=nodes, edges=topo_edges)


# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------


@dataclass
class LintError:
    rule: int
    message: str


def lint_canvas(canvas: dict[str, Any]) -> list[LintError]:
    """Lint a canvas dict against Graph.Model v1 rules."""
    errors: list[LintError] = []

    # Build id sets
    node_ids: set[str] = set()
    edge_card_ids: set[str] = set()
    seen_tids: dict[str, str] = {}  # tid -> node_id for uniqueness

    for node in canvas.get("nodes", []):
        nid = node["id"]
        text = node.get("text", "")
        lines = text.split("\n")
        tid = None
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("> node:") or stripped.startswith("> edge:"):
                tid = stripped[2:]  # "node: x" or "edge: x"
                break

        if tid is None:
            errors.append(LintError(rule=1, message=f"Node '{nid}' has no TID.Pair"))
        else:
            if tid in seen_tids:
                errors.append(
                    LintError(
                        rule=1,
                        message=f"Duplicate TID '{tid}' in nodes '{seen_tids[tid]}' and '{nid}'",
                    )
                )
            seen_tids[tid] = nid

        if tid and tid.startswith("edge:"):
            edge_card_ids.add(nid)
        else:
            node_ids.add(nid)

    # Check edges
    for edge in canvas.get("edges", []):
        from_node = edge.get("fromNode", "")
        to_node = edge.get("toNode", "")
        label = edge.get("label", "")

        from_is_edge_card = from_node in edge_card_ids
        to_is_edge_card = to_node in edge_card_ids

        # Rule 2: direct edge between two node cards must have a label
        if not from_is_edge_card and not to_is_edge_card:
            if not label or label == "*":
                errors.append(
                    LintError(
                        rule=2,
                        message=f"Edge '{from_node}' -> '{to_node}' has no label (naked direct edge)",
                    )
                )

        # Rule 3: edge connected to an edge card must have no label or '*'
        if from_is_edge_card or to_is_edge_card:
            if label and label != "*":
                errors.append(
                    LintError(
                        rule=3,
                        message=f"Card.Edge connector '{from_node}' -> '{to_node}' has label '{label}' (must be empty or '*')",
                    )
                )

    # Rule 4: Card.Edge directional consistency
    # Each connector is classified as: "directed" (arrow flows through) or "undirected" (no arrows).
    # Valid: all connectors same class. Invalid: sink, source, or mixed.
    for ec_id in edge_card_ids:
        connector_classes: list[str] = []  # "directed" | "undirected" | "reverse"
        for edge in canvas.get("edges", []):
            from_end = edge.get("fromEnd", "none")
            to_end = edge.get("toEnd", "arrow")
            if edge.get("toNode") == ec_id:
                # Connector pointing into edge card
                if to_end == "arrow" and from_end == "none":
                    connector_classes.append("directed_in")
                elif to_end == "none" and from_end == "none":
                    connector_classes.append("undirected")
                else:
                    connector_classes.append("other")
            elif edge.get("fromNode") == ec_id:
                # Connector going out of edge card
                if to_end == "arrow" and from_end == "none":
                    connector_classes.append("directed_out")
                elif to_end == "none" and from_end == "none":
                    connector_classes.append("undirected")
                else:
                    connector_classes.append("other")

        if len(connector_classes) < 2:
            continue

        classes = set(connector_classes)

        # Sink: all connectors flow in
        if classes == {"directed_in"}:
            errors.append(
                LintError(rule=4, message=f"Edge card '{ec_id}' is a sink (all arrows point in)")
            )
        # Source: all connectors flow out
        elif classes == {"directed_out"}:
            errors.append(
                LintError(rule=4, message=f"Edge card '{ec_id}' is a source (all arrows point out)")
            )
        # Mixed: some directed, some undirected
        elif "undirected" in classes and classes - {"undirected"}:
            errors.append(
                LintError(rule=4, message=f"Edge card '{ec_id}' has mixed directionality")
            )

    return errors
