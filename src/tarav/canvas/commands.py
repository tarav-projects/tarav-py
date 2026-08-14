# $kw: ^canvas-poi-command --from POI.System --from POI.Linter --note [CT] Canvas render errors use common POI reporting while actions and apply behavior remain separate ^c20260729-49u
"""CLI commands for tarav canvas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tarav._core.errors import CliError
from tarav.canvas.core import (
    CanvasModel,
    ModelCard,
    ModelRelationship,
    make_canvas_edge,
    make_canvas_node,
    model_to_canvas,
    model_to_dict,
    parse_model,
    place_one,
    read_canvas,
    read_model,
    render_canvas,
    write_canvas,
    write_model,
)
from tarav.canvas.poi import build_canvas_linter_report


def _load_canvas(args: argparse.Namespace) -> tuple[Path, dict[str, Any], CanvasModel]:
    """Open the canvas file referenced by args.file and parse it.

    Returns (path, canvas, model). Raises CliError if the file is missing.
    """
    path = Path(args.file)
    if not path.exists():
        raise CliError(f"canvas file not found: {path}")
    canvas = read_canvas(path)
    return path, canvas, read_model(canvas)


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

    write_canvas(out_path, canvas)
    print(
        f"Created {out_path} ({len(model.cards)} cards, {len(model.relationships)} relationships)"
    )
    return 0


def _cmd_canvas_show(args: argparse.Namespace) -> int:
    _, _, model = _load_canvas(args)
    print(json.dumps(model_to_dict(model), indent=2))
    return 0


def _cmd_canvas_card(args: argparse.Namespace) -> int:
    _, canvas, model = _load_canvas(args)


    if not args.card_id:
        for card in model.cards:
            print(f"{card.type}: {card.id}")
        return 0


    card = None
    for c in model.cards:
        if c.id == args.card_id:
            card = c
            break
    if card is None:
        raise CliError(f"card '{args.card_id}' not found in model")


    canvas_node = None
    for n in canvas.get("nodes", []):
        if n["id"] == args.card_id:
            canvas_node = n
            break


    if args.text:
        if canvas_node is None:
            raise CliError(f"card '{args.card_id}' has no canvas node")
        print(canvas_node.get("text", ""))
        return 0


    result: dict[str, Any] = {
        "id": card.id,
        "type": card.type,
    }

    if canvas_node is not None:
        result["text"] = canvas_node.get("text", "")
        result["x"] = canvas_node.get("x")
        result["y"] = canvas_node.get("y")
        result["width"] = canvas_node.get("width")
        result["height"] = canvas_node.get("height")
        if "color" in canvas_node:
            result["color"] = canvas_node["color"]


    rels = []
    for r in model.relationships:
        if r.from_card == args.card_id or r.to_card == args.card_id:
            rels.append(
                {
                    "from": r.from_card,
                    "to": r.to_card,
                    "type": r.rel_type,
                    "id": r.id,
                }
            )
    if rels:
        result["relationships"] = rels

    print(json.dumps(result, indent=2))
    return 0


def _cmd_canvas_add_card(args: argparse.Namespace) -> int:
    canvas_path, canvas, model = _load_canvas(args)

    card_id = args.card_id
    card_type = args.card_type

    for card in model.cards:
        if card.id == card_id:
            raise CliError(f"card '{card_id}' already exists in model")

    new_card = ModelCard(id=card_id, type=card_type)
    model.cards.append(new_card)


    connected_to = []
    if args.connect_to:
        connected_to.append(args.connect_to)

    x, y = place_one(card_id, canvas, connected_to)
    new_node = make_canvas_node(new_card, x, y)
    canvas.setdefault("nodes", []).append(new_node)


    if args.connect_to and args.edge_id:
        model.relationships.append(
            ModelRelationship(
                from_card=args.connect_to,
                to_card=card_id,
                rel_type="edge",
                id=args.edge_id,
            )
        )
        canvas.setdefault("edges", []).append(
            make_canvas_edge(args.connect_to, card_id, args.edge_id)
        )

    write_model(canvas, model)
    write_canvas(canvas_path, canvas)
    print(f"Added card '{card_id}' (type: {card_type})")
    return 0


def _cmd_canvas_add_edge(args: argparse.Namespace) -> int:
    canvas_path, canvas, model = _load_canvas(args)

    model_card_ids = {c.id for c in model.cards}
    if args.from_card not in model_card_ids:
        raise CliError(f"card '{args.from_card}' not found in model")
    if args.to_card not in model_card_ids:
        raise CliError(f"card '{args.to_card}' not found in model")

    rel_type = args.rel_type or "edge"

    model.relationships.append(
        ModelRelationship(
            from_card=args.from_card,
            to_card=args.to_card,
            rel_type=rel_type,
            id=args.edge_id,
        )
    )

    if rel_type == "edge":
        canvas.setdefault("edges", []).append(
            make_canvas_edge(args.from_card, args.to_card, args.edge_id)
        )

    write_model(canvas, model)
    write_canvas(canvas_path, canvas)
    print(f"Added {rel_type} '{args.edge_id}' ({args.from_card} -> {args.to_card})")
    return 0


def _cmd_canvas_render(args: argparse.Namespace) -> int:
    canvas_path, canvas, _ = _load_canvas(args)
    result = render_canvas(canvas)

    linter_report = build_canvas_linter_report(
        result.errors,
        canvas_path=canvas_path,
        actions=result.actions,
    )
    rendered_pois = linter_report.render_text()
    if rendered_pois:
        print(rendered_pois, file=sys.stderr)


    if result.actions:
        for action in result.actions:
            print(f"[{action.action}] {action.detail}")

    if not args.apply:

        if result.errors:
            print(f"\n{len(result.errors)} error(s)", file=sys.stderr)
            return 1
        if result.actions:
            print(
                f"\n{len(result.actions)} action(s) pending. Run with --apply to write."
            )
            return 0
        print("OK")
        return 0


    write_canvas(canvas_path, result.canvas)

    if result.actions:
        print(f"\n{len(result.actions)} action(s) applied.")
    else:
        print("Nothing to do.")

    if result.errors:
        print(f"{len(result.errors)} error(s) remain after render.", file=sys.stderr)
        return 1

    return 0


def register_canvas_commands(subparsers: argparse._SubParsersAction) -> None:
    canvas_parser = subparsers.add_parser(
        "canvas",
        help="Visual graph surface operations on Obsidian Canvas files.",
    )
    canvas_subparsers = canvas_parser.add_subparsers(dest="canvas_command")


    init_parser = canvas_subparsers.add_parser(
        "init", help="Create a canvas from a model JSON file."
    )
    init_parser.add_argument(
        "--model",
        required=True,
        help="Path to model JSON file (same format as _model).",
    )
    init_parser.add_argument("--file", required=True, help="Output .canvas file path.")
    init_parser.add_argument(
        "--this-is-dangerous",
        action="store_true",
        dest="this_is_dangerous",
        help="Overwrite existing canvas (all positions will be reset).",
    )
    init_parser.set_defaults(handler=_cmd_canvas_init)


    show_parser = canvas_subparsers.add_parser("show", help="Print model as JSON.")
    show_parser.add_argument("--file", required=True, help="Path to .canvas file.")
    show_parser.set_defaults(handler=_cmd_canvas_show)


    card_parser = canvas_subparsers.add_parser(
        "card", help="Query card info. Lists all cards if no --card-id given."
    )
    card_parser.add_argument("--file", required=True, help="Path to .canvas file.")
    card_parser.add_argument("--card-id", help="Card to query. Omit to list all.")
    card_parser.add_argument(
        "--text", action="store_true", help="Print only the card text content."
    )
    card_parser.set_defaults(handler=_cmd_canvas_card)


    add_card_parser = canvas_subparsers.add_parser(
        "add-card", help="Add a card to an existing canvas."
    )
    add_card_parser.add_argument("--file", required=True, help="Path to .canvas file.")
    add_card_parser.add_argument(
        "--card-id", required=True, help="ID for the new card."
    )
    add_card_parser.add_argument(
        "--card-type", required=True, help="Type for the new card."
    )
    add_card_parser.add_argument("--connect-to", help="Existing card to connect to.")
    add_card_parser.add_argument("--edge-id", help="Edge ID for the connection.")
    add_card_parser.set_defaults(handler=_cmd_canvas_add_card)


    add_edge_parser = canvas_subparsers.add_parser(
        "add-edge", help="Add a relationship between existing cards."
    )
    add_edge_parser.add_argument("--file", required=True, help="Path to .canvas file.")
    add_edge_parser.add_argument(
        "--from", dest="from_card", required=True, help="Source card ID."
    )
    add_edge_parser.add_argument(
        "--to", dest="to_card", required=True, help="Target card ID."
    )
    add_edge_parser.add_argument("--edge-id", required=True, help="Relationship ID.")
    add_edge_parser.add_argument(
        "--rel-type",
        default="edge",
        help="Relationship type (edge, adjacent, contains). Default: edge.",
    )
    add_edge_parser.set_defaults(handler=_cmd_canvas_add_edge)


    render_parser = canvas_subparsers.add_parser(
        "render", help="Compile model into canvas. Dry run by default."
    )
    render_parser.add_argument("--file", required=True, help="Path to .canvas file.")
    render_parser.add_argument(
        "--apply", action="store_true", help="Write the rendered canvas to disk."
    )
    render_parser.set_defaults(handler=_cmd_canvas_render)
