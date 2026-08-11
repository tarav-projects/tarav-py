from __future__ import annotations

import pytest

from agentos.cli.cli import build_parser


def test_index_line_manifest_is_the_canonical_command_surface() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "index",
            "line",
            "manifest",
            "show",
            "--depot",
            "skills/agentos-pkg",
            "--anchor",
            "c20260809-171u",
            "--verification",
            "sampled",
            "--verification-sample",
            "2",
            "--neighbors",
            "3",
            "--detail",
            "reference",
            "--json",
        ]
    )

    assert args.index_command == "line"
    assert args.index_line_command == "manifest"
    assert args.index_line_manifest_command == "show"
    assert args.verification == "sampled"
    assert args.verification_sample == 2
    assert args.neighbors == 3


def test_chatlas_line_manifest_route_is_removed() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["chatlas", "line", "manifest", "show"])
