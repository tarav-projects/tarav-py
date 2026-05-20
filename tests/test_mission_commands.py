from __future__ import annotations

import json
from pathlib import Path

from agentos.cli import main as _agentos_main
from _helpers import captured_json


def main(argv: list[str]) -> int:
    if argv and argv[0] == "mission" and "--project" not in argv:
        return _agentos_main([*argv, "--project"])
    return _agentos_main(argv)


def _init_project(tmp_path: Path, monkeypatch, capsys) -> None:
    assert main(["init", "--scope", "project", "--project", str(tmp_path)]) == 0
    capsys.readouterr()
    monkeypatch.chdir(tmp_path)


def _patch_mission_times(monkeypatch, values: list[str]) -> None:
    iterator = iter(values)
    monkeypatch.setattr("agentos.mission.core.utc_now_iso", lambda: next(iterator))


def _load_mission(tmp_path: Path, name: str) -> dict:
    mission_path = tmp_path / ".agentos" / "missions" / f"{name}.mission.json"
    return json.loads(mission_path.read_text(encoding="utf-8"))


def test_mission_defaults_to_most_recent_active_and_no_active_file_is_created(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)
    _patch_mission_times(
        monkeypatch,
        [
            "2026-04-14T00:00:01Z",
            "2026-04-14T00:00:02Z",
            "2026-04-14T00:00:03Z",
        ],
    )

    assert main(["mission", "new", "alpha", "--goal", "Alpha", "--validation", "Alpha check"]) == 0
    capsys.readouterr()
    assert main(["mission", "new", "beta", "--goal", "Beta", "--validation", "Beta check"]) == 0
    capsys.readouterr()

    assert main(["mission", "todo", "add", "default todo"]) == 0
    stdout = capsys.readouterr().out
    assert "added todo #1 to beta" in stdout

    beta = _load_mission(tmp_path, "beta")
    assert beta["todos"] == [{"text": "default todo", "done": False}]
    assert beta["last_activity"] == "2026-04-14T00:00:03Z"

    active_path = tmp_path / ".agentos" / "missions" / "_active.json"
    assert not active_path.exists()

    assert main(["mission", "list", "--json"]) == 0
    payload = captured_json(capsys)
    assert payload["default"] == "beta"
    assert [mission["name"] for mission in payload["missions"][:2]] == ["beta", "alpha"]


def test_mission_requires_explicit_project(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)

    assert _agentos_main(["mission", "list"]) == 1
    assert "agentos mission requires --project or --project-base" in capsys.readouterr().err


def test_mission_accepts_project_base(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)

    assert _agentos_main(["mission", "list", "--project-base", tmp_path.name, "--json"]) == 0
    payload = captured_json(capsys)
    assert payload["missions"] == []


def test_mission_activate_bumps_recency_and_reopens_parked_mission(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)
    _patch_mission_times(
        monkeypatch,
        [
            "2026-04-14T00:00:01Z",
            "2026-04-14T00:00:02Z",
            "2026-04-14T00:00:03Z",
            "2026-04-14T00:00:04Z",
            "2026-04-14T00:00:05Z",
        ],
    )

    assert main(["mission", "new", "alpha", "--goal", "Alpha", "--validation", "Alpha check"]) == 0
    capsys.readouterr()
    assert main(["mission", "new", "beta", "--goal", "Beta", "--validation", "Beta check"]) == 0
    capsys.readouterr()
    assert main(["mission", "park", "alpha"]) == 0
    capsys.readouterr()

    assert main(["mission", "activate", "alpha"]) == 0
    assert "mission activated: alpha" in capsys.readouterr().out

    assert main(["mission", "note", "focused note"]) == 0
    assert "noted on alpha" in capsys.readouterr().out

    alpha = _load_mission(tmp_path, "alpha")
    assert alpha["status"] == "active"
    assert alpha["notes"] == ["focused note"]
    assert alpha["last_activity"] == "2026-04-14T00:00:05Z"

    assert main(["mission", "list"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "active (most recent first):"
    assert lines[1].startswith("  alpha  (default)")
    assert "[last 2026-04-14T00:00:05Z]" in lines[1]
    assert lines[2].startswith("  beta")
    assert "[last 2026-04-14T00:00:02Z]" in lines[2]


def test_mission_default_skips_parked_missions(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)
    _patch_mission_times(
        monkeypatch,
        [
            "2026-04-14T00:00:01Z",
            "2026-04-14T00:00:02Z",
            "2026-04-14T00:00:03Z",
            "2026-04-14T00:00:04Z",
            "2026-04-14T00:00:05Z",
        ],
    )

    assert main(["mission", "new", "alpha", "--goal", "Alpha", "--validation", "Alpha check"]) == 0
    capsys.readouterr()
    assert main(["mission", "new", "beta", "--goal", "Beta", "--validation", "Beta check"]) == 0
    capsys.readouterr()
    assert main(["mission", "activate", "alpha"]) == 0
    capsys.readouterr()
    assert main(["mission", "park"]) == 0
    capsys.readouterr()

    assert main(["mission", "note", "beta note"]) == 0
    assert "noted on beta" in capsys.readouterr().out

    beta = _load_mission(tmp_path, "beta")
    assert beta["notes"] == ["beta note"]
    assert beta["last_activity"] == "2026-04-14T00:00:05Z"


def test_mission_errors_when_no_recent_active_mission_exists(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _init_project(tmp_path, monkeypatch, capsys)
    _patch_mission_times(
        monkeypatch,
        [
            "2026-04-14T00:00:01Z",
            "2026-04-14T00:00:02Z",
        ],
    )

    assert main(["mission", "new", "alpha", "--goal", "Alpha", "--validation", "Alpha check"]) == 0
    capsys.readouterr()
    assert main(["mission", "park", "alpha"]) == 0
    capsys.readouterr()

    assert main(["mission", "note", "should fail"]) == 1
    stderr = capsys.readouterr().err
    assert "no mission specified and no recent active mission found" in stderr
