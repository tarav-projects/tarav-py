"""The Tarav System Project: its active Projects, each loaded through its own harness."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest

from tarav.l0.project import project_id
from tarav.l2.project.system import ActiveProjectCheck, TaravSystemProject
from tarav.l3.runtime import create_runtime


@pytest.fixture(autouse=True)
def _runtime(monkeypatch, tmp_path):
    create_runtime()
    monkeypatch.setenv("_TARAV_IMPORT_ENTRY", "1")  # a launched child imports tarav
    # System checks must never inspect the real machine's Attic in a unit test.
    from tarav.l1.attic import model as attic_model
    monkeypatch.setattr(attic_model, "default_tarav_data_root", lambda: tmp_path / "tarav-data")
    import tarav.l1.archive as archive_module
    monkeypatch.setattr(archive_module, "default_archive_root", lambda: tmp_path / "doi-registry")


def _marker(root: Path, **fields) -> None:
    (root / ".tarav").mkdir(parents=True, exist_ok=True)
    (root / ".tarav/project.json").write_text(json.dumps(
        {"project_id": "20c26be7-a8e5-4974-9ec0-0b5a3a125a94",
         "created_at": "2026-10-15T00:00:00Z", **fields}))


# tarav.breadcrumb 8df042c52f14
def test_system_owns_locator_actions_and_rechecks_close_them(tmp_path, monkeypatch):
    from tarav.l1.archive import Archive
    from tarav.l1.archive.model import DOI, LocalLocator

    missing = tmp_path / "resource"
    archive = Archive.create(tmp_path / "doi-registry")
    doi = archive.register(DOI(locators=[LocalLocator(missing)]))
    system = tmp_path / "system"
    _marker(system)
    project = TaravSystemProject.from_path(system)
    project.status()
    actions = [run for run in project.actions.list()
               if run.data["action"] == "Tarav.Archive.Locator.Missing.Action"]
    assert len(actions) == 1
    action = actions[0]
    assert action.state == "running"
    assert action.data["project"]["id"] == str(project.id)
    assert action.data["event"]["poi"]["situation"]["doi"] == doi.id

    # Missing registry is not a completed scan: do not close earlier findings.
    marker = archive.store.marker.read_bytes()
    archive.store.marker.unlink()
    project.status()
    assert next(run for run in project.actions.list() if run.id == action.id).state == "running"
    archive.store.marker.write_bytes(marker)

    # Another host cannot establish local availability either.
    with monkeypatch.context() as remote_host:
        remote_host.setattr("tarav.l1.archive.checks.socket.gethostname", lambda: "another-host")
        project.status()
        assert next(run for run in project.actions.list() if run.id == action.id).state == "running"
    missing.write_text("restored")
    project.status()
    updated = next(run for run in project.actions.list() if run.id == action.id)
    assert updated.state == "closed" and updated.exit == "gone"


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
    # a Project is named by its UUID; a missing one only has its active path
    assert results["bare"].pois()[0].situation == {"project": project_id(bare)}
    assert results["gone"].pois()[0].situation == {"path": str((tmp_path / "gone").resolve())}
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


# tarav.breadcrumb 5ca1143617e7
def test_system_composes_attic_checks_and_actions_close_after_metadata_repair(tmp_path, monkeypatch):
    from tarav.l1.attic import model as attic_model
    from tarav.l1.attic.checks import ManifestMissing

    monkeypatch.setattr(attic_model, "default_tarav_data_root", lambda: tmp_path)
    missing = tmp_path / "attic/deposits/unfinished"
    missing.mkdir(parents=True)
    system = tmp_path / "system"
    _marker(system)
    project = TaravSystemProject.from_path(system)
    project.status()
    actions = project.actions.list()
    attic_actions = [run for run in actions
                    if run.data["event"]["poi"]["type"] == "Tarav.Attic.Manifest.Missing.POI"]
    assert len(attic_actions) == 1
    action = attic_actions[0]
    assert action.state == "running"
    assert action.data["action"] == "Tarav.Attic.Manifest.Missing.Action"
    assert action.data["event"]["poi"]["situation"] == {
        "root": str(tmp_path / "attic"), "deposit": "unfinished"}
    original = Path.iterdir

    def unavailable(path):
        if path == tmp_path / "attic/deposits":
            raise PermissionError("Attic temporarily unavailable")
        return original(path)

    with monkeypatch.context() as unavailable_depot:
        unavailable_depot.setattr(Path, "iterdir", unavailable)
        project.status()
    still_open = next(run for run in project.actions.list() if run.id == action.id)
    assert still_open.state == "running"
    (missing / "deposit.json").write_text(json.dumps({
        "class": "tarav.attic.deposit", "schema_version": 1,
        "uuid": "21cfc4b7-3c13-4d76-ad6a-63ef98c1929f", "deposited_at": "2026-10-19T00:00:00Z",
        "sources": ["/old"], "material": "material", "reason": "Displaced files",
        "dependency_status": "disconnected"}))
    project.status()
    assert not [poi for poi in project.checks.run().pois() if isinstance(poi, ManifestMissing)]
    updated = next(run for run in project.actions.list() if run.id == action.id)
    assert updated.state == "closed" and updated.exit == "gone"
