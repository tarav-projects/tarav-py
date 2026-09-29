from __future__ import annotations

from pathlib import Path

import pytest

from tarav.l0.testing import write_project_marker
from tarav.l3.cli.cli import main
from _helpers import captured_json, write_text_file


PROJECT_ID = "00000000-0000-4000-8000-000000000001"


def test_project_namespace_replaces_legacy_top_level_commands(capsys) -> None:
    for command in ("init", "rev-parse", "projects", "skills"):
        with pytest.raises(SystemExit) as excinfo:
            main([command])
        assert excinfo.value.code == 2
        assert "invalid choice" in capsys.readouterr().err


def test_project_resolve_reports_project_root(tmp_path: Path, capsys) -> None:
    write_project_marker(tmp_path)

    assert (
        main(
            [
                "project",
                "resolve",
                "--show-toplevel",
                "--path",
                str(tmp_path),
            ]
        )
        == 0
    )

    assert capsys.readouterr().out.strip() == str(tmp_path.resolve())


def _write_named_project_marker(project_root: Path, project_name: str) -> None:
    write_project_marker(
        project_root,
        project_id=PROJECT_ID,
        project_name=project_name,
    )


def _expected_project_list_record(project_root: Path, project_name: str | None) -> dict[str, object]:
    resolved_root = project_root.resolve()
    return {
        "project_root": str(resolved_root),
        "project_id": PROJECT_ID,
        "project_name": project_name,
        "marker_path": str(resolved_root / ".tarav" / "project.json"),
    }


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
    write_text_file(not_project / ".tarav" / "config.json", "{}\n")

    assert main(["project", "list", "--root", str(workspace)]) == 0

    assert capsys.readouterr().out.splitlines() == [
        str(project_b.resolve()),
        str(project_a.resolve()),
    ]


def test_projects_list_json_prints_project_metadata(
    tmp_path: Path,
    capsys,
) -> None:
    workspace = tmp_path / "workspace"
    project_b = workspace / "b-project"
    project_a = workspace / "nested" / "a-project"
    project_b.mkdir(parents=True)
    project_a.mkdir(parents=True)
    write_project_marker(project_b)
    _write_named_project_marker(project_a, "Tarav A")

    assert main(["project", "list", "--root", str(workspace), "--json"]) == 0

    assert captured_json(capsys) == [
        _expected_project_list_record(project_b, None),
        _expected_project_list_record(project_a, "Tarav A"),
    ]


def test_projects_list_requires_root(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["project", "list"])

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

    assert main(["project", "verify", "--project-base", "named-project"]) == 0

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
                "project",
                "verify",
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

    assert main(["project", "verify", "--project", "--project-base", "bare-project"]) == 0

    assert capsys.readouterr().out.strip() == "true"


def test_projects_resolve_requires_project_base(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    write_project_marker(tmp_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        main(["project", "verify"])

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

    assert main(["project", "verify", "--project-base", "other-project"]) == 1

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

    assert main(["project", "verify", "--project-base", "basename-project"]) == 0

    assert capsys.readouterr().out.strip() == "true"
