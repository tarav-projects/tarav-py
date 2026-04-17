from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli import build_parser, main

NO_ROUTED_SKILLS_MESSAGE = "No routed skills are available for this caller context."


def _set_fake_agentos_home(monkeypatch, root: Path) -> Path:
    agentos_home = root / ".agentos"
    agentos_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    return agentos_home


def _create_skill(path: Path, *, description: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        (
            "---\n"
            f"name: {path.name}\n"
            f"description: {description}\n"
            "---\n\n"
            f"# {path.name}\n"
        ),
        encoding="utf-8",
    )


def _create_local_agents_context(root: Path) -> None:
    (root / ".agents").mkdir(parents=True, exist_ok=True)


def _write_global_routing_config(
    agentos_home: Path,
    *,
    imports_registry: dict[str, dict[str, object]] | None = None,
    packages: dict[str, dict[str, object]] | None = None,
    profiles: dict[str, dict[str, object]] | None = None,
    default_profile: str | None = None,
) -> None:
    routing_payload: dict[str, object] = {
        "imports_registry": {} if imports_registry is None else imports_registry,
        "packages": {} if packages is None else packages,
        "profiles": {} if profiles is None else profiles,
    }
    if default_profile is not None:
        routing_payload["default_profile"] = default_profile

    config_path = agentos_home / "config.json"
    payload = {
        "class": "agentos.global.config",
        "schema_version": 1,
        "skills": {
            "routing": routing_payload,
        },
    }
    config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_project_marker(project_root: Path) -> None:
    marker_path = project_root / ".agentos" / "project.json"
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_payload = {
        "class": "agentos.project",
        "schema_version": 1,
        "project_id": "00000000-0000-4000-8000-000000000001",
    }
    marker_path.write_text(json.dumps(marker_payload, indent=2) + "\n", encoding="utf-8")


def _write_project_config(project_root: Path, *, profile: str | None = None) -> None:
    config_path = project_root / ".agentos" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "class": "agentos.project.config",
        "schema_version": 1,
    }
    if profile is not None:
        payload["skills"] = {
            "routing": {
                "profile": profile,
            }
        }
    config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_skills_list_returns_authoritative_empty_catalog(capsys, monkeypatch, tmp_path: Path) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(workspace)

    assert main(["skills", "list"]) == 0
    assert capsys.readouterr().out.strip() == NO_ROUTED_SKILLS_MESSAGE


def test_skills_list_uses_default_profile_and_predicts_local_depot_paths(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)
    _create_skill(workspace / "skills" / "alpha-skill", description="Base alpha skill")

    _write_global_routing_config(
        agentos_home,
        imports_registry={
            "base": {"path": str(workspace / "skills")},
        },
        profiles={
            "default": {
                "imports": [
                    {"name": "base"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    expected_path = workspace / ".agents" / "skills" / "base-alpha-skill"
    assert listed == [
        {
            "name": "base-alpha-skill",
            "description": "Base alpha skill",
            "source": "base",
            "path": str(expected_path),
        }
    ]
    assert not expected_path.exists()


def test_skills_list_renders_card_like_output(capsys, monkeypatch, tmp_path: Path) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)
    _create_skill(workspace / "skills" / "alpha-skill", description="Base alpha skill")

    _write_global_routing_config(
        agentos_home,
        imports_registry={
            "base": {"path": str(workspace / "skills")},
        },
        profiles={
            "default": {
                "imports": [
                    {"name": "base"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list"]) == 0
    assert capsys.readouterr().out.strip() == (
        "base-alpha-skill\n"
        "- source: base\n"
        f"- path: {workspace / '.agents' / 'skills' / 'base-alpha-skill'}\n"
        "- description: Base alpha skill"
    )


def test_skills_list_uses_agentos_project_root_before_pwd(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    project_root = tmp_path / "project"
    nested = project_root / "nested" / "child"
    nested.mkdir(parents=True, exist_ok=True)
    _write_project_marker(project_root)
    _create_skill(project_root / "skills" / "alpha-skill", description="Project alpha skill")

    _write_global_routing_config(
        agentos_home,
        imports_registry={
            "project": {"path": str(project_root / "skills")},
        },
        profiles={
            "default": {
                "imports": [
                    {"name": "project"},
                ]
            }
        },
    )

    monkeypatch.chdir(nested)
    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == [
        {
            "name": "project-alpha-skill",
            "description": "Project alpha skill",
            "source": "project",
            "path": str(project_root / ".agents" / "skills" / "project-alpha-skill"),
        }
    ]


def test_skills_list_uses_nearest_local_agents_context_before_agentos_project_root(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    parent_root = tmp_path / "workspace"
    child_root = parent_root / "child"
    deeper_root = child_root / "deeper"
    deeper_root.mkdir(parents=True, exist_ok=True)

    _write_project_marker(parent_root)
    _create_local_agents_context(child_root)
    _create_skill(parent_root / "skills" / "alpha-skill", description="Parent alpha skill")
    _create_skill(child_root / "skills" / "beta-skill", description="Child beta skill")

    _write_global_routing_config(
        agentos_home,
        profiles={
            "default": {
                "imports": [
                    {"name": "local", "path": "skills"},
                ]
            }
        },
    )

    monkeypatch.chdir(deeper_root)
    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == [
        {
            "name": "local-beta-skill",
            "description": "Child beta skill",
            "source": "local",
            "path": str(child_root / ".agents" / "skills" / "local-beta-skill"),
        }
    ]


def test_skills_list_honors_project_override(capsys, monkeypatch, tmp_path: Path) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    target_root = tmp_path / "target-project"
    other_root = tmp_path / "other"
    other_root.mkdir(parents=True, exist_ok=True)
    _create_skill(target_root / "skills" / "alpha-skill", description="Override alpha skill")

    _write_global_routing_config(
        agentos_home,
        profiles={
            "default": {
                "imports": [
                    {"name": "override", "path": "skills"},
                ]
            }
        },
    )

    monkeypatch.chdir(other_root)
    assert main(["skills", "list", "--project", str(target_root), "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == [
        {
            "name": "override-alpha-skill",
            "description": "Override alpha skill",
            "source": "override",
            "path": str(target_root / ".agents" / "skills" / "override-alpha-skill"),
        }
    ]


def test_skills_list_uses_pwd_when_project_flag_has_no_value(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_skill(workspace / "skills" / "alpha-skill", description="Pwd override alpha skill")

    _write_global_routing_config(
        agentos_home,
        profiles={
            "default": {
                "imports": [
                    {"name": "override", "path": "skills"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list", "--project", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == [
        {
            "name": "override-alpha-skill",
            "description": "Pwd override alpha skill",
            "source": "override",
            "path": str(workspace / ".agents" / "skills" / "override-alpha-skill"),
        }
    ]


def test_skills_list_honors_local_project_profile_override(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    project_root = tmp_path / "project"
    nested = project_root / "nested"
    nested.mkdir(parents=True, exist_ok=True)
    _write_project_marker(project_root)
    _write_project_config(project_root, profile="research")
    _create_skill(project_root / "default-skills" / "alpha-skill", description="Default alpha skill")
    _create_skill(project_root / "research-skills" / "beta-skill", description="Research beta skill")

    _write_global_routing_config(
        agentos_home,
        profiles={
            "default": {
                "imports": [
                    {"name": "default", "path": "default-skills"},
                ]
            },
            "research": {
                "imports": [
                    {"name": "research", "path": "research-skills"},
                ]
            },
        },
        default_profile="default",
    )

    monkeypatch.chdir(nested)
    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == [
        {
            "name": "research-beta-skill",
            "description": "Research beta skill",
            "source": "research",
            "path": str(project_root / ".agents" / "skills" / "research-beta-skill"),
        }
    ]


def test_skills_path_returns_predictive_local_path_before_import(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)
    _create_skill(workspace / "skills" / "alpha-skill", description="Base alpha skill")

    _write_global_routing_config(
        agentos_home,
        imports_registry={
            "base": {"path": str(workspace / "skills")},
        },
        profiles={
            "default": {
                "imports": [
                    {"name": "base"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    expected_path = workspace / ".agents" / "skills" / "base-alpha-skill"
    assert main(["skills", "path", "base-alpha-skill"]) == 0
    assert capsys.readouterr().out.strip() == str(expected_path)
    assert not expected_path.exists()


def test_skills_path_with_depot_flag_returns_local_depot_path(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)

    _write_global_routing_config(
        agentos_home,
        profiles={
            "default": {
                "imports": []
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "path", "--depot"]) == 0
    assert capsys.readouterr().out.strip() == str(workspace / ".agents" / "skills")


def test_skills_path_without_name_prints_help(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    monkeypatch.chdir(workspace)
    assert main(["skills", "path"]) == 0
    assert "usage: agentos skills path" in capsys.readouterr().out


def test_skills_path_with_depot_flag_errors_when_no_context_exists(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(workspace)

    assert main(["skills", "path", "--depot"]) == 1
    assert capsys.readouterr().err.strip() == (
        "error: no local routed skills context is available for this caller context"
    )


def test_skills_path_returns_routed_not_found_for_missing_catalog_skill(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)

    _write_global_routing_config(
        agentos_home,
        profiles={
            "default": {
                "imports": []
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "path", "agentos-live-note-base"]) == 1
    assert capsys.readouterr().err.strip() == (
        "error: skill not found in routed skills: agentos-live-note-base"
    )


def test_skills_profile_supports_packages_plus_inline_imports(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    registry_root = tmp_path / "registry-source"
    inline_root = tmp_path / "inline-source"
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)

    _create_skill(registry_root / "alpha-skill", description="Registry alpha skill")
    _create_skill(inline_root / "beta-skill", description="Inline beta skill")

    _write_global_routing_config(
        agentos_home,
        imports_registry={
            "registry": {"path": str(registry_root)},
        },
        packages={
            "core": {
                "imports": [
                    {"name": "registry"},
                ]
            }
        },
        profiles={
            "default": {
                "packages": [
                    {"name": "core"},
                ],
                "imports": [
                    {"name": "inline", "path": str(inline_root)},
                ],
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == [
        {
            "name": "inline-beta-skill",
            "description": "Inline beta skill",
            "source": "inline",
            "path": str(workspace / ".agents" / "skills" / "inline-beta-skill"),
        },
        {
            "name": "registry-alpha-skill",
            "description": "Registry alpha skill",
            "source": "registry",
            "path": str(workspace / ".agents" / "skills" / "registry-alpha-skill"),
        },
    ]


def test_skills_profile_import_ref_errors_on_unknown_registry_entry(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)

    _write_global_routing_config(
        agentos_home,
        profiles={
            "default": {
                "imports": [
                    {"name": "missing"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list"]) == 1
    assert capsys.readouterr().err.strip() == (
        "error: routing import references unknown registry entry: missing"
    )


def test_skills_import_materializes_local_skill_depot(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)
    source_skill = workspace / "skills" / "alpha-skill"
    _create_skill(source_skill, description="Base alpha skill")

    _write_global_routing_config(
        agentos_home,
        imports_registry={
            "base": {"path": str(workspace / "skills")},
        },
        profiles={
            "default": {
                "imports": [
                    {"name": "base"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    expected_path = workspace / ".agents" / "skills" / "base-alpha-skill"
    assert not expected_path.exists()

    assert main(["skills", "import"]) == 0
    out = capsys.readouterr().out

    assert "Routed skills import complete" in out
    assert f"- depot: {workspace / '.agents' / 'skills'}" in out
    assert "- catalog: 1" in out
    assert "- created: 1" in out
    assert expected_path.is_symlink()
    assert expected_path.resolve() == source_skill.resolve()


def test_skills_import_returns_authoritative_empty_catalog_when_no_context_exists(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    monkeypatch.chdir(workspace)
    assert main(["skills", "import"]) == 0
    assert capsys.readouterr().out.strip() == NO_ROUTED_SKILLS_MESSAGE


def test_skills_import_uses_pwd_when_project_flag_has_no_value(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    source_skill = workspace / "skills" / "alpha-skill"
    _create_skill(source_skill, description="Pwd import alpha skill")

    _write_global_routing_config(
        agentos_home,
        profiles={
            "default": {
                "imports": [
                    {"name": "override", "path": "skills"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    expected_path = workspace / ".agents" / "skills" / "override-alpha-skill"
    assert main(["skills", "import", "--project"]) == 0
    assert expected_path.is_symlink()
    assert expected_path.resolve() == source_skill.resolve()


def test_skills_surface_only_exposes_list_import_and_path(capsys) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["skills", "query"])

    assert excinfo.value.code == 2
    assert "invalid choice: 'query'" in capsys.readouterr().err
