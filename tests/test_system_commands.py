from __future__ import annotations

import json
from pathlib import Path

from agentos.cli import main
from _helpers import write_project_marker as _write_project_marker, write_text_file as _write


def test_doctor_supports_explicit_project_target(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "project"
    workspace = tmp_path / "workspace"
    project_root.mkdir()
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    _write_project_marker(project_root)

    assert main(["doctor", "--project", str(project_root)]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["cwd"] == str(workspace.resolve())
    assert payload["project_target"] == str(project_root.resolve())
    assert payload["inside_agentos_project"] is True
    assert payload["project_root"] == str(project_root.resolve())
    assert payload["effective_scope"] == "project"
    assert payload["effective_project_root"] == str(project_root.resolve())
    assert "tapes" not in payload["project_paths"]
    assert "tapes" not in payload["global_paths"]
    assert "effective_tapes_dir" not in payload


def test_init_project_storage_dirs_exclude_legacy_tapes(
    tmp_path: Path,
    capsys,
) -> None:
    assert main(["init", "--project", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert sorted(payload["dirs"]) == ["indexes", "state", "tmp"]
    assert not (tmp_path / ".agentos" / "tapes").exists()


def test_init_global_storage_dirs_exclude_legacy_tapes(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home_dir = tmp_path / "home"
    monkeypatch.setenv("AGENTOS_HOME", str(home_dir))

    assert main(["init", "--scope", "global"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert sorted(payload["dirs"]) == ["cache", "indexes", "tmp"]
    assert not (home_dir / "tapes").exists()
