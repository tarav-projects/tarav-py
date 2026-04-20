from __future__ import annotations

import json
from pathlib import Path

from agentos.cli import main


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _set_fake_agentos_home(monkeypatch, root: Path) -> Path:
    agentos_home = root / ".agentos"
    agentos_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    return agentos_home


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

    _write(
        agentos_home / "config.json",
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "skills": {"routing": routing_payload},
            },
            indent=2,
        )
        + "\n",
    )


def _create_skill(path: Path, *, description: str, type_: str | None = None) -> None:
    frontmatter_lines = [
        "---",
        f"name: {path.name}",
        f"description: {description}",
    ]
    if type_ is not None:
        frontmatter_lines.append(f"type: {type_}")
    frontmatter_lines.extend(["---", "", f"# {path.name}", ""])
    _write(path / "SKILL.md", "\n".join(frontmatter_lines))


def test_mission_templates_requires_existing_project(capsys, monkeypatch, tmp_path: Path) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(workspace)

    assert main(["mission", "templates"]) == 1
    assert capsys.readouterr().err.strip() == (
        "error: not inside an agentos project (missing .agentos/project.json); run `agentos init`"
    )


def test_mission_templates_reads_selected_imported_skills(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    workspace = tmp_path / "workspace"
    _write_project_marker(workspace)
    _create_skill(
        workspace / "skills" / "planning-template",
        description="Planning mission template",
        type_="mission.template",
    )
    _create_skill(
        workspace / "skills" / "other-skill",
        description="Not a template",
    )

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

    monkeypatch.chdir(workspace)
    assert main(["mission", "templates", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload == [
        {
            "name": "local-planning-template",
            "source": "local",
            "paths": [
                str((workspace / ".agents" / "skills" / "local-planning-template").resolve()),
                str((workspace / ".claude" / "skills" / "local-planning-template").resolve()),
            ],
            "frontmatter": {
                "name": "planning-template",
                "description": "Planning mission template",
                "type": "mission.template",
            },
        }
    ]
