"""Project agents bootstrap, Skillware source, and typed findings."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from tarav.l0.kernel import entity
from tarav.l1.project import TaravProject
from tarav.l1.project.agents import (
    AgentsAliasPOI,
    AgentsMdProductPOI,
    ProjectSystemPrompt,
    ProjectSystemPromptPOI,
    PROMPT_SOURCE,
    TaravSystemPrompt,
    TaravSystemPromptPOI,
)
from tarav.l1.skw.document import DocumentRecord, project_document
from tarav.l3.runtime import create_runtime


def _project(root: Path, **agents: object) -> TaravProject:
    marker = root / ".tarav/project.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({
        "class": "agentos.project", "schema_version": 1,
        "project_id": str(uuid4()), "agents": agents,
    }))
    return TaravProject.from_path(root)


def _source(project: TaravProject, *, tarav=True, authored=True) -> dict:
    data = {
        "type": entity(DocumentRecord).name,
        "schema_version": 1,
        "output": project.agents.agents_md.main.as_posix(),
        "blocks": [],
    }
    if tarav:
        data["blocks"].append({
            "type": entity(TaravSystemPrompt).name,
            "id": str(uuid4()), "label": "tarav", "content": None,
        })
    if authored:
        data["blocks"].append({
            "type": entity(ProjectSystemPrompt).name,
            "id": str(uuid4()), "label": "project", "content": ["# Local rules"],
        })
    source = project.agents.agents_md.source
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(json.dumps(data))
    return data


def _pois(project: TaravProject):
    return tuple(project.checks.run().pois())


# tarav.breadcrumb 7356d12f7524e6827f2a3d5459a86ed97566793b82d37fef9bd9367eeb16e93a
def test_default_bootstrap_reports_missing_source_and_opt_out(tmp_path: Path) -> None:
    project = _project(tmp_path)
    agents = project.agents.agents_md
    assert agents.path == tmp_path / "AGENTS.md"
    assert agents.source == tmp_path / ".tarav/skillware/src/AGENTS.skw.json"
    pois = _pois(project)
    assert any(isinstance(p, TaravSystemPromptPOI) and p.code == "no-source"
               for p in pois)
    assert any(isinstance(p, ProjectSystemPromptPOI) and p.code == "no-source"
               for p in pois)

    opted_out = _project(tmp_path, tarav_system_prompt=False,
                         project_system_prompt=False)
    assert not any(isinstance(p, (TaravSystemPromptPOI, ProjectSystemPromptPOI))
                   for p in _pois(opted_out))


def test_custom_depot_produce_compile_and_drift(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _source(project)
    agents = project.agents.agents_md
    document = project_document("AGENTS.skw.json", project=tmp_path,
                                depot=".tarav/skillware",
                                registry=create_runtime().records)
    assert document.source == agents.source
    assert document.depot == agents.depot
    assert document.produce("tarav")["content"] == PROMPT_SOURCE.read_text().splitlines()
    document = agents.document()
    assert document.block("tarav").get("content") == PROMPT_SOURCE.read_text().splitlines()
    assert document.compile()["written"]
    assert _pois(project) == ()
    agents.path.write_text("changed\n")
    assert any(isinstance(p, AgentsMdProductPOI) and p.code == "product-drift"
               for p in _pois(project))


def test_missing_and_stale_prompt_blocks(tmp_path: Path) -> None:
    project = _project(tmp_path)
    data = _source(project, tarav=False)
    assert any(isinstance(p, TaravSystemPromptPOI) and p.code == "missing"
               for p in _pois(project))
    data["blocks"].append({
        "type": entity(TaravSystemPrompt).name, "id": str(uuid4()),
        "label": "tarav", "content": ["old"],
    })
    project.agents.agents_md.source.write_text(json.dumps(data))
    assert any(isinstance(p, TaravSystemPromptPOI) and p.code == "stale"
               for p in _pois(project))

    data["blocks"][0]["content"] = []
    project.agents.agents_md.source.write_text(json.dumps(data))
    assert any(isinstance(p, ProjectSystemPromptPOI) and p.code == "empty"
               for p in _pois(project))


def test_declared_alias_must_link_to_main_file(tmp_path: Path) -> None:
    project = _project(tmp_path, aliases=["CLAUDE.md"])
    _source(project)
    agents = project.agents.agents_md
    agents.document().produce("tarav")
    agents.document().compile()
    alias = tmp_path / "CLAUDE.md"
    assert any(isinstance(p, AgentsAliasPOI) and p.code == "missing"
               for p in _pois(project))
    alias.write_text("copy")
    assert any(isinstance(p, AgentsAliasPOI) and p.code == "not-symlink"
               for p in _pois(project))
    alias.unlink()
    other = tmp_path / "other.md"
    other.write_text("other")
    alias.symlink_to(other)
    assert any(isinstance(p, AgentsAliasPOI) and p.code == "wrong-target"
               for p in _pois(project))
    alias.unlink()
    alias.symlink_to(agents.path)
    assert _pois(project) == ()


@pytest.mark.parametrize("main", ["../AGENTS.md", "/tmp/AGENTS.md", "x/../AGENTS.md"])
def test_agents_file_must_stay_inside_project(tmp_path: Path, main: str) -> None:
    project = _project(tmp_path, main=main)
    with pytest.raises(ValueError, match="inside the Project"):
        project.agents.agents_md
