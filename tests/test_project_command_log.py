from __future__ import annotations

import json
from pathlib import Path

from _helpers import set_fake_agentos_home as _set_fake_agentos_home
from _helpers import write_project_marker as _write_project_marker
from agentos._core.project import AgentosProjectHandler
from agentos._core.project_command_log import (
    project_command_log_path,
    record_project_command,
)
from agentos.cli import main


def test_project_command_log_path_rolls_by_year_month(monkeypatch, tmp_path: Path) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")

    assert project_command_log_path(timetag="2026-04-30T12:00:00Z") == (
        agentos_home / "projects" / "activity" / "202604.jsonl"
    )
    assert project_command_log_path(timetag="2026-05-01T00:00:00Z") == (
        agentos_home / "projects" / "activity" / "202605.jsonl"
    )


def test_record_project_command_appends_event(monkeypatch, tmp_path: Path) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    monkeypatch.setattr(
        "agentos._core.project_command_log.utc_now_iso",
        lambda: "2026-04-30T12:00:00Z",
    )
    project_root = tmp_path / "workspace"
    _write_project_marker(project_root)
    project = AgentosProjectHandler(project_root).validate()

    record_project_command(
        project=project,
        agentos_command={
            "command": "skills import",
            "argv": ["skills", "import", "--force"],
        },
    )

    log_path = agentos_home / "projects" / "activity" / "202604.jsonl"
    events = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert events == [
        {
            "schema_version": 1,
            "timetag": "2026-04-30T12:00:00Z",
            "project_id": "00000000-0000-4000-8000-000000000001",
            "project_root": str(project_root.resolve()),
            "agentos_command": {
                "command": "skills import",
                "argv": ["skills", "import", "--force"],
            },
        }
    ]


def test_record_project_command_is_best_effort_after_project_validation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    project_root = tmp_path / "workspace"
    _write_project_marker(project_root)
    project = AgentosProjectHandler(project_root).validate()

    def fail_open(*args, **kwargs):
        raise OSError("cannot write")

    monkeypatch.setattr(Path, "open", fail_open)

    record_project_command(
        project=project,
        agentos_command={"command": "skills list", "argv": ["skills", "list"]},
    )


def _read_logged_commands(agentos_home: Path) -> list[dict[str, object]]:
    log_paths = sorted((agentos_home / "projects" / "activity").glob("*.jsonl"))
    return [
        json.loads(line)
        for path in log_paths
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def test_mission_mutation_records_project_command(monkeypatch, tmp_path: Path, capsys) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    assert main(["init", "--project", str(tmp_path)]) == 0
    capsys.readouterr()

    assert main(
        [
            "mission",
            "new",
            "alpha",
            "--project",
            str(tmp_path),
            "--goal",
            "Alpha",
            "--validation",
            "Alpha check",
        ]
    ) == 0
    capsys.readouterr()

    commands = [event["agentos_command"]["command"] for event in _read_logged_commands(agentos_home)]
    assert "mission new" in commands


def test_forum_write_records_project_command(monkeypatch, tmp_path: Path, capsys) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    assert main(["init", "--project", str(tmp_path)]) == 0
    capsys.readouterr()

    assert main(["forum", "post", "--project", str(tmp_path), "Hello"]) == 0
    capsys.readouterr()

    commands = [event["agentos_command"]["command"] for event in _read_logged_commands(agentos_home)]
    assert "forum post" in commands


def test_project_tape_mode_records_project_command(monkeypatch, tmp_path: Path, capsys) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    assert main(["init", "--project", str(tmp_path)]) == 0
    capsys.readouterr()

    assert main(["tape", "init", "--project", str(tmp_path), "--tape", "events"]) == 0
    capsys.readouterr()

    commands = [event["agentos_command"]["command"] for event in _read_logged_commands(agentos_home)]
    assert "tape init" in commands
