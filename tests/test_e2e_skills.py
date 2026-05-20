from __future__ import annotations

from pathlib import Path

import pytest

from agentos.cli import build_parser, main
from _helpers import captured_json, set_fake_agentos_home, write_global_routing_config, write_project_marker, write_text_file


def _create_skill(path: Path, *, description: str) -> None:
    write_text_file(
        path / "SKILL.md",
        f"---\nname: {path.name}\ndescription: {description}\n---\n\n# {path.name}\n",
    )


def _make_project(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    write_project_marker(path)


def _skills(argv: list[str]) -> list[str]:
    return [*argv, "--project"]


def test_skills_list_and_path_use_selected_profile(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    agentos_home = set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    source_root = tmp_path / "source"
    _make_project(workspace)
    _create_skill(source_root / "alpha-skill", description="Alpha skill")
    write_global_routing_config(
        agentos_home,
        sources={"base": {"path": str(source_root)}},
        profiles={"default": {"sources": [{"name": "base"}]}},
    )
    monkeypatch.chdir(workspace)

    assert main(_skills(["skills", "list", "--json"])) == 0
    listed = captured_json(capsys)
    assert listed == [
        {
            "name": "base-alpha-skill",
            "description": "Alpha skill",
            "source": "base",
            "paths": [
                str(workspace / ".agents" / "skills" / "base-alpha-skill"),
                str(workspace / ".claude" / "skills" / "base-alpha-skill"),
            ],
        }
    ]

    assert main(_skills(["skills", "path", "base-alpha-skill"])) == 0
    assert capsys.readouterr().out.strip().splitlines() == [
        str(workspace / ".agents" / "skills" / "base-alpha-skill"),
        str(workspace / ".claude" / "skills" / "base-alpha-skill"),
    ]


def test_skills_import_and_status_materialize_default_depots(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    agentos_home = set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    source_skill = workspace / "skills" / "alpha-skill"
    _make_project(workspace)
    _create_skill(source_skill, description="Base alpha skill")
    write_global_routing_config(
        agentos_home,
        sources={"base": {"path": str(workspace / "skills")}},
        profiles={"default": {"sources": [{"name": "base"}]}},
    )
    monkeypatch.chdir(workspace)

    assert main(_skills(["skills", "import"])) == 0
    out = capsys.readouterr().out
    assert "Skills import complete" in out
    assert "- catalog: 1" in out

    agents_depot = workspace / ".agents" / "skills"
    claude_depot = workspace / ".claude" / "skills"
    assert agents_depot.is_symlink()
    assert claude_depot.is_symlink()
    assert (agents_depot / "base-alpha-skill").resolve() == source_skill.resolve()
    assert (claude_depot / "base-alpha-skill").resolve() == source_skill.resolve()

    assert main(_skills(["skills", "status", "--json"])) == 0
    status = captured_json(capsys)
    assert status["profile"] == "default"
    assert status["expected"] == 1
    assert [depot["depot"] for depot in status["depots"]] == [str(agents_depot), str(claude_depot)]
    assert all(depot["missing"] == [] and depot["broken"] == [] and depot["conflicts"] == [] for depot in status["depots"])


def test_skills_flat_import_and_force_rebuild_handle_project_depots(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    agentos_home = set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    source_skill = workspace / "skills" / "alpha-skill"
    _make_project(workspace)
    _create_skill(source_skill, description="Base alpha skill")
    write_global_routing_config(
        agentos_home,
        sources={"base": {"path": str(workspace / "skills")}},
        profiles={"default": {"sources": [{"name": "base"}]}},
    )
    monkeypatch.chdir(workspace)

    assert main(_skills(["skills", "import", "--mode", "flat-linking"])) == 0
    capsys.readouterr()
    agents_depot = workspace / ".agents" / "skills"
    assert agents_depot.is_dir()
    assert not agents_depot.is_symlink()
    assert (agents_depot / "base-alpha-skill").resolve() == source_skill.resolve()

    assert main(_skills(["skills", "import", "--force"])) == 0
    assert "Skills import complete" in capsys.readouterr().out
    assert agents_depot.is_symlink()


def test_skills_project_source_and_config_errors(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    agentos_home = set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    source_project = tmp_path / "source-project"
    _make_project(workspace)
    source_project.mkdir()
    write_global_routing_config(
        agentos_home,
        sources={"project": {"project": str(source_project)}},
        profiles={"default": {"sources": [{"name": "project"}]}},
    )
    monkeypatch.chdir(workspace)

    assert main(_skills(["skills", "list"])) == 1
    error = capsys.readouterr().err
    assert "is not an agentos project" in error
    assert ".agentos/project.json" in error

    write_project_marker(source_project)
    _create_skill(source_project / "skills" / "alpha-skill", description="Project alpha")
    assert main(_skills(["skills", "list", "--json"])) == 0
    listed = captured_json(capsys)
    assert listed[0]["name"] == "project-alpha-skill"


def test_skills_surface_only_exposes_supported_commands(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    assert parser.parse_args(["skills", "status"]).skills_command == "status"

    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["skills", "query"])
    assert excinfo.value.code == 2
    assert "invalid choice: 'query'" in capsys.readouterr().err
