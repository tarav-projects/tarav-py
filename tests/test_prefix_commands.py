from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli import main
from _helpers import set_fake_agentos_home
from _helpers import write_text_file


def _init_project(root: Path, monkeypatch, capsys) -> None:
    set_fake_agentos_home(monkeypatch, root / "agentos-home")
    assert main(["init", "--scope", "project", "--project", str(root)]) == 0
    capsys.readouterr()
    monkeypatch.chdir(root)


def _prefix_next_args(project: Path | None, project_base: str, target: str) -> list[str]:
    args = ["stdlib", "prefix", "next"]
    if project is not None:
        args.extend(["--project", str(project)])
    args.extend(["--project-base", project_base, "--target", target])
    return args


def test_prefix_next_allocates_rolling_prefix_across_project_scope(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)
    write_text_file(tmp_path / "notes" / "live" / "500-session.md", "")
    write_text_file(tmp_path / "dev" / "live" / "501-probe.py", "")
    write_text_file(tmp_path / "notes" / "index" / "100-index-note.md", "")
    write_text_file(tmp_path / "notes" / "live" / "010.TODOS.md", "")

    assert main(_prefix_next_args(None, tmp_path.name, "notes/live")) == 0

    assert capsys.readouterr().out.strip() == "502"


def test_prefix_next_allocates_index_prefix_from_index_range(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)
    write_text_file(tmp_path / "notes" / "index" / "100-Agentos.Index.Notes.md", "")
    write_text_file(tmp_path / "notes" / "live" / "500-session.md", "")

    assert main(_prefix_next_args(None, tmp_path.name, "notes/index")) == 0

    assert capsys.readouterr().out.strip() == "101"


def test_prefix_next_uses_longest_prefix_route_for_descendants(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)
    write_text_file(tmp_path / "notes" / "index" / "100-root.md", "")

    assert main(_prefix_next_args(None, tmp_path.name, "notes/index/archive")) == 0

    assert capsys.readouterr().out.strip() == "101"


def test_prefix_next_project_option_resolves_explicit_project(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "project"
    other_root = tmp_path / "other"
    project_root.mkdir()
    other_root.mkdir()
    _init_project(project_root, monkeypatch, capsys)
    write_text_file(project_root / "notes" / "live" / "500-session.md", "")
    monkeypatch.chdir(other_root)

    assert main(_prefix_next_args(project_root, project_root.name, "notes/live")) == 0

    assert capsys.readouterr().out.strip() == "501"


def test_prefix_next_bare_project_targets_current_directory(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)
    write_text_file(tmp_path / "notes" / "live" / "500-session.md", "")

    assert main(_prefix_next_args(None, tmp_path.name, "notes/live")) == 0

    assert capsys.readouterr().out.strip() == "501"


def test_prefix_next_project_base_assertion_matches_root_basename_with_discovery(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "named-project"
    project_root.mkdir()
    _init_project(project_root, monkeypatch, capsys)

    assert main(_prefix_next_args(None, "named-project", "notes/live")) == 0

    assert capsys.readouterr().out.strip() == "500"


def test_prefix_next_project_base_assertion_ignores_marker_name(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "basename-project"
    project_root.mkdir()
    set_fake_agentos_home(monkeypatch, tmp_path / "agentos-home")
    assert main(
        [
            "init",
            "--project",
            str(project_root),
            "--project-name",
            "declared-name",
        ]
    ) == 0
    capsys.readouterr()
    monkeypatch.chdir(project_root)

    assert main(_prefix_next_args(None, "basename-project", "notes/live")) == 0

    assert capsys.readouterr().out.strip() == "500"


def test_prefix_next_project_base_assertion_fails_on_mismatch(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)

    assert main(_prefix_next_args(None, "other-project", "notes/live")) == 1

    assert "project base assertion failed" in capsys.readouterr().err


def test_prefix_next_combines_project_path_with_project_base_assertion(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "path-project"
    other_root = tmp_path / "other"
    project_root.mkdir()
    other_root.mkdir()
    _init_project(project_root, monkeypatch, capsys)
    monkeypatch.chdir(other_root)

    assert main(_prefix_next_args(project_root, "path-project", "notes/live")) == 0

    assert capsys.readouterr().out.strip() == "500"


def test_prefix_next_explicit_project_without_target_fails(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _init_project(project_root, monkeypatch, capsys)

    with pytest.raises(SystemExit) as excinfo:
        main(["stdlib", "prefix", "next", "--project", str(project_root), "--project-base", project_root.name])

    assert excinfo.value.code == 2
    assert "the following arguments are required: --target" in capsys.readouterr().err


def test_prefix_next_requires_project_base(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)

    with pytest.raises(SystemExit) as excinfo:
        main(["stdlib", "prefix", "next", "--target", "notes/live"])

    assert excinfo.value.code == 2
    assert "the following arguments are required: --project-base" in capsys.readouterr().err

    with pytest.raises(SystemExit) as excinfo:
        main(["stdlib", "prefix", "next", "--project", "--target", "notes/live"])

    assert excinfo.value.code == 2
    assert "the following arguments are required: --project-base" in capsys.readouterr().err


def test_prefix_next_requires_existing_project_for_target_mode(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(_prefix_next_args(None, tmp_path.name, "notes/live")) == 1

    assert "not inside an agentos project" in capsys.readouterr().err


def test_prefix_next_rejects_absolute_target(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)

    assert main(_prefix_next_args(None, tmp_path.name, str(tmp_path / "notes" / "live"))) == 1

    assert capsys.readouterr().err.strip() == (
        "error: prefix target must be relative to the agentos project root"
    )


def test_prefix_next_rejects_target_that_escapes_project(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)

    assert main(_prefix_next_args(None, tmp_path.name, "../outside")) == 1

    assert capsys.readouterr().err.strip() == "error: prefix target escapes project root: ../outside"


def test_prefix_next_rejects_custom_prefix_config(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)
    config_path = tmp_path / ".agentos" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["prefix"] = {"scan": {}}
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    assert main(_prefix_next_args(None, tmp_path.name, "notes/live")) == 1

    assert capsys.readouterr().err.strip() == (
        "error: custom project prefix config is not supported yet"
    )


def test_prefix_next_missing_default_include_roots_are_ignored(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)

    assert main(_prefix_next_args(None, tmp_path.name, "notes/live")) == 0

    assert capsys.readouterr().out.strip() == "500"


def test_prefix_next_include_override_limits_project_scope(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)
    write_text_file(tmp_path / "notes" / "live" / "500-session.md", "")
    write_text_file(tmp_path / "dev" / "live" / "501-probe.py", "")

    assert main(_prefix_next_args(None, tmp_path.name, "notes/live") + ["--include", "notes/live"]) == 0

    assert capsys.readouterr().out.strip() == "501"


def test_prefix_next_exclude_filters_project_scope(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)
    write_text_file(tmp_path / "notes" / "live" / "500-session.md", "")
    write_text_file(tmp_path / "dev" / "live" / "501-probe.py", "")

    assert main(_prefix_next_args(None, tmp_path.name, "notes/live") + ["--exclude", "dev/live"]) == 0

    assert capsys.readouterr().out.strip() == "501"


def test_prefix_next_json_reports_project_metadata(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)
    write_text_file(tmp_path / "notes" / "live" / "500-session.md", "")
    write_text_file(tmp_path / "notes" / "live" / "010.TODOS.md", "")

    assert main(_prefix_next_args(None, tmp_path.name, "notes/live") + ["--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["next_prefix"] == "501"
    assert payload["next_value"] == 501
    assert payload["project_root"] == str(tmp_path)
    assert payload["target"] == "notes/live"
    assert payload["route"] == "*"
    assert payload["range"] == [500, 999]
    assert payload["scan"]["includes"] == ["notes", "dev/live"]
    assert ".git" in payload["scan"]["excludes"]
    assert payload["matched_prefix_count"] == 1
    assert payload["reserved_prefix_count"] == 1
    assert payload["policy_source"] == "default"
    assert payload["width"] == 3


def test_prefix_next_records_project_command(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)
    monkeypatch.setattr(
        "agentos._core.project_command_log.utc_now_iso",
        lambda: "2026-05-04T10:00:00Z",
    )

    command_argv = _prefix_next_args(None, tmp_path.name, "notes/live")
    assert main(command_argv) == 0
    capsys.readouterr()

    log_path = tmp_path / "agentos-home" / ".agentos" / "projects" / "activity" / "202605.jsonl"
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    project_marker = json.loads((tmp_path / ".agentos" / "project.json").read_text(encoding="utf-8"))
    assert events == [
        {
            "schema_version": 1,
            "timetag": "2026-05-04T10:00:00Z",
            "project_id": project_marker["project_id"],
            "project_root": str(tmp_path),
            "agentos_command": {
                "command": "stdlib prefix next",
                "argv": command_argv,
            },
        }
    ]


def test_prefix_next_fails_when_range_is_exhausted(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)
    write_text_file(tmp_path / "notes" / "live" / "999-last.md", "")

    assert main(_prefix_next_args(None, tmp_path.name, "notes/live")) == 1

    assert "prefix range exhausted" in capsys.readouterr().err


def test_prefix_next_rejects_legacy_scanner_mode(capsys, tmp_path: Path) -> None:
    write_text_file(tmp_path / "notes" / "live" / "500-session.md", "")

    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "stdlib",
                "prefix",
                "next",
                "--project-base",
                tmp_path.name,
                "--target",
                "notes/live",
                "--root",
                str(tmp_path),
                "--include",
                "notes/live",
                "--min",
                "500",
                "--width",
                "3",
            ]
        )

    assert excinfo.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err
