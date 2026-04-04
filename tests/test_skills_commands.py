from __future__ import annotations

import json
import shutil
from pathlib import Path

from agentos.cli import main


def _create_skill(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text("# skill\n", encoding="utf-8")


def _write_project_config(project_root: Path, imports: list[dict[str, object]]) -> None:
    marker_path = project_root / ".agentos" / "project.json"
    config_path = project_root / ".agentos" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    marker_payload = {
        "class": "agentos.project",
        "schema_version": 1,
        "project_id": "00000000-0000-4000-8000-000000000001",
    }
    payload = {
        "class": "agentos.project.config",
        "schema_version": 1,
        "skills": {
            "imports": imports,
        },
    }
    marker_path.write_text(json.dumps(marker_payload, indent=2) + "\n", encoding="utf-8")
    config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_skills_sync_creates_symlinks_from_configured_imports(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "project"
    workspace_dir = project_root / "nested" / "child"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    external_root = tmp_path / "external-skills"
    alpha_skill = external_root / "alpha-skill"
    beta_skill = external_root / "group-one" / "beta-skill"
    _create_skill(alpha_skill)
    _create_skill(beta_skill)

    _write_project_config(
        project_root,
        [{"name": "shared", "path": "../external-skills"}],
    )

    monkeypatch.chdir(workspace_dir)
    assert main(["skills", "sync"]) == 0
    stdout = capsys.readouterr().out

    alpha_link = project_root / "skills" / "alpha-skill"
    beta_link = project_root / "skills" / "beta-skill"
    assert "created:" in stdout
    assert alpha_link.is_symlink()
    assert beta_link.is_symlink()
    assert alpha_link.resolve() == alpha_skill.resolve()
    assert beta_link.resolve() == beta_skill.resolve()
    assert (project_root / ".agentos" / "state" / "skills-links.json").is_file()


def test_skills_sync_uses_skills_folder_override(tmp_path: Path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    external_root = tmp_path / "external-skills"
    alpha_skill = external_root / "alpha-skill"
    _create_skill(alpha_skill)

    _write_project_config(
        project_root,
        [{"name": "shared", "path": "../external-skills"}],
    )

    monkeypatch.chdir(project_root)
    assert main(["skills", "sync", "--skills-folder", ".agents/skills"]) == 0
    capsys.readouterr()

    override_link = project_root / ".agents" / "skills" / "alpha-skill"
    default_link = project_root / "skills" / "alpha-skill"
    assert override_link.is_symlink()
    assert override_link.resolve() == alpha_skill.resolve()
    assert not default_link.exists()


def test_skills_sync_errors_on_duplicate_imported_skill_names(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    _create_skill(first_root / "alpha-skill")
    _create_skill(second_root / "alpha-skill")

    _write_project_config(
        project_root,
        [
            {"name": "first", "path": "../first"},
            {"name": "second", "path": "../second"},
        ],
    )

    monkeypatch.chdir(project_root)
    assert main(["skills", "sync"]) == 1
    stderr = capsys.readouterr().err
    assert "duplicate imported skill names" in stderr
    assert not (project_root / "skills" / "alpha-skill").exists()


def test_skills_sync_updates_previous_managed_link(tmp_path: Path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_skill = first_root / "alpha-skill"
    second_skill = second_root / "alpha-skill"
    _create_skill(first_skill)
    _create_skill(second_skill)

    _write_project_config(
        project_root,
        [{"name": "shared", "path": "../first"}],
    )

    monkeypatch.chdir(project_root)
    assert main(["skills", "sync"]) == 0
    capsys.readouterr()

    _write_project_config(
        project_root,
        [{"name": "shared", "path": "../second"}],
    )

    assert main(["skills", "sync"]) == 0
    stdout = capsys.readouterr().out

    alpha_link = project_root / "skills" / "alpha-skill"
    assert "updated:" in stdout
    assert alpha_link.is_symlink()
    assert alpha_link.resolve() == second_skill.resolve()


def test_skills_sync_removes_stale_managed_link_when_import_removed(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    external_root = tmp_path / "external-skills"
    alpha_skill = external_root / "alpha-skill"
    _create_skill(alpha_skill)

    _write_project_config(
        project_root,
        [{"name": "shared", "path": "../external-skills"}],
    )

    monkeypatch.chdir(project_root)
    assert main(["skills", "sync"]) == 0
    capsys.readouterr()

    _write_project_config(project_root, [])
    assert main(["skills", "sync"]) == 0
    stdout = capsys.readouterr().out

    alpha_link = project_root / "skills" / "alpha-skill"
    assert "removed stale link:" in stdout
    assert not alpha_link.exists()
    assert not alpha_link.is_symlink()


def test_skills_sync_errors_on_unmanaged_conflicting_path(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    external_root = tmp_path / "external-skills"
    alpha_skill = external_root / "alpha-skill"
    _create_skill(alpha_skill)

    _write_project_config(
        project_root,
        [{"name": "shared", "path": "../external-skills"}],
    )

    conflicting_path = project_root / "skills" / "alpha-skill"
    conflicting_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.chdir(project_root)
    assert main(["skills", "sync"]) == 1
    stderr = capsys.readouterr().err

    assert "conflicting existing paths" in stderr
    assert conflicting_path.is_dir()
    assert not conflicting_path.is_symlink()


def test_skills_prune_removes_broken_managed_symlink(tmp_path: Path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    external_root = tmp_path / "external-skills"
    alpha_skill = external_root / "alpha-skill"
    _create_skill(alpha_skill)

    _write_project_config(
        project_root,
        [{"name": "shared", "path": "../external-skills"}],
    )

    monkeypatch.chdir(project_root)
    assert main(["skills", "sync"]) == 0
    capsys.readouterr()

    shutil.rmtree(alpha_skill)

    assert main(["skills", "prune"]) == 0
    stdout = capsys.readouterr().out

    alpha_link = project_root / "skills" / "alpha-skill"
    assert f"removed: {alpha_link}" in stdout
    assert not alpha_link.exists()
    assert not alpha_link.is_symlink()


def test_skills_list_and_path_use_effective_project_target(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    external_root = tmp_path / "external-skills"
    alpha_skill = external_root / "alpha-skill"
    _create_skill(alpha_skill)

    _write_project_config(
        project_root,
        [{"name": "shared", "path": "../external-skills"}],
    )

    monkeypatch.chdir(project_root)
    assert main(["skills", "sync", "--skills-folder", ".agents/skills"]) == 0
    capsys.readouterr()

    assert main(["skills", "list", "--skills-folder", ".agents/skills", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed == ["alpha-skill"]

    assert main(["skills", "path", "--skills-folder", ".agents/skills"]) == 0
    target_path = capsys.readouterr().out.strip()
    assert target_path == str((project_root / ".agents" / "skills").resolve())

    assert main(["skills", "path", "alpha-skill", "--skills-folder", ".agents/skills"]) == 0
    skill_path = capsys.readouterr().out.strip()
    assert skill_path == str(project_root / ".agents" / "skills" / "alpha-skill")


def test_skills_commands_require_dot_agentos_directory(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["skills", "path"]) == 1
    stderr = capsys.readouterr().err

    assert "missing .agentos/project.json" in stderr


def test_skills_commands_ignore_global_agentos_home_without_project_marker(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    fake_home = tmp_path / "home"
    (fake_home / ".agentos").mkdir(parents=True, exist_ok=True)

    workspace = fake_home / "work" / "repo"
    workspace.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(workspace)

    assert main(["skills", "path"]) == 1
    stderr = capsys.readouterr().err

    assert "missing .agentos/project.json" in stderr
