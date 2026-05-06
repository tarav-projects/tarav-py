"""Agentos.Canvas core — two-layer model, canvas I/O, layout, sync, lint."""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Model layer
# ---------------------------------------------------------------------------

MODEL_KEY = "_model"


@dataclass
class ModelCard:
    id: str
    type: str


@dataclass
class ModelRelationship:
    from_card: str
    to_card: str
    rel_type: str  # edge, adjacent, contains
    id: str


@dataclass
class CanvasModel:
    cards: list[ModelCard] = field(default_factory=list)
    relationships: list[ModelRelationship] = field(default_factory=list)


def parse_model(data: dict[str, Any]) -> CanvasModel:
    """Parse a _model dict into a CanvasModel."""
    cards = [
        ModelCard(id=c["id"], type=c["type"])
        for c in data.get("cards", [])
    ]
    relationships = [
        ModelRelationship(
            from_card=r["from"],
            to_card=r["to"],
            rel_type=r["type"],
            id=r["id"],
        )
        for r in data.get("relationships", [])
    ]
    return CanvasModel(cards=cards, relationships=relationships)


def model_to_dict(model: CanvasModel) -> dict[str, Any]:
    """Serialize a CanvasModel to dict."""
    return {
        "cards": [{"id": c.id, "type": c.type} for c in model.cards],
        "relationships": [
            {"from": r.from_card, "to": r.to_card, "type": r.rel_type, "id": r.id}
            for r in model.relationships
        ],
    }


def read_model(canvas: dict[str, Any]) -> CanvasModel:
    """Extract the model from a canvas dict. Returns empty model if absent."""
    raw = canvas.get(MODEL_KEY)
    if raw is None:
        return CanvasModel()
    return parse_model(raw)


def write_model(canvas: dict[str, Any], model: CanvasModel) -> None:
    """Write the model into a canvas dict in-place."""
    canvas[MODEL_KEY] = model_to_dict(model)


# ---------------------------------------------------------------------------
# Topology (init input format)
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
    """Parse a topology JSON dict into a Topology object.

    Supports both the new cards+relationships format and the legacy
    nodes+edges format.
    """
    # New format: cards + relationships
    if "cards" in data:
        nodes = [c["id"] for c in data["cards"]]
        edges: list[TopologyEdge] = []
        for r in data.get("relationships", []):
            edges.append(
                TopologyEdge(from_node=r["from"], to_node=r["to"], edge_id=r["id"])
            )
        return Topology(nodes=nodes, edges=edges)

    # Legacy format: nodes (string list) + edges
    nodes = list(data.get("nodes", []))
    edges = []
    for edge in data.get("edges", []):
        edges.append(
            TopologyEdge(
                from_node=edge["from"],
                to_node=edge["to"],
                edge_id=edge["edge-id"],
            )
        )
    return Topology(nodes=nodes, edges=edges)


def parse_init_input(data: dict[str, Any]) -> CanvasModel:
    """Parse the init input JSON into a CanvasModel.

    Supports both the new cards+relationships format and the legacy
    nodes+edges format (cards default to type 'node').
    """
    if "cards" in data:
        return parse_model(data)

    # Legacy: nodes as strings, edges
    cards = [ModelCard(id=n, type="node") for n in data.get("nodes", [])]
    relationships = [
        ModelRelationship(
            from_card=e["from"],
            to_card=e["to"],
            rel_type="edge",
            id=e.get("edge-id", e.get("id", uuid.uuid4().hex[:12])),
        )
        for e in data.get("edges", [])
    ]
    return CanvasModel(cards=cards, relationships=relationships)


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


def make_node_text(card: ModelCard) -> str:
    """Generate TID.Pair text for a card."""
    return f"## {card.id}\n> {card.type}: {card.id}"


def make_edge_id() -> str:
    """Generate a short unique canvas edge id."""
    return uuid.uuid4().hex[:12]


def make_canvas_node(
    card: ModelCard, x: float, y: float, text: str | None = None
) -> dict[str, Any]:
    """Build a canvas node dict at the given position, auto-sized from content."""
    if text is None:
        text = make_node_text(card)
    width, height = estimate_node_size(text)
    return {
        "id": card.id,
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


def layout_grid(card_ids: list[str]) -> dict[str, tuple[float, float]]:
    """Simple grid layout. Returns {card_id: (x, y)}."""
    cols = max(1, math.ceil(math.sqrt(len(card_ids))))
    spacing_x = MAX_NODE_WIDTH + 80
    spacing_y = MIN_NODE_HEIGHT + 80
    positions: dict[str, tuple[float, float]] = {}
    for i, cid in enumerate(card_ids):
        col = i % cols
        row = i // cols
        positions[cid] = (col * spacing_x, row * spacing_y)
    return positions


def place_one(
    card_id: str,
    canvas: dict[str, Any],
    connected_to: list[str],
) -> tuple[float, float]:
    """Find a good position for a single new node near its neighbors."""
    existing_positions: dict[str, tuple[float, float]] = {}
    for node in canvas.get("nodes", []):
        existing_positions[node["id"]] = (node["x"], node["y"])

    neighbor_positions = [
        existing_positions[nid]
        for nid in connected_to
        if nid in existing_positions
    ]

    if not neighbor_positions:
        if existing_positions:
            max_y = max(y for _, y in existing_positions.values())
            return (0.0, max_y + MIN_NODE_HEIGHT + 80)
        return (0.0, 0.0)

    cx = sum(x for x, _ in neighbor_positions) / len(neighbor_positions)
    cy = sum(y for _, y in neighbor_positions) / len(neighbor_positions)

    candidate = (cx, cy + MIN_NODE_HEIGHT + 80)
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
# Canvas construction from model
# ---------------------------------------------------------------------------


def model_to_canvas(model: CanvasModel) -> dict[str, Any]:
    """Convert a CanvasModel into a positioned .canvas JSON dict with _model."""
    card_ids = [c.id for c in model.cards]
    positions = layout_grid(card_ids)

    nodes = [
        make_canvas_node(card, *positions[card.id])
        for card in model.cards
    ]

    edges = [
        {
            "id": make_edge_id(),
            "fromNode": r.from_card,
            "toNode": r.to_card,
            "label": r.id,
        }
        for r in model.relationships
        if r.rel_type == "edge"
    ]

    canvas: dict[str, Any] = {"nodes": nodes, "edges": edges}
    write_model(canvas, model)
    return canvas


# ---------------------------------------------------------------------------
# Sync — forward-pass model → canvas
# ---------------------------------------------------------------------------


@dataclass
class SyncAction:
    action: str  # "created_node", "created_edge", "skipped"
    detail: str


def sync_canvas(canvas: dict[str, Any]) -> list[SyncAction]:
    """Forward-pass sync: model → canvas.

    Creates canvas nodes for model cards that have no canvas node.
    Creates canvas edges for model edge-relationships that have no canvas edge.
    Non-edge relationships (adjacent, contains) are not synced — they are
    spatial constraints checked by lint.
    """
    model = read_model(canvas)
    actions: list[SyncAction] = []

    # Index existing canvas nodes and edges
    canvas_node_ids = {n["id"] for n in canvas.get("nodes", [])}
    canvas_edge_pairs = set()
    for e in canvas.get("edges", []):
        canvas_edge_pairs.add((e.get("fromNode"), e.get("toNode"), e.get("label", "")))

    # Forward-pass: model cards → canvas nodes
    for card in model.cards:
        if card.id not in canvas_node_ids:
            connected_to = [
                r.to_card if r.from_card == card.id else r.from_card
                for r in model.relationships
                if r.rel_type == "edge" and (r.from_card == card.id or r.to_card == card.id)
            ]
            x, y = place_one(card.id, canvas, connected_to)
            node = make_canvas_node(card, x, y)
            resize_node(node)
            canvas.setdefault("nodes", []).append(node)
            canvas_node_ids.add(card.id)
            actions.append(SyncAction("created_node", card.id))

    # Forward-pass: model edge-relationships → canvas edges
    for rel in model.relationships:
        if rel.rel_type != "edge":
            continue
        if (rel.from_card, rel.to_card, rel.id) not in canvas_edge_pairs:
            canvas.setdefault("edges", []).append({
                "id": make_edge_id(),
                "fromNode": rel.from_card,
                "toNode": rel.to_card,
                "label": rel.id,
            })
            actions.append(SyncAction("created_edge", f"{rel.from_card} --{rel.id}--> {rel.to_card}"))

    return actions


# ---------------------------------------------------------------------------
# Lint — read-only model↔canvas consistency
# ---------------------------------------------------------------------------


@dataclass
class LintError:
    rule: str
    message: str


def lint_canvas(canvas: dict[str, Any]) -> list[LintError]:
    """Lint a canvas dict against model↔canvas consistency rules."""
    errors: list[LintError] = []
    model = read_model(canvas)

    if not model.cards and not model.relationships:
        errors.append(LintError(
            rule="model.missing",
            message="No _model found in canvas file",
        ))
        return errors

    # Index canvas state
    canvas_node_ids = {n["id"] for n in canvas.get("nodes", [])}
    canvas_nodes_by_id: dict[str, dict[str, Any]] = {
        n["id"]: n for n in canvas.get("nodes", [])
    }
    canvas_edge_set: set[tuple[str, str, str]] = set()
    for e in canvas.get("edges", []):
        canvas_edge_set.add((e.get("fromNode", ""), e.get("toNode", ""), e.get("label", "")))

    model_card_ids = {c.id for c in model.cards}

    # Rule: every model card has a canvas node
    for card in model.cards:
        if card.id not in canvas_node_ids:
            errors.append(LintError(
                rule="model.card.missing_node",
                message=f"Model card '{card.id}' has no canvas node",
            ))

    # Rule: model card type matches canvas TID.Pair
    for card in model.cards:
        node = canvas_nodes_by_id.get(card.id)
        if node is None:
            continue
        text = node.get("text", "")
        expected_tid = f"{card.type}: {card.id}"
        if expected_tid not in text:
            errors.append(LintError(
                rule="model.card.type_mismatch",
                message=f"Card '{card.id}' model type '{card.type}' not found in canvas text",
            ))

    # Rule: every model edge-relationship has a canvas edge
    for rel in model.relationships:
        if rel.rel_type != "edge":
            continue
        if (rel.from_card, rel.to_card, rel.id) not in canvas_edge_set:
            errors.append(LintError(
                rule="model.rel.missing_edge",
                message=f"Model relationship '{rel.id}' ({rel.from_card} -> {rel.to_card}) has no canvas edge",
            ))

    # Rule: adjacent — cards touch borders
    for rel in model.relationships:
        if rel.rel_type != "adjacent":
            continue
        a = canvas_nodes_by_id.get(rel.from_card)
        b = canvas_nodes_by_id.get(rel.to_card)
        if a is None or b is None:
            continue
        if not _nodes_adjacent(a, b):
            errors.append(LintError(
                rule="model.rel.adjacent",
                message=f"Adjacent relationship '{rel.id}': cards '{rel.from_card}' and '{rel.to_card}' do not touch",
            ))

    # Rule: contains — child inside parent
    for rel in model.relationships:
        if rel.rel_type != "contains":
            continue
        parent = canvas_nodes_by_id.get(rel.from_card)
        child = canvas_nodes_by_id.get(rel.to_card)
        if parent is None or child is None:
            continue
        if not _node_contains(parent, child):
            errors.append(LintError(
                rule="model.rel.contains",
                message=f"Contains relationship '{rel.id}': '{rel.to_card}' is not inside '{rel.from_card}'",
            ))

    # Rule: canvas nodes not in model (informational)
    for nid in canvas_node_ids:
        if nid not in model_card_ids:
            errors.append(LintError(
                rule="canvas.orphan_node",
                message=f"Canvas node '{nid}' has no model card",
            ))

    return errors


def _nodes_adjacent(a: dict[str, Any], b: dict[str, Any], tolerance: int = 10) -> bool:
    """Check if two nodes touch borders (within tolerance pixels)."""
    ax, ay, aw, ah = a["x"], a["y"], a["width"], a["height"]
    bx, by, bw, bh = b["x"], b["y"], b["width"], b["height"]

    # Check horizontal adjacency (right edge of a touches left edge of b, or vice versa)
    h_touch = (
        abs((ax + aw) - bx) <= tolerance or
        abs((bx + bw) - ax) <= tolerance
    )
    v_overlap = not (ay + ah < by or by + bh < ay)

    # Check vertical adjacency (bottom of a touches top of b, or vice versa)
    v_touch = (
        abs((ay + ah) - by) <= tolerance or
        abs((by + bh) - ay) <= tolerance
    )
    h_overlap = not (ax + aw < bx or bx + bw < ax)

    return (h_touch and v_overlap) or (v_touch and h_overlap)


def _node_contains(parent: dict[str, Any], child: dict[str, Any], tolerance: int = 10) -> bool:
    """Check if child node fits inside parent node (within tolerance)."""
    px, py, pw, ph = parent["x"], parent["y"], parent["width"], parent["height"]
    cx, cy, cw, ch = child["x"], child["y"], child["width"], child["height"]

    return (
        cx >= px - tolerance and
        cy >= py - tolerance and
        cx + cw <= px + pw + tolerance and
        cy + ch <= py + ph + tolerance
    )
