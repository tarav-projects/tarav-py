"""CLI commands for agentos canvas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError

from .core import (
    ModelCard,
    ModelRelationship,
    make_canvas_node,
    make_edge_id,
    model_to_canvas,
    model_to_dict,
    parse_model,
    place_one,
    read_canvas,
    read_model,
    resize_node,
    sync_canvas,
    lint_canvas,
    write_canvas,
    write_model,
)


def _resize_new_nodes(canvas: dict[str, Any], new_node_ids: set[str]) -> None:
    """Auto-resize only newly created nodes."""
    for node in canvas.get("nodes", []):
        if node["id"] in new_node_ids:
            resize_node(node)


def _cmd_canvas_init(args: argparse.Namespace) -> int:
    model_path = Path(args.model)
    if not model_path.exists():
        raise CliError(f"model file not found: {model_path}")

    out_path = Path(args.file)
    if out_path.exists() and not args.this_is_dangerous:
        raise CliError(
            f"{out_path} already exists. Re-init overwrites all positions. "
            "Pass --this-is-dangerous to proceed."
        )

    data = json.loads(model_path.read_text(encoding="utf-8"))
    model = parse_model(data)
    canvas = model_to_canvas(model)
    new_ids = {c.id for c in model.cards}
    _resize_new_nodes(canvas, new_ids)

    write_canvas(out_path, canvas)
    print(f"Created {out_path} ({len(model.cards)} cards, {len(model.relationships)} relationships)")
    return 0


def _cmd_canvas_show(args: argparse.Namespace) -> int:
    canvas_path = Path(args.file)
    if not canvas_path.exists():
        raise CliError(f"canvas file not found: {canvas_path}")

    canvas = read_canvas(canvas_path)
    model = read_model(canvas)
    output = model_to_dict(model)
    print(json.dumps(output, indent=2))
    return 0


def _cmd_canvas_add_card(args: argparse.Namespace) -> int:
    canvas_path = Path(args.file)
    if not canvas_path.exists():
        raise CliError(f"canvas file not found: {canvas_path}")

    canvas = read_canvas(canvas_path)
    model = read_model(canvas)

    card_id = args.card_id
    card_type = args.card_type

    # Check if card already exists in model
    for card in model.cards:
        if card.id == card_id:
            raise CliError(f"card '{card_id}' already exists in model")

    new_card = ModelCard(id=card_id, type=card_type)
    model.cards.append(new_card)

    # Determine connections
    connected_to = []
    if args.connect_to:
        connected_to.append(args.connect_to)

    # Place the canvas node (new card only)
    x, y = place_one(card_id, canvas, connected_to)
    new_node = make_canvas_node(new_card, x, y)
    resize_node(new_node)
    canvas.setdefault("nodes", []).append(new_node)

    # Add edge relationship if --connect-to and --edge-id provided
    if args.connect_to and args.edge_id:
        model.relationships.append(ModelRelationship(
            from_card=args.connect_to,
            to_card=card_id,
            rel_type="edge",
            id=args.edge_id,
        ))
        canvas.setdefault("edges", []).append({
            "id": make_edge_id(),
            "fromNode": args.connect_to,
            "toNode": card_id,
            "label": args.edge_id,
        })

    write_model(canvas, model)
    write_canvas(canvas_path, canvas)
    print(f"Added card '{card_id}' (type: {card_type})")
    return 0


def _cmd_canvas_add_edge(args: argparse.Namespace) -> int:
    canvas_path = Path(args.file)
    if not canvas_path.exists():
        raise CliError(f"canvas file not found: {canvas_path}")

    canvas = read_canvas(canvas_path)
    model = read_model(canvas)

    # Verify both cards exist in model
    model_card_ids = {c.id for c in model.cards}
    if args.from_card not in model_card_ids:
        raise CliError(f"card '{args.from_card}' not found in model")
    if args.to_card not in model_card_ids:
        raise CliError(f"card '{args.to_card}' not found in model")

    rel_type = args.rel_type or "edge"

    # Add to model
    model.relationships.append(ModelRelationship(
        from_card=args.from_card,
        to_card=args.to_card,
        rel_type=rel_type,
        id=args.edge_id,
    ))

    # Add canvas edge for edge-type relationships
    if rel_type == "edge":
        canvas.setdefault("edges", []).append({
            "id": make_edge_id(),
            "fromNode": args.from_card,
            "toNode": args.to_card,
            "label": args.edge_id,
        })

    write_model(canvas, model)
    write_canvas(canvas_path, canvas)
    print(f"Added {rel_type} '{args.edge_id}' ({args.from_card} -> {args.to_card})")
    return 0



def _cmd_canvas_sync(args: argparse.Namespace) -> int:
    canvas_path = Path(args.file)
    if not canvas_path.exists():
        raise CliError(f"canvas file not found: {canvas_path}")

    canvas = read_canvas(canvas_path)
    actions = sync_canvas(canvas)

    if not actions:
        print("Already in sync.")
        return 0

    new_node_ids = {a.detail for a in actions if a.action == "created_node"}
    _resize_new_nodes(canvas, new_node_ids)
    write_canvas(canvas_path, canvas)

    for action in actions:
        print(f"[{action.action}] {action.detail}")
    print(f"\n{len(actions)} action(s)")
    return 0


def _cmd_canvas_lint(args: argparse.Namespace) -> int:
    canvas_path = Path(args.file)
    if not canvas_path.exists():
        raise CliError(f"canvas file not found: {canvas_path}")

    canvas = read_canvas(canvas_path)
    errors = lint_canvas(canvas)

    if not errors:
        print("OK")
        return 0

    for err in errors:
        print(f"[{err.rule}] {err.message}", file=sys.stderr)
    print(f"\n{len(errors)} error(s)", file=sys.stderr)
    return 1


def register_canvas_commands(subparsers: argparse._SubParsersAction) -> None:
    canvas_parser = subparsers.add_parser(
        "canvas",
        help="Visual graph surface operations on Obsidian Canvas files.",
    )
    canvas_subparsers = canvas_parser.add_subparsers(dest="canvas_command")

    # init
    init_parser = canvas_subparsers.add_parser(
        "init", help="Create a canvas from a topology JSON file."
    )
    init_parser.add_argument("--model", required=True, help="Path to model JSON file (same format as _model).")
    init_parser.add_argument("--file", required=True, help="Output .canvas file path.")
    init_parser.add_argument("--this-is-dangerous", action="store_true", dest="this_is_dangerous", help="Overwrite existing canvas (all positions will be reset).")
    init_parser.set_defaults(handler=_cmd_canvas_init)

    # show
    show_parser = canvas_subparsers.add_parser(
        "show", help="Print model as JSON."
    )
    show_parser.add_argument("--file", required=True, help="Path to .canvas file.")
    show_parser.set_defaults(handler=_cmd_canvas_show)

    # add-card
    add_card_parser = canvas_subparsers.add_parser(
        "add-card", help="Add a card to an existing canvas."
    )
    add_card_parser.add_argument("--file", required=True, help="Path to .canvas file.")
    add_card_parser.add_argument("--card-id", required=True, help="ID for the new card.")
    add_card_parser.add_argument("--card-type", required=True, help="Type for the new card.")
    add_card_parser.add_argument("--connect-to", help="Existing card to connect to.")
    add_card_parser.add_argument("--edge-id", help="Edge ID for the connection.")
    add_card_parser.set_defaults(handler=_cmd_canvas_add_card)

    # add-edge
    add_edge_parser = canvas_subparsers.add_parser(
        "add-edge", help="Add a relationship between existing cards."
    )
    add_edge_parser.add_argument("--file", required=True, help="Path to .canvas file.")
    add_edge_parser.add_argument("--from", dest="from_card", required=True, help="Source card ID.")
    add_edge_parser.add_argument("--to", dest="to_card", required=True, help="Target card ID.")
    add_edge_parser.add_argument("--edge-id", required=True, help="Relationship ID.")
    add_edge_parser.add_argument("--rel-type", default="edge", help="Relationship type (edge, adjacent, contains). Default: edge.")
    add_edge_parser.set_defaults(handler=_cmd_canvas_add_edge)

    # sync
    sync_parser = canvas_subparsers.add_parser(
        "sync", help="Forward-pass model to canvas sync."
    )
    sync_parser.add_argument("--file", required=True, help="Path to .canvas file.")
    sync_parser.set_defaults(handler=_cmd_canvas_sync)

    # lint
    lint_parser = canvas_subparsers.add_parser(
        "lint", help="Validate model-canvas consistency."
    )
    lint_parser.add_argument("--file", required=True, help="Path to .canvas file.")
    lint_parser.set_defaults(handler=_cmd_canvas_lint)
