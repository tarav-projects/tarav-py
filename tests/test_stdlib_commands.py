from __future__ import annotations

import pytest

from agentos._core.project_command_log import command_payload_from_args
from agentos.cli import build_parser, main


def test_top_level_help_shows_stdlib_not_moved_commands() -> None:
    help_text = build_parser().format_help()

    assert "stdlib" in help_text
    assert "mdblocks" not in help_text
    assert "prefix" not in help_text
    assert "git-refs" not in help_text
    assert "utils" not in help_text


def test_stdlib_help_lists_grouped_commands(capsys) -> None:
    with pytest.raises(SystemExit, match="0"):
        main(["stdlib", "--help"])

    help_text = capsys.readouterr().out
    assert "mdblocks" in help_text
    assert "prefix" in help_text
    assert "git-refs" in help_text
    assert "utils" in help_text


@pytest.mark.parametrize("command", ["mdblocks", "prefix", "git-refs", "utils"])
def test_moved_top_level_commands_fail_before_dispatch(command: str, capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([command, "--help"])

    assert excinfo.value.code == 2
    assert f"invalid choice: '{command}'" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "expected_command"),
    [
        (["stdlib", "mdblocks", "lint", "."], "stdlib mdblocks lint"),
        (["stdlib", "prefix", "next"], "stdlib prefix next"),
        (["stdlib", "git-refs", "repo-hash"], "stdlib git-refs repo-hash"),
        (["stdlib", "utils", "tmp-folder", "new"], "stdlib utils tmp-folder new"),
        (["stdlib", "utils", "cmd-logger", "path"], "stdlib utils cmd-logger path"),
    ],
)
def test_stdlib_command_payload_includes_full_nested_path(
    argv: list[str],
    expected_command: str,
) -> None:
    args = build_parser().parse_args(argv)
    args._agentos_argv = argv

    assert command_payload_from_args(args) == {
        "command": expected_command,
        "argv": argv,
    }
