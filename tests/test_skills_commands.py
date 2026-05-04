from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli import build_parser, main as _agentos_main
from _helpers import set_fake_agentos_home as _set_fake_agentos_home, write_global_routing_config as _write_global_routing_config, write_project_marker as _write_project_marker

NO_SELECTED_SKILLS_MESSAGE = "No skills are selected for import into this project target."
DEFAULT_DEPOT_PATHS = (Path(".agents/skills"), Path(".claude/skills"))


def main(argv: list[str]) -> int:
    if (
        len(argv) >= 2
        and argv[0] == "skills"
        and argv[1] != "--help"
        and "--help" not in argv
        and "--project" not in argv
    ):
        return _agentos_main([*argv, "--project"])
    return _agentos_main(argv)


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


def _write_project_config(
    project_root: Path,
    *,
    profile: str | None = None,
    export_packages: dict[str, list[dict[str, object]]] | None = None,
) -> None:
    config_path = project_root / ".agentos" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "class": "agentos.project.config",
        "schema_version": 1,
    }
    skills_payload: dict[str, object] = {}
    if profile is not None:
        skills_payload["routing"] = {"profile": profile}
    if export_packages is not None:
        skills_payload["exports"] = {
            "packages": export_packages,
        }
    if skills_payload:
        payload["skills"] = skills_payload
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


def test_skills_list_requires_explicit_project(capsys, monkeypatch, tmp_path: Path) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)
    monkeypatch.chdir(workspace)

    assert _agentos_main(["skills", "list"]) == 1
    assert "agentos skills requires --project or --project-base" in capsys.readouterr().err


def test_skills_list_accepts_project_base(capsys, monkeypatch, tmp_path: Path) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)
    monkeypatch.chdir(workspace)

    assert _agentos_main(["skills", "list", "--project-base", "workspace"]) == 0
    assert NO_SELECTED_SKILLS_MESSAGE in capsys.readouterr().out


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
    assert main(["skills", "list", "--project", str(workspace), "--json"]) == 0
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
    assert main(["skills", "list", "--project", str(project_root), "--json"]) == 0
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
    assert main(["skills", "list", "--project", str(child_root), "--json"]) == 0
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
    assert main(["skills", "list", "--project", str(project_root), "--json"]) == 0
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


def test_project_source_imports_default_project_skills_root(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_project = tmp_path / "source-project"
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)
    _write_project_marker(source_project)
    _create_skill(source_project / "skills" / "alpha-skill", description="Project alpha skill")

    _write_global_routing_config(
        agentos_home,
        sources={
            "project": {"project": str(source_project)},
        },
        profiles={
            "default": {
                "sources": [
                    {"name": "project"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == [
        {
            "name": "project-alpha-skill",
            "description": "Project alpha skill",
            "source": "project",
            "paths": _resolved_skill_paths(workspace, "project-alpha-skill"),
        }
    ]


def test_project_source_export_package_supports_implicit_local_entries(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_project = tmp_path / "source-project"
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)
    _write_project_marker(source_project)
    _write_project_config(
        source_project,
        export_packages={
            "runtime": [
                {"include": ["project-alpha-skill"]},
            ],
        },
    )
    _create_skill(source_project / "skills" / "alpha-skill", description="Project alpha skill")
    _create_skill(source_project / "skills" / "beta-skill", description="Project beta skill")

    _write_global_routing_config(
        agentos_home,
        sources={
            "project": {"project": str(source_project)},
        },
        profiles={
            "default": {
                "sources": [
                    {"name": "project:runtime"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == [
        {
            "name": "project-alpha-skill",
            "description": "Project alpha skill",
            "source": "project",
            "paths": _resolved_skill_paths(workspace, "project-alpha-skill"),
        }
    ]


def test_project_source_export_package_supports_explicit_local_entries_and_consumer_filters(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_project = tmp_path / "source-project"
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)
    _write_project_marker(source_project)
    _write_project_config(
        source_project,
        export_packages={
            "runtime": [
                {
                    "name": "project",
                    "include": ["project-alpha-skill", "project-beta-skill"],
                },
            ],
        },
    )
    _create_skill(source_project / "skills" / "alpha-skill", description="Project alpha skill")
    _create_skill(source_project / "skills" / "beta-skill", description="Project beta skill")
    _create_skill(source_project / "skills" / "gamma-skill", description="Project gamma skill")

    _write_global_routing_config(
        agentos_home,
        sources={
            "project": {"project": str(source_project)},
        },
        profiles={
            "default": {
                "sources": [
                    {
                        "name": "project:runtime",
                        "exclude": ["project-beta-skill"],
                    },
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == [
        {
            "name": "project-alpha-skill",
            "description": "Project alpha skill",
            "source": "project",
            "paths": _resolved_skill_paths(workspace, "project-alpha-skill"),
        }
    ]


@pytest.mark.parametrize(
    "variant, expected_error",
    [
        ("missing_package", "error: routing source export package not found: project:missing"),
        ("not_project_backed", "error: routing source export package requires project-backed source: base:runtime"),
    ],
)
def test_project_source_export_rejects_invalid_configs(
    capsys,
    monkeypatch,
    tmp_path: Path,
    variant: str,
    expected_error: str,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)

    if variant == "missing_package":
        source_project = tmp_path / "source-project"
        _write_project_marker(source_project)
        _write_project_config(source_project, export_packages={})
        _create_skill(source_project / "skills" / "alpha-skill", description="Project alpha skill")
        _write_global_routing_config(
            agentos_home,
            sources={
                "project": {"project": str(source_project)},
            },
            profiles={
                "default": {
                    "sources": [
                        {"name": "project:missing"},
                    ]
                }
            },
        )
    elif variant == "not_project_backed":
        source_root = tmp_path / "source"
        _create_skill(source_root / "alpha-skill", description="Alpha skill")
        _write_global_routing_config(
            agentos_home,
            sources={
                "base": {"path": str(source_root)},
            },
            profiles={
                "default": {
                    "sources": [
                        {"name": "base:runtime"},
                    ]
                }
            },
        )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list"]) == 1
    assert capsys.readouterr().err.strip() == expected_error


def test_project_source_requires_project_marker(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_project = tmp_path / "source-project"
    workspace = tmp_path / "workspace"
    source_project.mkdir(parents=True, exist_ok=True)
    _create_local_agents_context(workspace)

    _write_global_routing_config(
        agentos_home,
        sources={
            "project": {"project": str(source_project)},
        },
        profiles={
            "default": {
                "sources": [
                    {"name": "project"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list"]) == 1
    stderr = capsys.readouterr().err.strip()
    assert stderr.startswith("error: global config field skills.routing.sources.project")
    assert "is not an agentos project" in stderr
    assert ".agentos/project.json" in stderr


def test_project_source_export_packages_detect_cycles(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_project = tmp_path / "source-project"
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)
    _write_project_marker(source_project)
    _write_project_config(
        source_project,
        export_packages={
            "runtime": [
                {"name": "project:missions"},
            ],
            "missions": [
                {"name": "project:runtime"},
            ],
        },
    )
    _create_skill(source_project / "skills" / "alpha-skill", description="Project alpha skill")

    _write_global_routing_config(
        agentos_home,
        sources={
            "project": {"project": str(source_project)},
        },
        profiles={
            "default": {
                "sources": [
                    {"name": "project:runtime"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list"]) == 1
    assert capsys.readouterr().err.strip() == (
        "error: routing source cycle detected: project:runtime -> project:missions -> project:runtime"
    )


def test_skills_source_entry_include_exclude_filters_and_exclude_wins(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_root = tmp_path / "source"
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)

    _create_skill(source_root / "alpha-skill", description="Alpha skill")
    _create_skill(source_root / "beta-skill", description="Beta skill")
    _create_skill(source_root / "gamma-skill", description="Gamma skill")

    _write_global_routing_config(
        agentos_home,
        sources={
            "base": {"path": str(source_root)},
        },
        profiles={
            "default": {
                "sources": [
                    {
                        "name": "base",
                        "include": ["base-alpha-skill", "base-beta-skill", "gamma-skill"],
                        "exclude": ["base-beta-skill", "gamma-skill"],
                    },
                ],
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == [
        {
            "name": "base-alpha-skill",
            "description": "Alpha skill",
            "source": "base",
            "paths": _resolved_skill_paths(workspace, "base-alpha-skill"),
        }
    ]


def test_skills_package_entry_filters_apply_to_expanded_sources(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    registry_root = tmp_path / "registry-source"
    docs_root = tmp_path / "docs-source"
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)

    _create_skill(registry_root / "alpha-skill", description="Registry alpha skill")
    _create_skill(registry_root / "beta-skill", description="Registry beta skill")
    _create_skill(docs_root / "guide-skill", description="Docs guide skill")

    _write_global_routing_config(
        agentos_home,
        sources={
            "registry": {"path": str(registry_root)},
            "docs": {"path": str(docs_root)},
            "core": {
                "package": [
                    {"name": "registry"},
                    {"name": "docs"},
                ]
            },
        },
        profiles={
            "default": {
                "sources": [
                    {
                        "name": "core",
                        "include": ["registry-alpha-skill", "docs-guide-skill"],
                        "exclude": ["docs-guide-skill"],
                    },
                ],
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == [
        {
            "name": "registry-alpha-skill",
            "description": "Registry alpha skill",
            "source": "registry",
            "paths": _resolved_skill_paths(workspace, "registry-alpha-skill"),
        }
    ]


def test_skills_filters_compose_through_registry_and_inline_packages(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    registry_root = tmp_path / "registry-source"
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)

    _create_skill(registry_root / "alpha-skill", description="Registry alpha skill")
    _create_skill(registry_root / "beta-skill", description="Registry beta skill")
    _create_skill(registry_root / "gamma-skill", description="Registry gamma skill")

    _write_global_routing_config(
        agentos_home,
        sources={
            "registry": {
                "path": str(registry_root),
                "exclude": ["registry-gamma-skill"],
            },
            "core": {
                "package": [
                    {
                        "name": "registry",
                        "include": [
                            "registry-alpha-skill",
                            "registry-beta-skill",
                            "registry-gamma-skill",
                        ],
                    },
                ],
                "exclude": ["registry-beta-skill"],
            },
        },
        profiles={
            "default": {
                "sources": [
                    {
                        "package": [
                            {"name": "core"},
                        ],
                        "include": ["registry-alpha-skill", "registry-beta-skill"],
                    },
                ],
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == [
        {
            "name": "registry-alpha-skill",
            "description": "Registry alpha skill",
            "source": "registry",
            "paths": _resolved_skill_paths(workspace, "registry-alpha-skill"),
        }
    ]


def test_skills_filter_rejects_unknown_skill_names(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_root = tmp_path / "source"
    workspace = tmp_path / "workspace"
    _create_local_agents_context(workspace)
    _create_skill(source_root / "alpha-skill", description="Alpha skill")

    _write_global_routing_config(
        agentos_home,
        sources={
            "base": {"path": str(source_root)},
        },
        profiles={
            "default": {
                "sources": [
                    {
                        "name": "base",
                        "include": ["missing-skill"],
                    },
                ],
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list"]) == 1
    assert capsys.readouterr().err.strip() == (
        "error: global config field skills.routing.profiles.default.sources[0].include "
        "references unknown skill: missing-skill"
    )


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
    expected_agents_depot = workspace / ".agents" / "skills"
    expected_claude_depot = workspace / ".claude" / "skills"
    expected_agents_path = workspace / ".agents" / "skills" / "base-alpha-skill"
    expected_claude_path = workspace / ".claude" / "skills" / "base-alpha-skill"
    assert not expected_agents_path.exists()
    assert not expected_claude_path.exists()

    assert main(["skills", "import"]) == 0
    out = capsys.readouterr().out

    assert "Skills import complete" in out
    assert "- mode: depot-linking" in out
    assert "- sync: sync" in out
    assert "- catalog: 1" in out
    assert "- depots: 2" in out
    assert f"- global depot: {agentos_home / 'skills' / 'depots'}" in out
    assert f"Depot: {workspace / '.agents' / 'skills'}" in out
    assert f"Depot: {workspace / '.claude' / 'skills'}" in out
    assert "- created: 1" in out
    assert expected_agents_depot.is_symlink()
    assert expected_claude_depot.is_symlink()
    assert expected_agents_depot.resolve() == expected_claude_depot.resolve()
    assert expected_agents_depot.resolve().parent == agentos_home / "skills" / "depots"
    assert expected_agents_path.is_symlink()
    assert expected_agents_path.resolve() == source_skill.resolve()
    assert expected_claude_path.is_symlink()
    assert expected_claude_path.resolve() == source_skill.resolve()


def test_skills_import_flat_linking_materializes_project_skill_depots(
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
    expected_agents_depot = workspace / ".agents" / "skills"
    expected_claude_depot = workspace / ".claude" / "skills"
    expected_agents_path = expected_agents_depot / "base-alpha-skill"
    expected_claude_path = expected_claude_depot / "base-alpha-skill"

    assert main(["skills", "import", "--mode", "flat-linking"]) == 0
    out = capsys.readouterr().out

    assert "Skills import complete" in out
    assert "- mode: flat-linking" in out
    assert "- sync: sync" in out
    assert expected_agents_depot.is_dir()
    assert not expected_agents_depot.is_symlink()
    assert expected_claude_depot.is_dir()
    assert not expected_claude_depot.is_symlink()
    assert expected_agents_path.is_symlink()
    assert expected_agents_path.resolve() == source_skill.resolve()
    assert expected_claude_path.is_symlink()
    assert expected_claude_path.resolve() == source_skill.resolve()


def test_skills_import_depot_linking_refreshes_shared_global_depot(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_root = tmp_path / "source-skills"
    alpha_skill = source_root / "alpha-skill"
    _create_skill(alpha_skill, description="Base alpha skill")
    workspace_a = tmp_path / "workspace-a"
    workspace_b = tmp_path / "workspace-b"
    _create_local_agents_context(workspace_a)
    _create_local_agents_context(workspace_b)

    _write_global_routing_config(
        agentos_home,
        sources={
            "base": {"path": str(source_root)},
        },
        profiles={
            "default": {
                "depots": [".agents/skills"],
                "sources": [
                    {"name": "base"},
                ],
            }
        },
    )

    monkeypatch.chdir(workspace_a)
    assert main(["skills", "import"]) == 0
    capsys.readouterr()
    depot_a = workspace_a / ".agents" / "skills"
    global_depot = depot_a.resolve()
    assert depot_a.is_symlink()
    assert global_depot.parent == agentos_home / "skills" / "depots"
    assert (depot_a / "base-alpha-skill").resolve() == alpha_skill.resolve()

    monkeypatch.chdir(workspace_b)
    assert main(["skills", "import"]) == 0
    capsys.readouterr()
    depot_b = workspace_b / ".agents" / "skills"
    assert depot_b.is_symlink()
    assert depot_b.resolve() == global_depot

    beta_skill = source_root / "beta-skill"
    _create_skill(beta_skill, description="Base beta skill")
    assert not (depot_a / "base-beta-skill").exists()

    assert main(["skills", "import"]) == 0
    capsys.readouterr()

    assert depot_b.resolve() == global_depot
    assert (depot_b / "base-beta-skill").is_symlink()
    assert (depot_b / "base-beta-skill").resolve() == beta_skill.resolve()
    assert (depot_a / "base-beta-skill").is_symlink()
    assert (depot_a / "base-beta-skill").resolve() == beta_skill.resolve()


def test_skills_import_depot_linking_rejects_unmanaged_project_depot(
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
                ],
            }
        },
    )

    depot_root = workspace / ".agents" / "skills"
    depot_root.mkdir(parents=True, exist_ok=True)
    (depot_root / "notes.txt").write_text("user data\n", encoding="utf-8")

    monkeypatch.chdir(workspace)
    assert main(["skills", "import"]) == 1
    stderr = capsys.readouterr().err

    assert "error: skills depot path cannot be replaced safely:" in stderr
    assert depot_root.is_dir()
    assert not depot_root.is_symlink()
    assert (depot_root / "notes.txt").read_text(encoding="utf-8") == "user data\n"


def test_skills_import_depot_linking_force_overwrites_project_depot(
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
                ],
            }
        },
    )

    depot_root = workspace / ".agents" / "skills"
    depot_root.mkdir(parents=True, exist_ok=True)
    (depot_root / "notes.txt").write_text("user data\n", encoding="utf-8")

    monkeypatch.chdir(workspace)
    assert main(["skills", "import", "--force"]) == 0
    out = capsys.readouterr().out

    assert "- mode: depot-linking" in out
    assert "- sync: force" in out
    assert depot_root.is_symlink()
    assert depot_root.resolve().parent == agentos_home / "skills" / "depots"
    assert not (depot_root / "notes.txt").exists()
    assert (depot_root / "base-alpha-skill").is_symlink()
    assert (depot_root / "base-alpha-skill").resolve() == source_skill.resolve()


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
    assert main(["skills", "import", "--force", "--mode", "flat-linking"]) == 0
    out = capsys.readouterr().out

    assert "Skills import complete" in out
    assert "- mode: flat-linking" in out
    assert "- sync: force" in out
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
    assert main(["skills", "import", "--force", "--mode", "flat-linking"]) == 1
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
    assert main(["skills", "import", "--force", "--mode", "flat-linking"]) == 1
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


@pytest.mark.parametrize(
    "state_id",
    ["missing", "broken", "unsynced", "conflicting_and_extra"],
)
def test_skills_status_reports_depot_states(
    capsys,
    monkeypatch,
    tmp_path: Path,
    state_id: str,
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

    depot_root = workspace / ".agents" / "skills"

    if state_id == "broken":
        depot_root.mkdir(parents=True, exist_ok=True)
        broken_target = workspace / "skills" / "missing-skill"
        (depot_root / "base-alpha-skill").symlink_to(broken_target, target_is_directory=True)
    elif state_id == "unsynced":
        wrong_skill = workspace / "other-skills" / "beta-skill"
        _create_skill(wrong_skill, description="Wrong beta skill")
        depot_root.mkdir(parents=True, exist_ok=True)
        (depot_root / "base-alpha-skill").symlink_to(wrong_skill.resolve(), target_is_directory=True)
    elif state_id == "conflicting_and_extra":
        extra_skill = workspace / "extra-skills" / "gamma-skill"
        _create_skill(extra_skill, description="Extra gamma skill")
        depot_root.mkdir(parents=True, exist_ok=True)
        (depot_root / "base-alpha-skill").mkdir()
        (depot_root / "extra-gamma-skill").symlink_to(extra_skill.resolve(), target_is_directory=True)

    monkeypatch.chdir(workspace)
    assert main(["skills", "status", "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    depot_status = status["depots"][0]

    if state_id == "missing":
        assert len(depot_status["missing"]) == 1
        assert depot_status["missing"][0]["name"] == "base-alpha-skill"
        assert depot_status["missing"][0]["expected_source_path"] == str(source_skill.resolve())
        assert depot_status["matching"] == []
        assert depot_status["broken"] == []
        assert depot_status["unsynced"] == []
        assert depot_status["conflicts"] == []
        assert depot_status["extra"] == []
    elif state_id == "broken":
        assert len(depot_status["broken"]) == 1
        assert depot_status["broken"][0]["name"] == "base-alpha-skill"
        assert depot_status["broken"][0]["actual_resolved_target"] is None
        assert depot_status["matching"] == []
        assert depot_status["missing"] == []
        assert depot_status["unsynced"] == []
        assert depot_status["conflicts"] == []
        assert depot_status["extra"] == []
    elif state_id == "unsynced":
        wrong_skill = workspace / "other-skills" / "beta-skill"
        assert len(depot_status["unsynced"]) == 1
        assert depot_status["unsynced"][0]["name"] == "base-alpha-skill"
        assert depot_status["unsynced"][0]["actual_resolved_target"] == str(wrong_skill.resolve())
        assert depot_status["matching"] == []
        assert depot_status["missing"] == []
        assert depot_status["broken"] == []
        assert depot_status["conflicts"] == []
        assert depot_status["extra"] == []
    elif state_id == "conflicting_and_extra":
        extra_skill = workspace / "extra-skills" / "gamma-skill"
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
