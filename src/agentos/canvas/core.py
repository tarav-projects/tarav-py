# $kw: --from Agentos.Canvas --from Canvas.Model
"""Agentos.Canvas core — two-layer model, canvas I/O, layout, sync, lint."""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any






MODEL_KEY = "_model"


@dataclass
class ModelCard:
    id: str
    type: str


@dataclass
class ModelRelationship:
    from_card: str
    to_card: str
    rel_type: str
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


def make_canvas_edge(from_node: str, to_node: str, label: str) -> dict[str, Any]:
    """Build a canvas edge dict with a fresh id."""
    return {
        "id": make_edge_id(),
        "fromNode": from_node,
        "toNode": to_node,
        "label": label,
    }


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







def model_to_canvas(model: CanvasModel) -> dict[str, Any]:
    """Convert a CanvasModel into a positioned .canvas JSON dict with _model."""
    card_ids = [c.id for c in model.cards]
    positions = layout_grid(card_ids)

    nodes = [
        make_canvas_node(card, *positions[card.id])
        for card in model.cards
    ]

    edges = [
        make_canvas_edge(r.from_card, r.to_card, r.id)
        for r in model.relationships
        if r.rel_type == "edge"
    ]

    canvas: dict[str, Any] = {"nodes": nodes, "edges": edges}
    write_model(canvas, model)
    return canvas







@dataclass
class RenderError:
    rule: str
    message: str


@dataclass
class RenderAction:
    action: str
    detail: str


@dataclass
class RenderResult:
    errors: list[RenderError]
    actions: list[RenderAction]
    canvas: dict[str, Any]


def render_canvas(canvas: dict[str, Any]) -> RenderResult:
    """Compile model into canvas. model + old canvas → new canvas.

    The model is the authority for what exists. The old canvas provides
    positions, sizes, text, and colors. The output is a new canvas that
    reflects the model with layout inherited from the old canvas.

    Returns a RenderResult with errors (lint-like), actions (what changed),
    and the new canvas dict. The caller decides whether to write it.
    """
    errors: list[RenderError] = []
    actions: list[RenderAction] = []
    model = read_model(canvas)

    if not model.cards and not model.relationships:
        errors.append(RenderError(
            rule="model.missing",
            message="No _model found in canvas file",
        ))
        return RenderResult(errors=errors, actions=actions, canvas=canvas)


    old_nodes_by_id: dict[str, dict[str, Any]] = {
        n["id"]: n for n in canvas.get("nodes", [])
    }

    old_edges_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for e in canvas.get("edges", []):
        key = (e.get("fromNode", ""), e.get("toNode", ""))
        old_edges_by_pair[key] = e


    new_nodes: list[dict[str, Any]] = []

    placed_positions: dict[str, tuple[float, float]] = {}

    for card in model.cards:
        old_node = old_nodes_by_id.get(card.id)
        if old_node is not None:

            node = dict(old_node)


            model_text = _get_model_card_text(canvas, card.id)
            if model_text is not None:
                node["text"] = model_text
                actions.append(RenderAction("migrated_text", card.id))

            new_nodes.append(node)
            placed_positions[card.id] = (node["x"], node["y"])
        else:

            connected_to = [
                r.to_card if r.from_card == card.id else r.from_card
                for r in model.relationships
                if r.rel_type == "edge" and (r.from_card == card.id or r.to_card == card.id)
            ]

            temp_canvas: dict[str, Any] = {"nodes": new_nodes}
            x, y = place_one(card.id, temp_canvas, connected_to)
            node = make_canvas_node(card, x, y)
            new_nodes.append(node)
            placed_positions[card.id] = (x, y)
            actions.append(RenderAction("created_node", card.id))


    new_edges: list[dict[str, Any]] = []
    for rel in model.relationships:
        if rel.rel_type != "edge":
            continue

        pair = (rel.from_card, rel.to_card)
        old_edge = old_edges_by_pair.get(pair)
        if old_edge is not None:

            edge = dict(old_edge)

            if edge.get("label", "") != rel.id:
                actions.append(RenderAction("updated_label",
                    f"{rel.from_card} -> {rel.to_card}: '{edge.get('label', '')}' -> '{rel.id}'"))
                edge["label"] = rel.id
            new_edges.append(edge)
        else:

            new_edges.append(make_canvas_edge(rel.from_card, rel.to_card, rel.id))
            actions.append(RenderAction("created_edge",
                f"{rel.from_card} --{rel.id}--> {rel.to_card}"))


    model_card_ids = {c.id for c in model.cards}
    for nid in old_nodes_by_id:
        if nid not in model_card_ids:
            actions.append(RenderAction("dropped_node", nid))

    model_edge_pairs = {
        (r.from_card, r.to_card) for r in model.relationships if r.rel_type == "edge"
    }
    for pair, old_edge in old_edges_by_pair.items():
        if pair not in model_edge_pairs:
            actions.append(RenderAction("dropped_edge",
                f"{pair[0]} -> {pair[1]} (label: '{old_edge.get('label', '')}')"))


    _clear_model_card_texts(canvas)


    new_canvas: dict[str, Any] = {"nodes": new_nodes, "edges": new_edges}
    write_model(new_canvas, model)


    errors = _lint_rendered(new_canvas, model)

    return RenderResult(errors=errors, actions=actions, canvas=new_canvas)


def _get_model_card_text(canvas: dict[str, Any], card_id: str) -> str | None:
    """Get pending text for a card from the model layer, if any."""
    raw = canvas.get(MODEL_KEY, {})
    texts = raw.get("_texts", {})
    return texts.get(card_id)


def _clear_model_card_texts(canvas: dict[str, Any]) -> None:
    """Clear all pending texts from the model layer."""
    raw = canvas.get(MODEL_KEY, {})
    raw.pop("_texts", None)


def _lint_rendered(canvas: dict[str, Any], model: CanvasModel) -> list[RenderError]:
    """Lint a rendered canvas against model rules."""
    errors: list[RenderError] = []

    canvas_nodes_by_id: dict[str, dict[str, Any]] = {
        n["id"]: n for n in canvas.get("nodes", [])
    }


    for card in model.cards:
        node = canvas_nodes_by_id.get(card.id)
        if node is None:
            continue
        text = node.get("text", "")
        expected_tid = f"{card.type}: {card.id}"
        if expected_tid not in text:
            errors.append(RenderError(
                rule="model.card.type_mismatch",
                message=f"Card '{card.id}' model type '{card.type}' not found in canvas text",
            ))


    for rel in model.relationships:
        if rel.rel_type != "adjacent":
            continue
        a = canvas_nodes_by_id.get(rel.from_card)
        b = canvas_nodes_by_id.get(rel.to_card)
        if a is None or b is None:
            continue
        if not _nodes_adjacent(a, b):
            errors.append(RenderError(
                rule="model.rel.adjacent",
                message=f"Adjacent relationship '{rel.id}': cards '{rel.from_card}' and '{rel.to_card}' do not touch",
            ))


    for rel in model.relationships:
        if rel.rel_type != "contains":
            continue
        parent = canvas_nodes_by_id.get(rel.from_card)
        child = canvas_nodes_by_id.get(rel.to_card)
        if parent is None or child is None:
            continue
        if not _node_contains(parent, child):
            errors.append(RenderError(
                rule="model.rel.contains",
                message=f"Contains relationship '{rel.id}': '{rel.to_card}' is not inside '{rel.from_card}'",
            ))


    for edge in canvas.get("edges", []):
        label = edge.get("label", "")
        if label and not _is_tid_pair(label):
            errors.append(RenderError(
                rule="canvas.edge.label_not_tid",
                message=f"Edge '{edge.get('fromNode')}' -> '{edge.get('toNode')}' label '{label}' is not a valid TID.Pair (expected 'type: id')",
            ))

    return errors


def _is_tid_pair(label: str) -> bool:
    """Check if a string is a valid TID.Pair ('type: id')."""
    parts = label.split(": ", 1)
    return len(parts) == 2 and parts[0].strip() != "" and parts[1].strip() != ""


def _nodes_adjacent(a: dict[str, Any], b: dict[str, Any], tolerance: int = 10) -> bool:
    """Check if two nodes touch borders (within tolerance pixels)."""
    ax, ay, aw, ah = a["x"], a["y"], a["width"], a["height"]
    bx, by, bw, bh = b["x"], b["y"], b["width"], b["height"]


    h_touch = (
        abs((ax + aw) - bx) <= tolerance or
        abs((bx + bw) - ax) <= tolerance
    )
    v_overlap = not (ay + ah < by or by + bh < ay)


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
