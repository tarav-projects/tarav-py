from __future__ import annotations

import pytest

from tarav.cli.cli import build_parser, main


def test_reference_namespace_exposes_wayfinder_operations() -> None:
    parser = build_parser()

    assert parser.parse_args(
        ["reference", "register", "--root-json", "{}", "--path", "."]
    ).reference_command == "register"
    assert parser.parse_args(
        ["reference", "resolve", "block://project/block"]
    ).reference_command == "resolve"
    assert parser.parse_args(["reference", "check"]).reference_command == "check"


def test_legacy_wayfinder_command_is_absent(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["wayfinder"])

    assert excinfo.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_legacy_top_level_hook_command_is_absent(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["hook", "--name", "event", "--ctx", "{}"])

    assert excinfo.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
