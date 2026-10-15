"""The check of a Project's project.json and config.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.l1.project.files import ProjectFilesCheck
from tarav.l2.project import Project
from tarav.l3.runtime import create_runtime

HARNESS = {"environment": "env", "type": "tarav.l2.project:Project"}


@pytest.fixture(autouse=True)
def _runtime():
    create_runtime()  # registers the config sections of the workflows


def _project(root: Path, *, config: dict | None = None, **fields) -> Project:
    (root / ".tarav").mkdir(parents=True, exist_ok=True)
    record = {"type": "Tarav.Project", "project_id": "20c26be7-a8e5-4974-9ec0-0b5a3a125a94",
              "created_at": "2026-10-15T00:00:00Z", "harness": HARNESS, **fields}
    (root / ".tarav/project.json").write_text(json.dumps(
        {key: value for key, value in record.items() if value is not None}))
    (root / ".tarav/config.json").write_text(json.dumps(config or {}))
    return Project.from_path(root)


def _found(project: Project) -> list[tuple[str, dict]]:
    result = ProjectFilesCheck(project).run()
    assert result.status == "completed"
    return [(type(poi).__name__, {key: value for key, value in poi.situation.items()
                                  if key != "project"}) for poi in result.pois()]


def test_a_project_whose_files_match_their_models_raises_nothing(tmp_path: Path) -> None:
    (tmp_path / "env").mkdir()
    (tmp_path / "env/pyvenv.cfg").write_text("")
    project = _project(tmp_path, config={"agents": {"package_skill": "tarav-pkg"},
                                         "diagram": {"main_model": "m"}})
    assert _found(project) == []


def test_each_case_is_its_own_poi(tmp_path: Path) -> None:
    project = _project(tmp_path, harness=None, schema_version=1,
                       config={"index": {"workspace": "x"}, "agents": {"main": 3}})
    assert _found(project) == [
        ("UnknownProjectField", {"file": "project.json", "field": "schema_version"}),
        ("NoHarness", {}),
        ("InvalidConfigSection", {"file": "config.json", "section": "agents"}),
        ("UnknownConfigSection", {"file": "config.json", "section": "index"}),
    ]


def test_the_harness_must_start_the_project_as_its_type(tmp_path: Path) -> None:
    project = _project(tmp_path, harness={"environment": "env",
                                          "type": "tarav.l2.project.root:RootProject"})
    assert _found(project) == [
        ("HarnessEnvironmentMissing", {"environment": "env"}),
        ("HarnessTypeMismatch", {"harness_type": "tarav.l2.project.root:RootProject",
                                 "record_type": "Tarav.Project"}),
    ]
    project = _project(tmp_path, harness={"environment": "env", "type": "nowhere.at.all:X"})
    [_, (name, situation)] = _found(project)
    assert (name, situation["harness_type"]) == ("HarnessTypeMismatch", "nowhere.at.all:X")
