from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli import main
from _helpers import write_project_marker, write_text_file


def _write_named_project_marker(project_root: Path, project_name: str) -> None:
    write_text_file(
        project_root / ".agentos" / "project.json",
        json.dumps(
            {
                "class": "agentos.project",
                "schema_version": 1,
                "project_id": "00000000-0000-4000-8000-000000000001",
                "project_name": project_name,
            }
        )
        + "\n",
    )


def test_projects_list_prints_agentos_projects_under_root(
    tmp_path: Path,
    capsys,
) -> None:
    workspace = tmp_path / "workspace"
    project_b = workspace / "b-project"
    project_a = workspace / "nested" / "a-project"
    not_project = workspace / "not-project"
    project_b.mkdir(parents=True)
    project_a.mkdir(parents=True)
    not_project.mkdir(parents=True)
    write_project_marker(project_b)
    write_project_marker(project_a)
    write_text_file(not_project / ".agentos" / "config.json", "{}\n")

    assert main(["projects", "list", "--root", str(workspace)]) == 0

    assert capsys.readouterr().out.splitlines() == [
        str(project_b.resolve()),
        str(project_a.resolve()),
    ]


def test_projects_list_requires_root(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["projects", "list"])

    assert excinfo.value.code == 2
    assert "the following arguments are required: --root" in capsys.readouterr().err


def test_projects_resolve_matches_current_project_basename(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "named-project"
    project_root.mkdir()
    write_project_marker(project_root)
    monkeypatch.chdir(project_root)

    assert main(["projects", "resolve", "--project-base", "named-project"]) == 0

    assert capsys.readouterr().out.strip() == "true"


def test_projects_resolve_uses_explicit_project_target(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "path-project"
    other_root = tmp_path / "other"
    project_root.mkdir()
    other_root.mkdir()
    write_project_marker(project_root)
    monkeypatch.chdir(other_root)

    assert (
        main(
            [
                "projects",
                "resolve",
                "--project",
                str(project_root),
                "--project-base",
                "path-project",
            ]
        )
        == 0
    )

    assert capsys.readouterr().out.strip() == "true"


def test_projects_resolve_bare_project_targets_current_directory(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "bare-project"
    project_root.mkdir()
    write_project_marker(project_root)
    monkeypatch.chdir(project_root)

    assert main(["projects", "resolve", "--project", "--project-base", "bare-project"]) == 0

    assert capsys.readouterr().out.strip() == "true"


def test_projects_resolve_requires_project_base(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    write_project_marker(tmp_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        main(["projects", "resolve"])

    assert excinfo.value.code == 2
    assert "the following arguments are required: --project-base" in capsys.readouterr().err


def test_projects_resolve_project_base_assertion_fails_on_mismatch(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "actual-project"
    project_root.mkdir()
    write_project_marker(project_root)
    monkeypatch.chdir(project_root)

    assert main(["projects", "resolve", "--project-base", "other-project"]) == 1

    assert "project base assertion failed" in capsys.readouterr().err


def test_projects_resolve_project_base_ignores_marker_name(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "basename-project"
    project_root.mkdir()
    _write_named_project_marker(project_root, "declared-name")
    monkeypatch.chdir(project_root)

    assert main(["projects", "resolve", "--project-base", "basename-project"]) == 0

    assert capsys.readouterr().out.strip() == "true"
