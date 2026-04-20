from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli import build_parser, main

NO_SELECTED_SKILLS_MESSAGE = "No skills are selected for import into this project target."
DEFAULT_DEPOT_PATHS = (Path(".agents/skills"), Path(".claude/skills"))


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
    _write_project_marker(root)


def _resolved_default_depots(root: Path) -> list[Path]:
    return [(root / depot_path).resolve() for depot_path in DEFAULT_DEPOT_PATHS]


def _resolved_skill_paths(root: Path, skill_name: str) -> list[str]:
    return [str(depot_root / skill_name) for depot_root in _resolved_default_depots(root)]


def _write_global_routing_config(
    agentos_home: Path,
    *,
    sources: dict[str, dict[str, object]] | None = None,
    profiles: dict[str, dict[str, object]] | None = None,
    default_profile: str | None = None,
) -> None:
    routing_payload: dict[str, object] = {
        "sources": {} if sources is None else sources,
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

    assert main(["skills", "list"]) == 1
    assert capsys.readouterr().err.strip() == (
        "error: not inside an agentos project (missing .agentos/project.json); run `agentos init`"
    )


def test_skills_help_describes_import_manager(capsys) -> None:
    with pytest.raises(SystemExit, match="0"):
        main(["skills", "--help"])
    output = capsys.readouterr().out

    assert "Preview the selected skills catalog for the current project" in output
    assert "routed" not in output


def test_skills_path_help_describes_predictive_paths(capsys) -> None:
    with pytest.raises(SystemExit, match="0"):
        main(["skills", "path", "--help"])
    output = capsys.readouterr().out

    assert "Paths are predictive until import syncs the depots." in output
    assert "Canonical selected skill name." in output


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
        sources={
            "base": {"path": str(workspace / "skills")},
        },
        profiles={
            "default": {
                "sources": [
                    {"name": "base"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == [
        {
            "name": "base-alpha-skill",
            "description": "Base alpha skill",
            "source": "base",
            "paths": _resolved_skill_paths(workspace, "base-alpha-skill"),
        }
    ]
    assert not (workspace / ".agents" / "skills" / "base-alpha-skill").exists()
    assert not (workspace / ".claude" / "skills" / "base-alpha-skill").exists()


def test_skills_list_renders_name_and_provenance_output(capsys, monkeypatch, tmp_path: Path) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)
    _create_skill(workspace / "skills" / "alpha-skill", description="Base alpha skill")

    _write_global_routing_config(
        agentos_home,
        sources={
            "base": {"path": str(workspace / "skills")},
        },
        profiles={
            "default": {
                "sources": [
                    {"name": "base"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list"]) == 0
    assert capsys.readouterr().out.strip() == "base-alpha-skill (base)"


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
        sources={
            "project": {"path": str(project_root / "skills")},
        },
        profiles={
            "default": {
                "sources": [
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
            "paths": _resolved_skill_paths(project_root, "project-alpha-skill"),
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
                "sources": [
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
            "paths": _resolved_skill_paths(child_root, "local-beta-skill"),
        }
    ]


def test_skills_list_honors_project_override(capsys, monkeypatch, tmp_path: Path) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    target_root = tmp_path / "target-project"
    other_root = tmp_path / "other"
    other_root.mkdir(parents=True, exist_ok=True)
    _write_project_marker(target_root)
    _create_skill(target_root / "skills" / "alpha-skill", description="Override alpha skill")

    _write_global_routing_config(
        agentos_home,
        profiles={
            "default": {
                "sources": [
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
            "paths": _resolved_skill_paths(target_root, "override-alpha-skill"),
        }
    ]


def test_skills_list_uses_pwd_when_project_flag_has_no_value(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _write_project_marker(workspace)
    _create_skill(workspace / "skills" / "alpha-skill", description="Pwd override alpha skill")

    _write_global_routing_config(
        agentos_home,
        profiles={
            "default": {
                "sources": [
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
            "paths": _resolved_skill_paths(workspace, "override-alpha-skill"),
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
                "sources": [
                    {"name": "default", "path": "default-skills"},
                ]
            },
            "research": {
                "sources": [
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
            "paths": _resolved_skill_paths(project_root, "research-beta-skill"),
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
        sources={
            "base": {"path": str(workspace / "skills")},
        },
        profiles={
            "default": {
                "sources": [
                    {"name": "base"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    expected_paths = _resolved_skill_paths(workspace, "base-alpha-skill")
    assert main(["skills", "path", "base-alpha-skill"]) == 0
    assert capsys.readouterr().out.strip() == "\n".join(expected_paths)
    assert not (workspace / ".agents" / "skills" / "base-alpha-skill").exists()
    assert not (workspace / ".claude" / "skills" / "base-alpha-skill").exists()


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
                "sources": []
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "path", "--depot"]) == 0
    assert capsys.readouterr().out.strip() == "\n".join(
        str(path) for path in _resolved_default_depots(workspace)
    )


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
        "error: not inside an agentos project (missing .agentos/project.json); run `agentos init`"
    )


def test_skills_path_returns_not_found_for_missing_catalog_skill(
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
                "sources": []
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "path", "agentos-live-note-base"]) == 1
    assert capsys.readouterr().err.strip() == (
        "error: skill not found in imported skills: agentos-live-note-base"
    )


def test_skills_profile_supports_registry_packages_plus_inline_sources(
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
        sources={
            "registry": {"path": str(registry_root)},
            "core": {
                "package": [
                    {"name": "registry"},
                ]
            },
        },
        profiles={
            "default": {
                "sources": [
                    {"name": "core"},
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
            "paths": _resolved_skill_paths(workspace, "inline-beta-skill"),
        },
        {
            "name": "registry-alpha-skill",
            "description": "Registry alpha skill",
            "source": "registry",
            "paths": _resolved_skill_paths(workspace, "registry-alpha-skill"),
        },
    ]


def test_registry_package_inline_sources_resolve_from_agentos_home(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    registry_root = agentos_home / "bundled-skills"
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)

    _create_skill(registry_root / "alpha-skill", description="Bundled alpha skill")

    _write_global_routing_config(
        agentos_home,
        sources={
            "bundle": {
                "package": [
                    {"name": "bundled", "path": "bundled-skills"},
                ]
            },
        },
        profiles={
            "default": {
                "sources": [
                    {"name": "bundle"},
                ],
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == [
        {
            "name": "bundled-alpha-skill",
            "description": "Bundled alpha skill",
            "source": "bundled",
            "paths": _resolved_skill_paths(workspace, "bundled-alpha-skill"),
        }
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
                "sources": [
                    {"name": "missing"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list"]) == 1
    assert capsys.readouterr().err.strip() == (
        "error: routing source references unknown registry source: missing"
    )


def test_skills_profile_source_packages_detect_cycles(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)

    _write_global_routing_config(
        agentos_home,
        sources={
            "alpha": {
                "package": [
                    {"name": "beta"},
                ]
            },
            "beta": {
                "package": [
                    {"name": "alpha"},
                ]
            },
        },
        profiles={
            "default": {
                "sources": [
                    {"name": "alpha"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list"]) == 1
    assert capsys.readouterr().err.strip() == (
        "error: routing source cycle detected: alpha -> beta -> alpha"
    )


def test_skills_list_rejects_legacy_routing_imports_registry_key(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)

    config_path = agentos_home / "config.json"
    payload = {
        "class": "agentos.global.config",
        "schema_version": 1,
        "skills": {
            "routing": {
                "imports_registry": {
                    "legacy": {
                        "path": str(workspace / "skills"),
                    }
                },
                "profiles": {
                    "default": {
                        "sources": [],
                    }
                },
            }
        },
    }
    config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    monkeypatch.chdir(workspace)
    assert main(["skills", "list"]) == 1
    assert capsys.readouterr().err.strip() == (
        "error: global config field skills.routing.imports_registry is no longer supported; use sources"
    )


def test_skills_import_materializes_default_local_skill_depots(
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
        sources={
            "base": {"path": str(workspace / "skills")},
        },
        profiles={
            "default": {
                "sources": [
                    {"name": "base"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    expected_agents_path = workspace / ".agents" / "skills" / "base-alpha-skill"
    expected_claude_path = workspace / ".claude" / "skills" / "base-alpha-skill"
    assert not expected_agents_path.exists()
    assert not expected_claude_path.exists()

    assert main(["skills", "import"]) == 0
    out = capsys.readouterr().out

    assert "Skills import complete" in out
    assert "- mode: sync" in out
    assert "- catalog: 1" in out
    assert "- depots: 2" in out
    assert f"Depot: {workspace / '.agents' / 'skills'}" in out
    assert f"Depot: {workspace / '.claude' / 'skills'}" in out
    assert "- created: 1" in out
    assert expected_agents_path.is_symlink()
    assert expected_agents_path.resolve() == source_skill.resolve()
    assert expected_claude_path.is_symlink()
    assert expected_claude_path.resolve() == source_skill.resolve()


def test_skills_import_returns_authoritative_empty_catalog_when_no_context_exists(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    monkeypatch.chdir(workspace)
    assert main(["skills", "import"]) == 1
    assert capsys.readouterr().err.strip() == (
        "error: not inside an agentos project (missing .agentos/project.json); run `agentos init`"
    )


def test_skills_import_uses_pwd_when_project_flag_has_no_value(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _write_project_marker(workspace)
    source_skill = workspace / "skills" / "alpha-skill"
    _create_skill(source_skill, description="Pwd import alpha skill")

    _write_global_routing_config(
        agentos_home,
        profiles={
            "default": {
                "depots": [".agents/skills"],
                "sources": [
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


def test_skills_import_warns_when_local_project_config_resolves_to_global_config(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    _write_project_marker(workspace)
    (workspace / ".agentos" / "config.json").symlink_to(agentos_home / "config.json")
    source_skill = workspace / "skills" / "alpha-skill"
    _create_skill(source_skill, description="Pwd import alpha skill")

    _write_global_routing_config(
        agentos_home,
        profiles={
            "default": {
                "depots": [".agents/skills"],
                "sources": [
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
    stderr = capsys.readouterr().err
    assert "error:" not in stderr
    assert "warning: ignoring local project config" in stderr
    assert str(workspace / ".agentos" / "config.json") in stderr
    assert str(agentos_home / "config.json") in stderr


def test_skills_import_force_rebuilds_depot_symlink_layer(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)
    source_skill = workspace / "skills" / "alpha-skill"
    _create_skill(source_skill, description="Base alpha skill")
    wrong_skill = workspace / "other-skills" / "beta-skill"
    _create_skill(wrong_skill, description="Wrong beta skill")
    extra_skill = workspace / "extra-skills" / "gamma-skill"
    _create_skill(extra_skill, description="Extra gamma skill")

    _write_global_routing_config(
        agentos_home,
        sources={
            "base": {"path": str(workspace / "skills")},
        },
        profiles={
            "default": {
                "sources": [
                    {"name": "base"},
                ]
            }
        },
    )

    depot_root = workspace / ".agents" / "skills"
    depot_root.mkdir(parents=True, exist_ok=True)
    managed_path = depot_root / "base-alpha-skill"
    managed_path.symlink_to(wrong_skill.resolve(), target_is_directory=True)
    extra_path = depot_root / "extra-gamma-skill"
    extra_path.symlink_to(extra_skill.resolve(), target_is_directory=True)

    monkeypatch.chdir(workspace)
    assert main(["skills", "import", "--force"]) == 0
    out = capsys.readouterr().out

    assert "Skills import complete" in out
    assert "- mode: force" in out
    assert "- created: 1" in out
    assert "- updated: 0" in out
    assert "- removed: 2" in out
    assert "- matching: 0" in out
    assert managed_path.is_symlink()
    assert managed_path.resolve() == source_skill.resolve()
    assert not extra_path.exists()


def test_skills_import_force_preserves_non_symlink_conflicts(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)
    _create_skill(workspace / "skills" / "alpha-skill", description="Base alpha skill")
    extra_skill = workspace / "extra-skills" / "gamma-skill"
    _create_skill(extra_skill, description="Extra gamma skill")

    _write_global_routing_config(
        agentos_home,
        sources={
            "base": {"path": str(workspace / "skills")},
        },
        profiles={
            "default": {
                "sources": [
                    {"name": "base"},
                ]
            }
        },
    )

    depot_root = workspace / ".agents" / "skills"
    depot_root.mkdir(parents=True, exist_ok=True)
    conflict_path = depot_root / "base-alpha-skill"
    conflict_path.mkdir()
    extra_path = depot_root / "extra-gamma-skill"
    extra_path.symlink_to(extra_skill.resolve(), target_is_directory=True)

    monkeypatch.chdir(workspace)
    assert main(["skills", "import", "--force"]) == 1
    stderr = capsys.readouterr().err

    assert "error: skills import found conflicting existing paths:" in stderr
    assert str(conflict_path) in stderr
    assert conflict_path.is_dir()
    assert extra_path.is_symlink()
    assert extra_path.resolve() == extra_skill.resolve()


def test_skills_import_force_preflights_all_default_depots_before_writing(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)
    source_skill = workspace / "skills" / "alpha-skill"
    _create_skill(source_skill, description="Base alpha skill")
    wrong_skill = workspace / "other-skills" / "beta-skill"
    _create_skill(wrong_skill, description="Wrong beta skill")

    _write_global_routing_config(
        agentos_home,
        sources={
            "base": {"path": str(workspace / "skills")},
        },
        profiles={
            "default": {
                "sources": [
                    {"name": "base"},
                ]
            }
        },
    )

    agents_path = workspace / ".agents" / "skills" / "base-alpha-skill"
    agents_path.parent.mkdir(parents=True, exist_ok=True)
    agents_path.symlink_to(wrong_skill.resolve(), target_is_directory=True)

    claude_path = workspace / ".claude" / "skills" / "base-alpha-skill"
    claude_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.chdir(workspace)
    assert main(["skills", "import", "--force"]) == 1
    stderr = capsys.readouterr().err

    assert "error: skills import found conflicting existing paths:" in stderr
    assert str(claude_path) in stderr
    assert agents_path.is_symlink()
    assert agents_path.resolve() == wrong_skill.resolve()
    assert claude_path.is_dir()


def test_skills_status_reports_clean_imported_depot(
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
        sources={
            "base": {"path": str(workspace / "skills")},
        },
        profiles={
            "default": {
                "sources": [
                    {"name": "base"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "import"]) == 0
    capsys.readouterr()

    assert main(["skills", "status", "--json"]) == 0
    status = json.loads(capsys.readouterr().out)

    assert status["profile"] == "default"
    assert status["expected"] == 1
    assert len(status["depots"]) == 2
    assert [depot["depot"] for depot in status["depots"]] == [
        str(workspace / ".agents" / "skills"),
        str(workspace / ".claude" / "skills"),
    ]
    for depot_status in status["depots"]:
        assert len(depot_status["matching"]) == 1
        assert depot_status["missing"] == []
        assert depot_status["broken"] == []
        assert depot_status["unsynced"] == []
        assert depot_status["conflicts"] == []
        assert depot_status["extra"] == []
        assert depot_status["matching"][0]["name"] == "base-alpha-skill"
        assert depot_status["matching"][0]["actual_resolved_target"] == str(source_skill.resolve())


def test_skills_status_reports_missing_symlinks(
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
        sources={
            "base": {"path": str(workspace / "skills")},
        },
        profiles={
            "default": {
                "depots": [".agents/skills"],
                "sources": [
                    {"name": "base"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "status", "--json"]) == 0
    status = json.loads(capsys.readouterr().out)

    depot_status = status["depots"][0]
    assert len(depot_status["missing"]) == 1
    assert depot_status["missing"][0]["name"] == "base-alpha-skill"
    assert depot_status["missing"][0]["expected_source_path"] == str(source_skill.resolve())
    assert depot_status["matching"] == []
    assert depot_status["broken"] == []
    assert depot_status["unsynced"] == []
    assert depot_status["conflicts"] == []
    assert depot_status["extra"] == []


def test_skills_status_reports_broken_symlinks(
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
        sources={
            "base": {"path": str(workspace / "skills")},
        },
        profiles={
            "default": {
                "depots": [".agents/skills"],
                "sources": [
                    {"name": "base"},
                ]
            }
        },
    )

    depot_root = workspace / ".agents" / "skills"
    depot_root.mkdir(parents=True, exist_ok=True)
    broken_target = workspace / "skills" / "missing-skill"
    (depot_root / "base-alpha-skill").symlink_to(broken_target, target_is_directory=True)

    monkeypatch.chdir(workspace)
    assert main(["skills", "status", "--json"]) == 0
    status = json.loads(capsys.readouterr().out)

    depot_status = status["depots"][0]
    assert len(depot_status["broken"]) == 1
    assert depot_status["broken"][0]["name"] == "base-alpha-skill"
    assert depot_status["broken"][0]["actual_resolved_target"] is None
    assert depot_status["matching"] == []
    assert depot_status["missing"] == []
    assert depot_status["unsynced"] == []
    assert depot_status["conflicts"] == []
    assert depot_status["extra"] == []


def test_skills_status_reports_unsynced_symlinks(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)
    _create_skill(workspace / "skills" / "alpha-skill", description="Base alpha skill")
    wrong_skill = workspace / "other-skills" / "beta-skill"
    _create_skill(wrong_skill, description="Wrong beta skill")

    _write_global_routing_config(
        agentos_home,
        sources={
            "base": {"path": str(workspace / "skills")},
        },
        profiles={
            "default": {
                "depots": [".agents/skills"],
                "sources": [
                    {"name": "base"},
                ]
            }
        },
    )

    depot_root = workspace / ".agents" / "skills"
    depot_root.mkdir(parents=True, exist_ok=True)
    (depot_root / "base-alpha-skill").symlink_to(wrong_skill.resolve(), target_is_directory=True)

    monkeypatch.chdir(workspace)
    assert main(["skills", "status", "--json"]) == 0
    status = json.loads(capsys.readouterr().out)

    depot_status = status["depots"][0]
    assert len(depot_status["unsynced"]) == 1
    assert depot_status["unsynced"][0]["name"] == "base-alpha-skill"
    assert depot_status["unsynced"][0]["actual_resolved_target"] == str(wrong_skill.resolve())
    assert depot_status["matching"] == []
    assert depot_status["missing"] == []
    assert depot_status["broken"] == []
    assert depot_status["conflicts"] == []
    assert depot_status["extra"] == []


def test_skills_status_reports_conflicting_and_extra_entries(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)
    _create_skill(workspace / "skills" / "alpha-skill", description="Base alpha skill")
    extra_skill = workspace / "extra-skills" / "gamma-skill"
    _create_skill(extra_skill, description="Extra gamma skill")

    _write_global_routing_config(
        agentos_home,
        sources={
            "base": {"path": str(workspace / "skills")},
        },
        profiles={
            "default": {
                "depots": [".agents/skills"],
                "sources": [
                    {"name": "base"},
                ]
            }
        },
    )

    depot_root = workspace / ".agents" / "skills"
    depot_root.mkdir(parents=True, exist_ok=True)
    (depot_root / "base-alpha-skill").mkdir()
    (depot_root / "extra-gamma-skill").symlink_to(extra_skill.resolve(), target_is_directory=True)

    monkeypatch.chdir(workspace)
    assert main(["skills", "status", "--json"]) == 0
    status = json.loads(capsys.readouterr().out)

    depot_status = status["depots"][0]
    assert len(depot_status["conflicts"]) == 1
    assert depot_status["conflicts"][0]["name"] == "base-alpha-skill"
    assert depot_status["conflicts"][0]["actual_entry_kind"] == "directory"
    assert len(depot_status["extra"]) == 1
    assert depot_status["extra"][0]["name"] == "extra-gamma-skill"
    assert depot_status["extra"][0]["actual_resolved_target"] == str(extra_skill.resolve())
    assert depot_status["matching"] == []
    assert depot_status["missing"] == []
    assert depot_status["broken"] == []
    assert depot_status["unsynced"] == []


def test_skills_surface_only_exposes_list_import_status_and_path(capsys) -> None:
    parser = build_parser()

    args = parser.parse_args(["skills", "status"])
    assert args.skills_command == "status"

    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["skills", "query"])

    assert excinfo.value.code == 2
    assert "invalid choice: 'query'" in capsys.readouterr().err
