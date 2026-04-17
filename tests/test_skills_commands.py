from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.cli import build_parser, main


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


def _write_global_routing_config(
    agentos_home: Path,
    *,
    imports_registry: dict[str, dict[str, object]] | None = None,
    profiles: dict[str, dict[str, object]] | None = None,
    bindings: list[dict[str, object]] | None = None,
) -> None:
    config_path = agentos_home / "config.json"
    payload = {
        "class": "agentos.global.config",
        "schema_version": 1,
        "skills": {
            "routing": {
                "imports_registry": {} if imports_registry is None else imports_registry,
                "profiles": {} if profiles is None else profiles,
                "bindings": [] if bindings is None else bindings,
            }
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


def test_skills_list_returns_authoritative_empty_catalog(capsys, monkeypatch, tmp_path: Path) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(workspace)

    assert main(["skills", "list"]) == 0
    assert capsys.readouterr().out.strip() == (
        "No routed skills are available for this caller context.\n"
        "AGENTS: Treat this result as authoritative. Do not search for skills outside `agentos skills`."
    )


def test_skills_list_uses_base_profile_when_no_binding_matches(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_skill(workspace / "skills" / "alpha-skill", description="Base alpha skill")

    _write_global_routing_config(
        agentos_home,
        imports_registry={
            "base": {"path": "skills"},
        },
        profiles={
            "base": {
                "imports": [
                    {"name": "base"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    expected_path = agentos_home / "skills-depot" / "base" / "base-alpha-skill"
    assert listed == [
        {
            "name": "base-alpha-skill",
            "description": "Base alpha skill",
            "source": "base",
            "path": str(expected_path),
        }
    ]
    assert expected_path.is_symlink()
    assert expected_path.resolve() == (workspace / "skills" / "alpha-skill").resolve()


def test_skills_list_renders_card_like_output(capsys, monkeypatch, tmp_path: Path) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_skill(workspace / "skills" / "alpha-skill", description="Base alpha skill")

    _write_global_routing_config(
        agentos_home,
        imports_registry={
            "base": {"path": "skills"},
        },
        profiles={
            "base": {
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
        f"- path: {agentos_home / 'skills-depot' / 'base' / 'base-alpha-skill'}\n"
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
            "project": {"path": "skills"},
        },
        profiles={
            "project-profile": {
                "imports": [
                    {"name": "project"},
                ]
            }
        },
        bindings=[
            {"root": str(project_root), "profile": "project-profile"},
        ],
    )

    monkeypatch.chdir(nested)
    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == [
        {
            "name": "project-alpha-skill",
            "description": "Project alpha skill",
            "source": "project",
            "path": str(agentos_home / "skills-depot" / "project-profile" / "project-alpha-skill"),
        }
    ]


def test_skills_list_uses_closest_bound_parent_context(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    parent_root = tmp_path / "workspace"
    child_root = parent_root / "child"
    deeper_root = child_root / "deeper"
    deeper_root.mkdir(parents=True, exist_ok=True)

    _create_skill(parent_root / "skills" / "alpha-skill", description="Parent alpha skill")
    _create_skill(child_root / "skills" / "beta-skill", description="Child beta skill")

    _write_global_routing_config(
        agentos_home,
        imports_registry={
            "parent": {"path": "skills"},
            "child": {"path": "skills"},
        },
        profiles={
            "parent-profile": {
                "imports": [
                    {"name": "parent"},
                ]
            },
            "child-profile": {
                "imports": [
                    {"name": "child"},
                ]
            },
        },
        bindings=[
            {"root": str(parent_root), "profile": "parent-profile"},
            {"root": str(child_root), "profile": "child-profile"},
        ],
    )

    monkeypatch.chdir(deeper_root)
    assert main(["skills", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == [
        {
            "name": "child-beta-skill",
            "description": "Child beta skill",
            "source": "child",
            "path": str(agentos_home / "skills-depot" / "child-profile" / "child-beta-skill"),
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
            "base": {
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
            "path": str(agentos_home / "skills-depot" / "base" / "override-alpha-skill"),
        }
    ]


def test_skills_path_returns_routed_symlink_path(capsys, monkeypatch, tmp_path: Path) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _create_skill(workspace / "skills" / "alpha-skill", description="Base alpha skill")

    _write_global_routing_config(
        agentos_home,
        imports_registry={
            "base": {"path": "skills"},
        },
        profiles={
            "base": {
                "imports": [
                    {"name": "base"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "path", "base-alpha-skill"]) == 0
    assert capsys.readouterr().out.strip() == str(
        agentos_home / "skills-depot" / "base" / "base-alpha-skill"
    )


def test_skills_path_returns_routed_not_found(capsys, monkeypatch, tmp_path: Path) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(workspace)

    assert main(["skills", "path", "agentos-live-note-base"]) == 1
    assert capsys.readouterr().err.strip() == (
        "error: skill not found in routed skills: agentos-live-note-base"
    )


def test_skills_profile_imports_support_mixed_registry_and_inline_entries(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    registry_root = tmp_path / "registry-source"
    inline_root = tmp_path / "inline-source"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    _create_skill(registry_root / "alpha-skill", description="Registry alpha skill")
    _create_skill(inline_root / "beta-skill", description="Inline beta skill")

    _write_global_routing_config(
        agentos_home,
        imports_registry={
            "registry": {"path": str(registry_root)},
        },
        profiles={
            "base": {
                "imports": [
                    {"name": "registry"},
                    {"name": "inline", "path": str(inline_root)},
                ]
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
            "path": str(agentos_home / "skills-depot" / "base" / "inline-beta-skill"),
        },
        {
            "name": "registry-alpha-skill",
            "description": "Registry alpha skill",
            "source": "registry",
            "path": str(agentos_home / "skills-depot" / "base" / "registry-alpha-skill"),
        },
    ]


def test_skills_profile_import_ref_errors_on_unknown_registry_entry(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    _write_global_routing_config(
        agentos_home,
        profiles={
            "base": {
                "imports": [
                    {"name": "missing"},
                ]
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["skills", "list"]) == 1
    assert capsys.readouterr().err.strip() == (
        "error: routing profile import references unknown registry entry: base/missing"
    )


def test_skills_surface_only_exposes_list_and_path(capsys) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["skills", "query"])

    assert excinfo.value.code == 2
    assert "invalid choice: 'query'" in capsys.readouterr().err
