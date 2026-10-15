"""The Tarav System Project: its active Projects, each loaded through its own harness."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest

from tarav.l2.project.system import ActiveProjectCheck, TaravSystemProject
from tarav.l3.runtime import create_runtime


@pytest.fixture(autouse=True)
def _runtime(monkeypatch):
    create_runtime()
    monkeypatch.setenv("_TARAV_IMPORT_ENTRY", "1")  # a launched child imports tarav


def _marker(root: Path, **fields) -> None:
    (root / ".tarav").mkdir(parents=True, exist_ok=True)
    (root / ".tarav/project.json").write_text(json.dumps(
        {"project_id": "20c26be7-a8e5-4974-9ec0-0b5a3a125a94",
         "created_at": "2026-10-15T00:00:00Z", **fields}))


def test_each_active_project_is_loaded_through_its_own_harness(tmp_path: Path) -> None:
    loads = tmp_path / "loads"
    loads.mkdir()
    # this test's own environment has tarav installed: the Project's harness names it
    _marker(loads, type="Tarav.Project",
            harness={"environment": os.path.relpath(sys.prefix, loads),
                     "type": "tarav.l2.project:Project"})
    bare = tmp_path / "bare"
    bare.mkdir()
    _marker(bare)
    system = tmp_path / "system"
    system.mkdir()
    _marker(system, active=[str(loads), str(bare), str(tmp_path / "gone")])
    project = TaravSystemProject.from_path(system)

    assert project.active_paths() == (loads.resolve(), bare.resolve(), (tmp_path / "gone").resolve())
    results = {Path(result.check.path).name: result
               for result in project.checks.run().results_of(ActiveProjectCheck)}
    assert {name: [type(poi).__name__ for poi in result.pois()]
            for name, result in results.items()} == {
        "loads": [], "bare": ["ActiveProjectDoesNotLoad"], "gone": ["ActiveProjectMissing"]}
    assert "declares no harness" in results["bare"].pois()[0].details["error"]
    assert all(result.status == "completed" for result in results.values())


def test_init_creates_the_system_project_once(tmp_path: Path, monkeypatch) -> None:
    from tarav.l0._core.errors import CliError
    from tarav.l1.project import TaravProject
    from tarav.l2.project import system as system_module
    from tarav.l3.project.system import init_system

    monkeypatch.setattr(system_module, "default_tarav_data_root", lambda: tmp_path / "tarav")
    source = Path(__file__).resolve().parents[1]  # this tarav-py checkout
    init_system(tarav_source=source, sync=False)

    root = tmp_path / "tarav" / "system"
    record = json.loads((root / ".tarav/project.json").read_text())
    assert record["type"]["label"] == "Project.tarav_system_harness.SystemProject"
    assert record["harness"] == {"environment": ".tarav/env",
                                 "type": "tarav_system_harness.project:SystemProject"}
    assert record["active"] == []
    assert (root / ".git").is_dir() and "/.tarav/env/" in (root / ".gitignore").read_text()
    # its own Type, installed in its environment, is a TaravSystemProject
    monkeypatch.syspath_prepend(str(root / ".tarav/src"))
    project = TaravProject.load_project(path=root)
    assert isinstance(project, TaravSystemProject) and type(project) is not TaravSystemProject
    with pytest.raises(CliError, match="already has a System Project"):
        init_system(tarav_source=source, sync=False)
