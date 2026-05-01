from __future__ import annotations

import json
from pathlib import Path

from _helpers import set_fake_agentos_home as _set_fake_agentos_home
from agentos.cli import main


def test_tmp_folder_new_returns_path_without_creating_directory(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    assert main(["init", "--scope", "project", "--project", str(tmp_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path)
    assert main(["utils", "tmp-folder", "new"]) == 0
    out = capsys.readouterr().out.strip()

    generated_path = Path(out)
    expected_parent = (tmp_path / ".agentos" / "tmp").resolve()
    assert generated_path.is_absolute()
    assert generated_path.parent == expected_parent
    assert not generated_path.exists()
    assert expected_parent.is_dir()

    log_paths = sorted((agentos_home / "projects" / "activity").glob("*.jsonl"))
    assert len(log_paths) == 1
    event = json.loads(log_paths[0].read_text(encoding="utf-8").splitlines()[0])
    marker = json.loads((tmp_path / ".agentos" / "project.json").read_text(encoding="utf-8"))
    assert event["project_id"] == marker["project_id"]
    assert event["project_root"] == str(tmp_path.resolve())
    assert event["agentos_command"] == {
        "command": "utils tmp-folder new",
        "argv": ["utils", "tmp-folder", "new"],
    }


def test_tmp_folder_new_returns_distinct_paths_per_call(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    assert main(["init", "--scope", "project", "--project", str(tmp_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path)
    assert main(["utils", "tmp-folder", "new"]) == 0
    first = Path(capsys.readouterr().out.strip())

    assert main(["utils", "tmp-folder", "new"]) == 0
    second = Path(capsys.readouterr().out.strip())

    assert first != second
    assert not first.exists()
    assert not second.exists()


def test_tmp_folder_new_with_create_creates_directory_under_project_tmp(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    assert main(["init", "--scope", "project", "--project", str(tmp_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path)
    assert main(["utils", "tmp-folder", "new", "--create"]) == 0
    out = capsys.readouterr().out.strip()

    created_path = Path(out)
    expected_parent = (tmp_path / ".agentos" / "tmp").resolve()
    assert created_path.is_absolute()
    assert created_path.is_dir()
    assert created_path.parent == expected_parent


def test_tmp_folder_new_requires_agentos_project(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    monkeypatch.chdir(tmp_path)

    assert main(["utils", "tmp-folder", "new"]) == 1
    stderr = capsys.readouterr().err
    assert "not inside an agentos project" in stderr
