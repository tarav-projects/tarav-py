from __future__ import annotations

from agentos.cli import build_parser


def test_agentos_registers_canvas_commands() -> None:
    parser = build_parser()

    args = parser.parse_args(["canvas", "render", "--file", "graph.canvas"])

    assert args.command == "canvas"
    assert args.canvas_command == "render"
