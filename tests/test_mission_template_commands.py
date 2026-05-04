from __future__ import annotations

import json
from pathlib import Path

from agentos.cli import main
from _helpers import set_fake_agentos_home as _set_fake_agentos_home, write_global_routing_config as _write_global_routing_config, write_project_marker as _write_project_marker, write_text_file as _write


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
    assert main(["mission", "templates", "--project", "--json"]) == 0
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
