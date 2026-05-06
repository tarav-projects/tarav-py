"""CLI commands for agentos canvas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentos._core.errors import CliError

from .core import (
    LintError,
    TopologyEdge,
    Topology,
    canvas_to_topology,
    lint_canvas,
    parse_topology,
    place_one,
    read_canvas,
    topology_to_canvas,
    topology_to_dict,
    write_canvas,
    _make_node_text,
    _short_id,
    NODE_WIDTH,
    NODE_HEIGHT,
)


def _cmd_canvas_init(args: argparse.Namespace) -> int:
    topology_path = Path(args.topology)
    if not topology_path.exists():
        raise CliError(f"topology file not found: {topology_path}")

    data = json.loads(topology_path.read_text(encoding="utf-8"))
    topo = parse_topology(data)
    canvas = topology_to_canvas(topo)

    out_path = Path(args.file)
    write_canvas(out_path, canvas)
    print(f"Created {out_path} ({len(topo.nodes)} nodes, {len(topo.edges)} edges)")
    return 0


def _cmd_canvas_show(args: argparse.Namespace) -> int:
    canvas_path = Path(args.file)
    if not canvas_path.exists():
        raise CliError(f"canvas file not found: {canvas_path}")

    canvas = read_canvas(canvas_path)
    topo = canvas_to_topology(canvas)
    output = topology_to_dict(topo)
    print(json.dumps(output, indent=2))
    return 0


def _cmd_canvas_add_node(args: argparse.Namespace) -> int:
    canvas_path = Path(args.file)
    if not canvas_path.exists():
        raise CliError(f"canvas file not found: {canvas_path}")

    canvas = read_canvas(canvas_path)
    node_id = args.node_id

    # Check if node already exists
    for node in canvas.get("nodes", []):
        if node["id"] == node_id:
            raise CliError(f"node '{node_id}' already exists")

    # Determine connections
    connected_to = []
    if args.connect_to:
        connected_to.append(args.connect_to)

    # Place the node
    x, y = place_one(node_id, canvas, connected_to)

    # Add node
    canvas.setdefault("nodes", []).append(
        {
            "id": node_id,
            "type": "text",
            "text": _make_node_text(node_id),
            "x": int(x),
            "y": int(y),
            "width": NODE_WIDTH,
            "height": NODE_HEIGHT,
        }
    )

    # Add edge if --connect-to and --edge-id provided
    if args.connect_to and args.edge_id:
        canvas.setdefault("edges", []).append(
            {
                "id": _short_id(),
                "fromNode": args.connect_to,
                "toNode": node_id,
                "label": args.edge_id,
            }
        )

    write_canvas(canvas_path, canvas)
    print(f"Added node '{node_id}'")
    return 0


def _cmd_canvas_add_edge(args: argparse.Namespace) -> int:
    canvas_path = Path(args.file)
    if not canvas_path.exists():
        raise CliError(f"canvas file not found: {canvas_path}")

    canvas = read_canvas(canvas_path)

    # Verify both nodes exist
    node_ids = {n["id"] for n in canvas.get("nodes", [])}
    if args.from_node not in node_ids:
        raise CliError(f"node '{args.from_node}' not found")
    if args.to_node not in node_ids:
        raise CliError(f"node '{args.to_node}' not found")

    canvas.setdefault("edges", []).append(
        {
            "id": _short_id(),
            "fromNode": args.from_node,
            "toNode": args.to_node,
            "label": args.edge_id,
        }
    )

    write_canvas(canvas_path, canvas)
    print(f"Added edge '{args.edge_id}' ({args.from_node} -> {args.to_node})")
    return 0


def _cmd_canvas_place(args: argparse.Namespace) -> int:
    canvas_path = Path(args.file)
    if not canvas_path.exists():
        raise CliError(f"canvas file not found: {canvas_path}")

    canvas = read_canvas(canvas_path)
    node_id = args.node_id

    # Find the node
    target_node = None
    for node in canvas.get("nodes", []):
        if node["id"] == node_id:
            target_node = node
            break

    if target_node is None:
        raise CliError(f"node '{node_id}' not found")

    # Find connected neighbors
    connected_to = []
    for edge in canvas.get("edges", []):
        if edge.get("fromNode") == node_id:
            connected_to.append(edge["toNode"])
        elif edge.get("toNode") == node_id:
            connected_to.append(edge["fromNode"])

    x, y = place_one(node_id, canvas, connected_to)
    target_node["x"] = int(x)
    target_node["y"] = int(y)

    write_canvas(canvas_path, canvas)
    print(f"Placed node '{node_id}' at ({int(x)}, {int(y)})")
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
        print(f"[rule {err.rule}] {err.message}", file=sys.stderr)
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
    init_parser.add_argument("--topology", required=True, help="Path to topology JSON file.")
    init_parser.add_argument("--file", required=True, help="Output .canvas file path.")
    init_parser.set_defaults(handler=_cmd_canvas_init)

    # show
    show_parser = canvas_subparsers.add_parser(
        "show", help="Print canvas topology as JSON."
    )
    show_parser.add_argument("--file", required=True, help="Path to .canvas file.")
    show_parser.set_defaults(handler=_cmd_canvas_show)

    # add-node
    add_node_parser = canvas_subparsers.add_parser(
        "add-node", help="Add a node to an existing canvas."
    )
    add_node_parser.add_argument("--file", required=True, help="Path to .canvas file.")
    add_node_parser.add_argument("--node-id", required=True, help="ID for the new node.")
    add_node_parser.add_argument("--connect-to", help="Existing node to connect to.")
    add_node_parser.add_argument("--edge-id", help="Edge ID for the connection.")
    add_node_parser.set_defaults(handler=_cmd_canvas_add_node)

    # add-edge
    add_edge_parser = canvas_subparsers.add_parser(
        "add-edge", help="Add an edge between existing nodes."
    )
    add_edge_parser.add_argument("--file", required=True, help="Path to .canvas file.")
    add_edge_parser.add_argument("--from", dest="from_node", required=True, help="Source node ID.")
    add_edge_parser.add_argument("--to", dest="to_node", required=True, help="Target node ID.")
    add_edge_parser.add_argument("--edge-id", required=True, help="Edge ID (label).")
    add_edge_parser.set_defaults(handler=_cmd_canvas_add_edge)

    # place
    place_parser = canvas_subparsers.add_parser(
        "place", help="Reposition a node near its neighbors."
    )
    place_parser.add_argument("--file", required=True, help="Path to .canvas file.")
    place_parser.add_argument("--node-id", required=True, help="Node to reposition.")
    place_parser.set_defaults(handler=_cmd_canvas_place)

    # lint
    lint_parser = canvas_subparsers.add_parser(
        "lint", help="Validate canvas against Graph.Model rules."
    )
    lint_parser.add_argument("--file", required=True, help="Path to .canvas file.")
    lint_parser.set_defaults(handler=_cmd_canvas_lint)
