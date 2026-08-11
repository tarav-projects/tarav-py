from __future__ import annotations

from pathlib import Path

from agentos.testing import AgentosTestEnvironment, write_project_marker
from agentos.cli.cli import main
from _helpers import captured_json, write_text_file as _write


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
    environment = AgentosTestEnvironment.create(tmp_path / "home")
    environment.apply_environment(monkeypatch.setenv)
    workspace = tmp_path / "workspace"
    write_project_marker(workspace)
    _create_skill(
        workspace / "skills" / "planning-template",
        description="Planning mission template",
        type_="mission.template",
    )
    _create_skill(
        workspace / "skills" / "other-skill",
        description="Not a template",
    )

    environment.write_global_config(
        skills={
            "routing": {
                "sources": {},
                "profiles": {
                    "default": {
                        "sources": [
                            {"name": "local", "path": "skills"},
                        ]
                    }
                },
            }
        },
    )

    monkeypatch.chdir(workspace)
    assert main(["mission", "templates", "--project", "--json"]) == 0
    payload = captured_json(capsys)

    assert payload == [
        {
            "name": "local-planning-template",
            "source": "local",
            "paths": [
                str(
                    (
                        workspace / ".agents" / "skills" / "local-planning-template"
                    ).resolve()
                ),
                str(
                    (
                        workspace / ".claude" / "skills" / "local-planning-template"
                    ).resolve()
                ),
            ],
            "frontmatter": {
                "name": "planning-template",
                "description": "Planning mission template",
                "type": "mission.template",
            },
        }
    ]
