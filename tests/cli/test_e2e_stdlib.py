from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from agentos.testing import AgentosTestEnvironment, write_project_marker
from agentos.cli.cli import build_parser, main
from _helpers import captured_json, read_jsonl_file, write_text_file


def _init_project(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Path:
    environment = AgentosTestEnvironment.create(root / "agentos-home")
    environment.apply_environment(monkeypatch.setenv)
    assert main(["init", "--scope", "project", "--project", str(root)]) == 0
    capsys.readouterr()
    monkeypatch.chdir(root)
    return root


def _activity_event(
    *, timetag: str, project_root: Path | str, command: str
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "timetag": timetag,
        "project_id": "project-id",
        "project_root": str(project_root),
        "agentos_command": {"command": command, "argv": []},
    }


def test_stdlib_routing_and_payloads_are_nested(
    capsys: pytest.CaptureFixture[str],
) -> None:
    help_text = build_parser().format_help()
    assert "stdlib" in help_text
    assert "mdblocks" not in help_text
    assert "future" in help_text
    assert "forum" in help_text

    with pytest.raises(SystemExit) as excinfo:
        main(["prefix", "--help"])
    assert excinfo.value.code == 2
    assert "invalid choice: 'prefix'" in capsys.readouterr().err

    args = build_parser().parse_args(
        ["stdlib", "utils", "tmp-folder", "new", "--project"]
    )
    assert args.command == "stdlib"
    assert args.stdlib_command == "utils"
    assert args.utils_command == "tmp-folder"
    assert args.tmp_folder_command == "new"


def test_prefix_next_allocates_across_project_numbered_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)
    write_text_file(tmp_path / "notes" / "live" / "500-session.md", "")
    write_text_file(tmp_path / "dev" / "live" / "501-probe.py", "")
    write_text_file(tmp_path / "notes" / "index" / "100-index-note.md", "")

    assert (
        main(
            [
                "stdlib",
                "prefix",
                "next",
                "--project-base",
                tmp_path.name,
                "--target",
                "notes/live",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out.strip() == "502"

    assert (
        main(
            [
                "stdlib",
                "prefix",
                "next",
                "--project-base",
                tmp_path.name,
                "--target",
                "notes/index",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out.strip() == "101"

    assert (
        main(
            [
                "stdlib",
                "prefix",
                "next",
                "--project-base",
                "wrong",
                "--target",
                "notes/live",
            ]
        )
        == 1
    )
    assert "project base assertion failed" in capsys.readouterr().err


def test_tmp_folder_new_allocates_project_tmp_and_logs_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path / "home")
    environment.apply_environment(monkeypatch.setenv)
    agentos_home = environment.agentos_home
    assert main(["init", "--scope", "project", "--project", str(tmp_path)]) == 0
    capsys.readouterr()
    monkeypatch.chdir(tmp_path)

    assert main(["stdlib", "utils", "tmp-folder", "new", "--project", "--create"]) == 0
    generated = Path(capsys.readouterr().out.strip())
    assert generated.is_dir()
    assert generated.parent == (tmp_path / ".agentos" / "tmp").resolve()

    log_paths = sorted((agentos_home / "activity").glob("*.jsonl"))
    assert len(log_paths) == 1
    event = read_jsonl_file(log_paths[0])[0]
    assert event["event_type"] == "project.command"
    assert event["command"] == "stdlib utils tmp-folder new"


def test_mdblocks_blocks_find_and_lint_use_line_regions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    md_path = tmp_path / "doc.md"
    write_text_file(
        md_path,
        "\n".join(
            ["****", "## alpha", "payload alpha", "****", "## beta", "payload beta", ""]
        ),
    )

    assert (
        main(
            [
                "stdlib",
                "mdblocks",
                "blocks",
                str(md_path),
                "--root",
                str(tmp_path),
                "--start-line",
                "4",
                "--json",
            ]
        )
        == 0
    )
    blocks = captured_json(capsys)
    assert blocks["block_count"] == 1
    assert blocks["files"][0]["blocks"][0]["title"] == "beta"

    assert (
        main(
            [
                "stdlib",
                "mdblocks",
                "find",
                str(md_path),
                "--root",
                str(tmp_path),
                "--start-line",
                "4",
                "--query",
                "alpha",
                "--json",
            ]
        )
        == 0
    )
    assert captured_json(capsys)["match_count"] == 0

    bad_path = tmp_path / "bad.md"
    write_text_file(bad_path, "****\nplain text\n****\n## valid\nbody\n")
    assert (
        main(
            [
                "stdlib",
                "mdblocks",
                "lint",
                str(bad_path),
                "--root",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
    pois = captured_json(capsys)["pois"]
    assert "Markdown.Block.Linter/Separator.OutsideBlockSemantics" in [
        poi["class"]["address"] for poi in pois
    ]


def test_utils_uuid_outputs_text_and_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["stdlib", "utils", "uuid", "--count", "2"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2
    assert all(str(UUID(line)) == line for line in lines)

    assert main(["stdlib", "utils", "uuid", "--json"]) == 0
    payload = captured_json(capsys)
    assert payload["status"] == "ok"
    assert str(UUID(payload["uuid"])) == payload["uuid"]


def test_cmd_logger_path_tail_and_query_filter_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path / "home")
    environment.apply_environment(monkeypatch.setenv)
    agentos_home = environment.agentos_home
    project = tmp_path / "project"
    project.mkdir()
    write_project_marker(project)
    log_path = agentos_home / "activity" / "202605.jsonl"
    write_text_file(
        log_path,
        "\n".join(
            [
                json.dumps(
                    _activity_event(
                        timetag="2026-05-01T00:00:00Z",
                        project_root=project,
                        command="skills list",
                    )
                ),
                json.dumps(
                    _activity_event(
                        timetag="2026-05-02T00:00:00Z",
                        project_root=project,
                        command="mission new",
                    )
                ),
                json.dumps(
                    {
                        "schema_version": 2,
                        "timetag": "2026-05-03T00:00:00Z",
                        "event_type": "agent.accounts.link",
                        "command": "agent accounts link",
                        "argv": [],
                        "status": "ok",
                        "payload": {"provider": "codex"},
                    }
                ),
            ]
        )
        + "\n",
    )

    assert main(["stdlib", "utils", "cmd-logger", "path", "--month", "202605"]) == 0
    assert capsys.readouterr().out.strip() == str(log_path)

    assert (
        main(
            [
                "stdlib",
                "utils",
                "cmd-logger",
                "tail",
                "--month",
                "202605",
                "--limit",
                "1",
                "--json",
            ]
        )
        == 0
    )
    assert captured_json(capsys)["event_type"] == "agent.accounts.link"

    assert (
        main(
            [
                "stdlib",
                "utils",
                "cmd-logger",
                "query",
                "--month",
                "202605",
                "--event-type",
                "agent.accounts.link",
                "--json",
            ]
        )
        == 0
    )
    payload = captured_json(capsys)
    assert payload["count"] == 1
    assert payload["events"][0]["event_type"] == "agent.accounts.link"


def test_stdlib_validation_errors_are_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["stdlib", "utils", "tmp-folder", "new", "--project"]) == 1
    assert "not inside an agentos project" in capsys.readouterr().err

    assert main(["stdlib", "utils", "cmd-logger", "path", "--month", "2026-05"]) == 1
    assert "--month must use YYYYMM format" in capsys.readouterr().err

    with pytest.raises(SystemExit) as excinfo:
        main(["stdlib", "prefix", "next", "--target", "notes/live"])
    assert excinfo.value.code == 2
    assert (
        "the following arguments are required: --project-base"
        in capsys.readouterr().err
    )
