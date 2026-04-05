from __future__ import annotations

import json
import shutil
from pathlib import Path

from agentos.cli import main


def _create_skill(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text("# skill\n", encoding="utf-8")


def _write_project_config(
    project_root: Path,
    imports: list[dict[str, object]] | None = None,
    *,
    include_imports_field: bool = True,
    skills_depot: str | None = None,
) -> None:
    marker_path = project_root / ".agentos" / "project.json"
    config_path = project_root / ".agentos" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    marker_payload = {
        "class": "agentos.project",
        "schema_version": 1,
        "project_id": "00000000-0000-4000-8000-000000000001",
    }
    skills_payload: dict[str, object] = {}
    if include_imports_field:
        skills_payload["imports"] = [] if imports is None else imports
    if skills_depot is not None:
        skills_payload["skills_depot"] = skills_depot
    payload = {
        "class": "agentos.project.config",
        "schema_version": 1,
        "skills": skills_payload,
    }
    marker_path.write_text(json.dumps(marker_payload, indent=2) + "\n", encoding="utf-8")
    config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _set_fake_home(monkeypatch, home_root: Path) -> Path:
    monkeypatch.setenv("HOME", str(home_root))
    (home_root / ".agentos").mkdir(parents=True, exist_ok=True)
    global_depot = home_root / ".agents" / "skills"
    global_depot.mkdir(parents=True, exist_ok=True)
    return global_depot


def _write_global_config(
    home_root: Path,
    imports: list[dict[str, object]] | None = None,
    *,
    include_imports_field: bool = True,
) -> Path:
    agentos_root = home_root / ".agentos"
    agentos_root.mkdir(parents=True, exist_ok=True)
    config_path = agentos_root / "config.json"
    skills_payload: dict[str, object] = {}
    if include_imports_field:
        skills_payload["imports"] = [] if imports is None else imports
    payload = {
        "class": "agentos.global.config",
        "schema_version": 1,
        "skills": skills_payload,
    }
    config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return config_path


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

    alpha_link = project_root / "skills" / "shared-alpha-skill"
    beta_link = project_root / "skills" / "shared-beta-skill"
    assert "created:" in stdout
    assert alpha_link.is_symlink()
    assert beta_link.is_symlink()
    assert alpha_link.resolve() == alpha_skill.resolve()
    assert beta_link.resolve() == beta_skill.resolve()
    assert (project_root / ".agentos" / "state" / "skills-links.json").is_file()


def test_skills_sync_uses_skills_depot_override(tmp_path: Path, monkeypatch, capsys) -> None:
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
    assert main(["skills", "sync", "--skills-depot", ".agents/skills"]) == 0
    capsys.readouterr()

    override_link = project_root / ".agents" / "skills" / "shared-alpha-skill"
    default_link = project_root / "skills" / "shared-alpha-skill"
    assert override_link.is_symlink()
    assert override_link.resolve() == alpha_skill.resolve()
    assert not default_link.exists()


def test_skills_sync_allows_same_skill_name_across_different_import_prefixes(
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
    assert main(["skills", "sync"]) == 0
    capsys.readouterr()
    assert (project_root / "skills" / "first-alpha-skill").is_symlink()
    assert (project_root / "skills" / "second-alpha-skill").is_symlink()


def test_skills_sync_errors_on_duplicate_mapped_skill_names_within_import(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    first_root = tmp_path / "first"
    _create_skill(first_root / "group-one" / "alpha-skill")
    _create_skill(first_root / "group-two" / "alpha-skill")

    _write_project_config(
        project_root,
        [{"name": "first", "path": "../first"}],
    )

    monkeypatch.chdir(project_root)
    assert main(["skills", "sync"]) == 1
    stderr = capsys.readouterr().err
    assert "duplicate imported skill names" in stderr
    assert "first-alpha-skill" in stderr
    assert not (project_root / "skills" / "first-alpha-skill").exists()


def test_skills_sync_does_not_duplicate_existing_import_prefix(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    external_root = tmp_path / "external-skills"
    prefixed_skill = external_root / "phd-document-collector-base"
    _create_skill(prefixed_skill)

    _write_project_config(
        project_root,
        [{"name": "phd", "path": "../external-skills"}],
    )

    monkeypatch.chdir(project_root)
    assert main(["skills", "sync"]) == 0
    capsys.readouterr()

    expected_link = project_root / "skills" / "phd-document-collector-base"
    duplicated_link = project_root / "skills" / "phd-phd-document-collector-base"
    assert expected_link.is_symlink()
    assert expected_link.resolve() == prefixed_skill.resolve()
    assert not duplicated_link.exists()


def test_skills_sync_does_not_duplicate_exact_import_name(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    external_root = tmp_path / "external-skills"
    exact_skill = external_root / "spec-surfaces"
    _create_skill(exact_skill)

    _write_project_config(
        project_root,
        [{"name": "spec-surfaces", "path": "../external-skills"}],
    )

    monkeypatch.chdir(project_root)
    assert main(["skills", "sync"]) == 0
    capsys.readouterr()

    expected_link = project_root / "skills" / "spec-surfaces"
    duplicated_link = project_root / "skills" / "spec-surfaces-spec-surfaces"
    assert expected_link.is_symlink()
    assert expected_link.resolve() == exact_skill.resolve()
    assert not duplicated_link.exists()


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

    alpha_link = project_root / "skills" / "shared-alpha-skill"
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

    alpha_link = project_root / "skills" / "shared-alpha-skill"
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

    conflicting_path = project_root / "skills" / "shared-alpha-skill"
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

    alpha_link = project_root / "skills" / "shared-alpha-skill"
    assert f"removed: {alpha_link}" in stdout
    assert not alpha_link.exists()
    assert not alpha_link.is_symlink()


def test_skills_list_and_path_use_effective_project_target(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    global_skills_root = _set_fake_home(monkeypatch, tmp_path / "home")
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    external_root = tmp_path / "external-skills"
    alpha_skill = external_root / "alpha-skill"
    _create_skill(alpha_skill)
    _create_skill(global_skills_root / "alpha-skill")
    gamma_skill = global_skills_root / "gamma-skill"
    _create_skill(gamma_skill)

    _write_project_config(
        project_root,
        [{"name": "shared", "path": "../external-skills"}],
        skills_depot=".agents/skills",
    )

    monkeypatch.chdir(project_root)
    assert main(["skills", "sync"]) == 0
    capsys.readouterr()

    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed == [
        {
            "name": "alpha-skill",
            "resolved_from_index": 1,
            "source_kind": "global",
            "root": str(global_skills_root.resolve()),
            "path": str(global_skills_root / "alpha-skill"),
        },
        {
            "name": "gamma-skill",
            "resolved_from_index": 1,
            "source_kind": "global",
            "root": str(global_skills_root.resolve()),
            "path": str(gamma_skill),
        },
        {
            "name": "shared-alpha-skill",
            "resolved_from_index": 0,
            "source_kind": "project",
            "root": str((project_root / ".agents" / "skills").resolve()),
            "path": str(project_root / ".agents" / "skills" / "shared-alpha-skill"),
        },
    ]

    assert main(["skills", "path"]) == 0
    target_path_lines = capsys.readouterr().out.strip().splitlines()
    assert target_path_lines == [
        f"PATH[0] project {(project_root / '.agents' / 'skills').resolve()}",
        f"PATH[1] global {global_skills_root.resolve()}",
    ]

    assert main(["skills", "path", "shared-alpha-skill"]) == 0
    skill_path_lines = capsys.readouterr().out.strip().splitlines()
    assert skill_path_lines == [
        "shared-alpha-skill",
        "resolved_from: PATH[0]",
        "source_kind: project",
        f"path: {project_root / '.agents' / 'skills' / 'shared-alpha-skill'}",
    ]

    assert main(["skills", "list"]) == 0
    list_lines = capsys.readouterr().out.strip().splitlines()
    assert list_lines == [
        f"alpha-skill         global[1]   {global_skills_root / 'alpha-skill'}",
        f"gamma-skill         global[1]   {gamma_skill}",
        f"shared-alpha-skill  project[0]  {project_root / '.agents' / 'skills' / 'shared-alpha-skill'}",
    ]


def test_skills_list_and_path_use_global_skills_outside_project(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    global_skills_root = _set_fake_home(monkeypatch, tmp_path / "home")
    alpha_skill = global_skills_root / "alpha-skill"
    _create_skill(alpha_skill)

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(workspace)

    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed == [
        {
            "name": "alpha-skill",
            "resolved_from_index": 0,
            "source_kind": "global",
            "root": str(global_skills_root.resolve()),
            "path": str(alpha_skill),
        }
    ]

    assert main(["skills", "path"]) == 0
    path_lines = capsys.readouterr().out.strip().splitlines()
    assert path_lines == [f"PATH[0] global {global_skills_root.resolve()}"]

    assert main(["skills", "path", "alpha-skill"]) == 0
    skill_path_lines = capsys.readouterr().out.strip().splitlines()
    assert skill_path_lines == [
        "alpha-skill",
        "resolved_from: PATH[0]",
        "source_kind: global",
        f"path: {alpha_skill}",
    ]


def test_skills_depot_override_affects_list_and_path(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    global_skills_root = _set_fake_home(monkeypatch, tmp_path / "home")
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    external_root = tmp_path / "external-skills"
    alpha_skill = external_root / "alpha-skill"
    _create_skill(alpha_skill)
    gamma_skill = global_skills_root / "gamma-skill"
    _create_skill(gamma_skill)

    _write_project_config(
        project_root,
        [{"name": "shared", "path": "../external-skills"}],
    )

    monkeypatch.chdir(project_root)
    assert main(["skills", "sync", "--skills-depot", ".agents/skills"]) == 0
    capsys.readouterr()

    assert main(["skills", "list", "--skills-depot", ".agents/skills", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed == [
        {
            "name": "gamma-skill",
            "resolved_from_index": 1,
            "source_kind": "global",
            "root": str(global_skills_root.resolve()),
            "path": str(gamma_skill),
        },
        {
            "name": "shared-alpha-skill",
            "resolved_from_index": 0,
            "source_kind": "project",
            "root": str((project_root / ".agents" / "skills").resolve()),
            "path": str(project_root / ".agents" / "skills" / "shared-alpha-skill"),
        },
    ]

    assert main(["skills", "path", "--skills-depot", ".agents/skills"]) == 0
    path_lines = capsys.readouterr().out.strip().splitlines()
    assert path_lines == [
        f"PATH[0] project {(project_root / '.agents' / 'skills').resolve()}",
        f"PATH[1] global {global_skills_root.resolve()}",
    ]


def test_skills_sync_falls_back_to_global_imports_when_project_imports_missing(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home_root = tmp_path / "home"
    _set_fake_home(monkeypatch, home_root)

    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    shared_root = home_root / ".agentos" / "shared-imports"
    alpha_skill = shared_root / "alpha-skill"
    _create_skill(alpha_skill)

    _write_global_config(
        home_root,
        [{"name": "global-shared", "path": "shared-imports"}],
    )
    _write_project_config(project_root, include_imports_field=False)

    monkeypatch.chdir(project_root)
    assert main(["skills", "sync"]) == 0
    stdout = capsys.readouterr().out

    linked_skill = project_root / "skills" / "global-shared-alpha-skill"
    assert "created:" in stdout
    assert linked_skill.is_symlink()
    assert linked_skill.resolve() == alpha_skill.resolve()


def test_skills_sync_project_imports_override_global_fallback(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home_root = tmp_path / "home"
    _set_fake_home(monkeypatch, home_root)

    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    global_shared_root = home_root / ".agentos" / "shared-imports"
    global_alpha_skill = global_shared_root / "alpha-skill"
    _create_skill(global_alpha_skill)

    project_shared_root = tmp_path / "project-imports"
    project_alpha_skill = project_shared_root / "alpha-skill"
    _create_skill(project_alpha_skill)

    _write_global_config(
        home_root,
        [{"name": "global-shared", "path": "shared-imports"}],
    )
    _write_project_config(
        project_root,
        [{"name": "project-shared", "path": "../project-imports"}],
    )

    monkeypatch.chdir(project_root)
    assert main(["skills", "sync"]) == 0
    capsys.readouterr()

    linked_skill = project_root / "skills" / "project-shared-alpha-skill"
    assert linked_skill.is_symlink()
    assert linked_skill.resolve() == project_alpha_skill.resolve()


def test_skills_sync_explicit_empty_project_imports_disable_global_fallback(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home_root = tmp_path / "home"
    _set_fake_home(monkeypatch, home_root)

    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    shared_root = home_root / ".agentos" / "shared-imports"
    _create_skill(shared_root / "alpha-skill")

    _write_global_config(
        home_root,
        [{"name": "global-shared", "path": "shared-imports"}],
    )
    _write_project_config(project_root, [])

    monkeypatch.chdir(project_root)
    assert main(["skills", "sync"]) == 0
    stdout = capsys.readouterr().out

    assert "No changes." in stdout
    assert not (project_root / "skills" / "global-shared-alpha-skill").exists()


def test_skills_sync_global_depot_uses_global_imports_without_project(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home_root = tmp_path / "home"
    global_depot = _set_fake_home(monkeypatch, home_root)
    shared_root = home_root / ".agentos" / "shared-imports"
    alpha_skill = shared_root / "alpha-skill"
    _create_skill(alpha_skill)

    _write_global_config(
        home_root,
        [{"name": "global-shared", "path": "shared-imports"}],
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(workspace)

    assert main(["skills", "sync", "--global-depot"]) == 0
    stdout = capsys.readouterr().out

    linked_skill = global_depot / "global-shared-alpha-skill"
    assert "created:" in stdout
    assert linked_skill.is_symlink()
    assert linked_skill.resolve() == alpha_skill.resolve()


def test_skills_prune_global_depot_removes_broken_managed_symlink(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home_root = tmp_path / "home"
    global_depot = _set_fake_home(monkeypatch, home_root)
    shared_root = home_root / ".agentos" / "shared-imports"
    alpha_skill = shared_root / "alpha-skill"
    _create_skill(alpha_skill)

    _write_global_config(
        home_root,
        [{"name": "global-shared", "path": "shared-imports"}],
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(workspace)

    assert main(["skills", "sync", "--global-depot"]) == 0
    capsys.readouterr()

    shutil.rmtree(alpha_skill)

    assert main(["skills", "prune", "--global-depot"]) == 0
    stdout = capsys.readouterr().out

    linked_skill = global_depot / "global-shared-alpha-skill"
    assert f"removed: {linked_skill}" in stdout
    assert not linked_skill.exists()
    assert not linked_skill.is_symlink()


def test_skills_sync_global_depot_rejects_skills_depot_override(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home_root = tmp_path / "home"
    _set_fake_home(monkeypatch, home_root)

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(workspace)

    assert main(["skills", "sync", "--global-depot", "--skills-depot", ".agents/skills"]) == 1
    stderr = capsys.readouterr().err

    assert "--global-depot cannot be combined with --skills-depot" in stderr


def test_skills_sync_uses_current_folder_as_implicit_project_root(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home_root = tmp_path / "home"
    _set_fake_home(monkeypatch, home_root)

    shared_root = home_root / ".agentos" / "shared-imports"
    alpha_skill = shared_root / "alpha-skill"
    _create_skill(alpha_skill)
    _write_global_config(
        home_root,
        [{"name": "global-shared", "path": "shared-imports"}],
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(workspace)

    assert main(["skills", "sync", "--dry-run"]) == 0
    stdout = capsys.readouterr().out

    expected_link = workspace / "skills" / "global-shared-alpha-skill"
    assert f"DRY-RUN would create: {expected_link}" in stdout
    assert not expected_link.exists()
    assert not (workspace / ".agentos").exists()


def test_skills_prune_uses_current_folder_as_implicit_project_root(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    home_root = tmp_path / "home"
    _set_fake_home(monkeypatch, home_root)

    shared_root = home_root / ".agentos" / "shared-imports"
    alpha_skill = shared_root / "alpha-skill"
    _create_skill(alpha_skill)
    _write_global_config(
        home_root,
        [{"name": "global-shared", "path": "shared-imports"}],
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(workspace)

    assert main(["skills", "sync"]) == 0
    capsys.readouterr()

    shutil.rmtree(alpha_skill)

    assert main(["skills", "prune"]) == 0
    stdout = capsys.readouterr().out

    linked_skill = workspace / "skills" / "global-shared-alpha-skill"
    assert f"removed: {linked_skill}" in stdout
    assert not linked_skill.exists()
