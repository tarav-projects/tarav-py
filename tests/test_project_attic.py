"""Project checks discover local Attic metadata without consuming its material."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from tarav.l0._core.errors import CliError
from tarav.l1.attic.checks import ManifestMissing, ManifestCheck
from tarav.l1.project.files import InvalidConfigSection, ProjectFilesCheck
from tarav.l2.project import Project
from tarav.l2.project.attic import AtticLoadCheck
from tarav.l2.project.root import RootProject
from tarav.l3.runtime import create_runtime


@pytest.fixture(autouse=True)
def runtime():
    create_runtime()


def project_at(root, cls=Project, config=None, **fields):
    (root / ".tarav").mkdir(parents=True)
    (root / ".tarav/project.json").write_text(json.dumps({
        "type": "Tarav.Project", "project_id": str(uuid4()),
        "created_at": "2026-10-22T00:00:00Z", **fields}))
    if config is not None:
        (root / ".tarav/config.json").write_text(json.dumps(config))
    return cls.from_path(root)


def manifest():
    return {"class": "tarav.attic.deposit", "schema_version": 1,
            "uuid": "25717a94-4821-4d11-8b44-272fb38ae412",
            "deposited_at": "2026-10-22T00:00:00Z", "sources": ["/former/source"],
            "material": "missing/material", "reason": "Retired Project",
            "dependency_status": "disconnected"}


# tarav.context 96bd11c6:8e6ed6047b3cd490
def test_default_and_override_discovery_never_create_folders(tmp_path):
    default = project_at(tmp_path / "default")
    custom = project_at(tmp_path / "custom", config={"attic": {"path": "old/attic"}})
    assert default.attic().root == tmp_path / "default/_ATTIC"
    assert custom.attic().root == tmp_path / "custom/old/attic"
    for project in (default, custom):
        assert project.checks.run().results_of(ManifestCheck) == ()
        assert not project.attic().root.exists()
    assert not [p for p in ProjectFilesCheck(custom).run().pois()
                if isinstance(p, InvalidConfigSection)]


@pytest.mark.parametrize("path", ["", " ", ".", "..", "../other", "/tmp/attic", 123])
def test_invalid_config_is_reported_without_stopping_other_checks(tmp_path, path):
    project = project_at(tmp_path, config={"attic": {"path": path}})
    with pytest.raises(CliError):
        project.attic()
    run = project.checks.run()
    assert len(run.results_of(AtticLoadCheck)) == 1
    assert run.results_of(AtticLoadCheck)[0].status == "incomplete"
    assert any(isinstance(p, InvalidConfigSection) and p.situation["section"] == "attic"
               for p in run.pois())
    assert run.results_of(ProjectFilesCheck)[0].status == "completed"


def test_symlink_cannot_select_an_external_attic(tmp_path):
    project = project_at(tmp_path / "project")
    (project.root / "_ATTIC").symlink_to(tmp_path / "outside")
    with pytest.raises(CliError, match="below the Project"):
        project.attic()
    assert project.checks.run().results_of(AtticLoadCheck)[0].status == "incomplete"


def test_project_checks_only_read_manifest_and_actions_close_after_repair(tmp_path, monkeypatch):
    project = project_at(tmp_path, config={"attic": {"path": "retired"}})
    deposit = tmp_path / "retired/deposits/old-project"
    deposit.mkdir(parents=True)
    project.status()
    actions = [a for a in project.actions.list()
               if a.data["action"] == "Tarav.Attic.Manifest.Missing.Action"]
    assert len(actions) == 1
    action = actions[0]
    assert action.data["project"]["id"] == str(project.id)
    assert action.state == "running"

    original = Path.iterdir
    def unavailable(path):
        if path == deposit.parent:
            raise PermissionError("offline")
        return original(path)
    with monkeypatch.context() as m:
        m.setattr(Path, "iterdir", unavailable)
        project.status()
    assert next(a for a in project.actions.list() if a.id == action.id).state == "running"

    (deposit / "deposit.json").write_text(json.dumps(manifest()))
    project.status()
    updated = next(a for a in project.actions.list() if a.id == action.id)
    assert (updated.state, updated.exit) == ("closed", "gone")
    assert sorted(p.name for p in deposit.iterdir()) == ["deposit.json"]


def test_root_aggregates_own_and_child_attics_without_discovering_retired_projects(tmp_path):
    import os
    import sys
    parent = project_at(tmp_path, RootProject, children=["child"])
    child = project_at(tmp_path / "child", harness={
        "environment": os.path.relpath(sys.prefix, tmp_path / "child"),
        "type": "tarav.l2.project:Project"})
    for project in (parent, child):
        (project.attic().root / "deposits/old").mkdir(parents=True)
    run = parent.checks.run()
    assert {p.situation["root"] for p in run.pois() if isinstance(p, ManifestMissing)} == {
        str(tmp_path / "_ATTIC"), str(tmp_path / "child/_ATTIC")}
    assert parent.child_paths() == ("child",)
