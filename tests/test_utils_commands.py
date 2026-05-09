from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from _helpers import set_fake_agentos_home as _set_fake_agentos_home
from _helpers import write_project_marker as _write_project_marker
from agentos.cli import main


def _assert_valid_uuid(text: str) -> None:
    parsed = UUID(text)
    assert str(parsed) == text


def _write_cmd_logger_events(agentos_home: Path, events: list[dict[str, object]]) -> Path:
    log_path = agentos_home / "projects" / "activity" / "202605.jsonl"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )
    return log_path


def _cmd_logger_event(
    *,
    timetag: str,
    project_id: str,
    project_root: Path | str,
    command: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "timetag": timetag,
        "project_id": project_id,
        "project_root": str(project_root),
        "agentos_command": {"command": command, "argv": []},
    }


def test_utils_uuid_default_outputs_single_uuid(capsys) -> None:
    assert main(["utils", "uuid"]) == 0
    out = capsys.readouterr().out.strip()
    assert out
    _assert_valid_uuid(out)


def test_utils_uuid_count_outputs_multiple_lines(capsys) -> None:
    assert main(["utils", "uuid", "--count", "3"]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 3
    for line in lines:
        _assert_valid_uuid(line)


def test_utils_uuid_json_outputs_payload(capsys) -> None:
    assert main(["utils", "uuid", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "utils uuid"
    assert payload["count"] == 1
    assert isinstance(payload["uuids"], list)
    assert len(payload["uuids"]) == 1
    _assert_valid_uuid(payload["uuid"])
    _assert_valid_uuid(payload["uuids"][0])


def test_utils_cmd_logger_path_uses_month(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")

    assert main(["utils", "cmd-logger", "path", "--month", "202605"]) == 0

    assert capsys.readouterr().out.strip() == str(
        agentos_home / "projects" / "activity" / "202605.jsonl"
    )


def test_utils_cmd_logger_tail_outputs_recent_events(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    _write_cmd_logger_events(
        agentos_home,
        [
            _cmd_logger_event(
                timetag="2026-05-01T00:00:00Z",
                project_id="project-1",
                project_root="/tmp/project-1",
                command="skills list",
            ),
            _cmd_logger_event(
                timetag="2026-05-02T00:00:00Z",
                project_id="project-2",
                project_root="/tmp/project-2",
                command="mission new",
            ),
        ],
    )

    assert (
        main(
            [
                "utils",
                "cmd-logger",
                "tail",
                "--month",
                "202605",
                "--limit",
                "1",
            ]
        )
        == 0
    )

    assert capsys.readouterr().out == (
        "2026-05-02T00:00:00Z\tproject-2\tmission new\t/tmp/project-2\n"
    )


def test_utils_cmd_logger_query_filters_under_path_and_valid_project(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    valid_project = workspace / "valid"
    non_project = workspace / "plain"
    outside_project = tmp_path / "outside"
    valid_project.mkdir(parents=True)
    non_project.mkdir()
    outside_project.mkdir()
    _write_project_marker(valid_project)
    _write_project_marker(outside_project)
    _write_cmd_logger_events(
        agentos_home,
        [
            _cmd_logger_event(
                timetag="2026-05-01T00:00:00Z",
                project_id="valid-id",
                project_root=valid_project,
                command="skills list",
            ),
            _cmd_logger_event(
                timetag="2026-05-02T00:00:00Z",
                project_id="plain-id",
                project_root=non_project,
                command="mission new",
            ),
            _cmd_logger_event(
                timetag="2026-05-03T00:00:00Z",
                project_id="outside-id",
                project_root=outside_project,
                command="forum post",
            ),
        ],
    )

    assert (
        main(
            [
                "utils",
                "cmd-logger",
                "query",
                "--month",
                "202605",
                "--under",
                str(workspace),
                "--valid-project",
                "yes",
            ]
        )
        == 0
    )

    assert capsys.readouterr().out == (
        f"2026-05-01T00:00:00Z\tvalid-id\tyes\tyes\tskills list\t{valid_project}\n"
    )


def test_utils_cmd_logger_query_filters_missing_project_roots(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    existing_project = tmp_path / "existing"
    missing_project = tmp_path / "missing"
    existing_project.mkdir()
    _write_project_marker(existing_project)
    _write_cmd_logger_events(
        agentos_home,
        [
            _cmd_logger_event(
                timetag="2026-05-01T00:00:00Z",
                project_id="existing-id",
                project_root=existing_project,
                command="skills list",
            ),
            _cmd_logger_event(
                timetag="2026-05-02T00:00:00Z",
                project_id="missing-id",
                project_root=missing_project,
                command="mission new",
            ),
        ],
    )

    assert (
        main(
            [
                "utils",
                "cmd-logger",
                "query",
                "--month",
                "202605",
                "--exists",
                "no",
            ]
        )
        == 0
    )

    assert capsys.readouterr().out == (
        f"2026-05-02T00:00:00Z\tmissing-id\tno\tno\tmission new\t{missing_project}\n"
    )


def test_utils_cmd_logger_query_filters_command_and_outputs_json(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    project = tmp_path / "project"
    project.mkdir()
    _write_project_marker(project)
    _write_cmd_logger_events(
        agentos_home,
        [
            _cmd_logger_event(
                timetag="2026-05-01T00:00:00Z",
                project_id="project-id",
                project_root=project,
                command="skills list",
            ),
            _cmd_logger_event(
                timetag="2026-05-02T00:00:00Z",
                project_id="project-id",
                project_root=project,
                command="mission new",
            ),
        ],
    )

    assert (
        main(
            [
                "utils",
                "cmd-logger",
                "query",
                "--month",
                "202605",
                "--command",
                "mission",
                "--project-id",
                "project-id",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "utils cmd-logger query"
    assert payload["month"] == "202605"
    assert payload["filters"]["command"] == "mission"
    assert payload["filters"]["project_id"] == "project-id"
    assert payload["count"] == 1
    assert payload["events"][0]["agentos_command"]["command"] == "mission new"
    assert payload["events"][0]["project_exists"] is True
    assert payload["events"][0]["valid_project"] is True


def test_utils_cmd_logger_tail_json_outputs_raw_jsonl(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    log_path = agentos_home / "projects" / "activity" / "202605.jsonl"
    log_path.parent.mkdir(parents=True)
    event = {
        "schema_version": 1,
        "timetag": "2026-05-01T00:00:00Z",
        "project_id": "project-1",
        "project_root": "/tmp/project-1",
        "agentos_command": {"command": "skills list", "argv": []},
    }
    log_path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    assert (
        main(
            [
                "utils",
                "cmd-logger",
                "tail",
                "--month",
                "202605",
                "--json",
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out) == event


def test_utils_cmd_logger_rejects_invalid_month(capsys) -> None:
    assert main(["utils", "cmd-logger", "path", "--month", "2026-05"]) == 1

    assert "--month must use YYYYMM format" in capsys.readouterr().err


def test_utils_cmd_logger_tail_rejects_invalid_limit(capsys) -> None:
    assert main(["utils", "cmd-logger", "tail", "--limit", "0"]) == 1

    assert "--limit must be >= 1" in capsys.readouterr().err
