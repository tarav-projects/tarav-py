from __future__ import annotations

import json
from pathlib import Path

from agentos.cli import main


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_project_marker(project_root: Path) -> None:
    _write(
        project_root / ".agentos" / "project.json",
        json.dumps(
            {
                "class": "agentos.project",
                "schema_version": 1,
                "project_id": "00000000-0000-4000-8000-000000000001",
            }
        )
        + "\n",
    )


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
