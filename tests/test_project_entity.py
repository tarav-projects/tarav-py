import json

import pytest

from tarav.l0._core.errors import CliError
from tarav.l0._core.project import initialize_project_layout
from tarav.l0.kernel import Ship, entity
from tarav.l1.project import Project, ProjectWorkflow, TaravProject
from tarav.runtime import create_runtime


def test_discovery_preserves_marker_and_selects_nearest_project(tmp_path):
    initialize_project_layout(tmp_path)
    nested = tmp_path / "nested"
    nested.mkdir()
    initialize_project_layout(nested)
    child = nested / "src"
    child.mkdir()
    file = child / "example.py"
    file.touch()
    marker = nested / ".tarav/project.json"
    before = marker.read_bytes()
    for path in (nested, child, file):
        project = Project.from_path(path)
        assert project.root == nested
        assert project.id == Ship(json.loads(before)["project_id"])
        assert project.name == "nested"
        assert project.to_record() == json.loads(before)
        assert project.workflow is ProjectWorkflow()
        assert project.wiki().root == nested / "notes/wiki"
    assert marker.read_bytes() == before
    assert not (nested / "notes/wiki").exists()
    assert Project.from_path(tmp_path).id != project.id


def test_detached_project_preserves_extra_metadata_and_identity():
    record = {**Project.record_example(), "name": "Named", "custom": {"keep": True}}
    project = Project.from_record(record)
    assert project.name == "Named"
    assert project.to_record() == record
    assert project.id in project.ships()
    with pytest.raises(ValueError, match="Detached"):
        _ = project.root
    assert Project(project.id).to_record() == Project.record_example()


def test_typed_project_record_supports_generic_loading(tmp_path):
    initialize_project_layout(tmp_path)
    marker = tmp_path / ".tarav/project.json"
    record = json.loads(marker.read_text())
    record["type"] = entity(Project).name
    marker.write_text(json.dumps(record))
    before = marker.read_bytes()
    project = create_runtime().load_object(marker, expected_type=Project)
    assert project.root == tmp_path
    assert project.to_record() == record
    assert marker.read_bytes() == before


def test_missing_and_invalid_markers_do_not_create_or_repair(tmp_path):
    with pytest.raises(CliError):
        Project.from_path(tmp_path)
    assert not (tmp_path / ".tarav").exists()
    initialize_project_layout(tmp_path)
    marker = tmp_path / ".tarav/project.json"
    marker.write_text('{"class": "agentos.project", "project_id": "bad"}')
    before = marker.read_bytes()
    with pytest.raises(CliError):
        Project.from_path(tmp_path)
    assert marker.read_bytes() == before


def test_project_context_is_available_without_creating_archive(tmp_path):
    from tarav.l1.context import context
    from tarav import get_runtime, set_runtime

    initialize_project_layout(tmp_path)
    project = Project.from_path(tmp_path)
    archive = tmp_path / "archive"
    previous = get_runtime()
    runtime = create_runtime(archive_root=archive)
    try:
        set_runtime(runtime)
        assert context(project) is not None
        assert not archive.exists()
    finally:
        set_runtime(previous)
    assert runtime.records.resolve_ship(entity(Project).id) is Project


@pytest.mark.parametrize("typed", [False, True])
def test_explicit_project_subtypes_share_identity_without_rewriting(tmp_path, typed):
    from tarav.l0.kernel import TaravClass, TypeShip

    class LocalProject(Project):
        @classmethod
        def class_entity(cls):
            return TaravClass(target=cls, id=TypeShip("f97f48ca-e48c-4720-aa3d-3caf4f81ea22"),
                              name="Test.LocalProject")

        def local_config(self):
            return self.root / "local.json"

    initialize_project_layout(tmp_path)
    marker = tmp_path / ".tarav/project.json"
    if typed:
        record = json.loads(marker.read_text())
        record["type"] = entity(Project).name
        marker.write_text(json.dumps(record))
    before = marker.read_bytes()
    base = TaravProject.from_path(tmp_path)
    featured = Project.from_path(tmp_path)
    local = LocalProject.from_path(tmp_path)
    assert type(base) is TaravProject
    assert type(local) is LocalProject
    assert base.id == featured.id == local.id
    assert not hasattr(base, "models") and not hasattr(base, "wiki")
    assert local.local_config() == tmp_path / "local.json"
    assert local.wiki().root == featured.wiki().root
    assert marker.read_bytes() == before
    if typed:
        assert base.to_record()["type"] == entity(TaravProject).name
        assert local.to_record()["type"] == entity(LocalProject).name


def test_minimal_import_does_not_load_integrations():
    import subprocess
    import sys

    subprocess.run([sys.executable, "-c", '''
import sys
from tarav.l1.project import TaravProject, Project
assert "tarav.l1.project.models" not in sys.modules
assert "tarav.l1.project.wiki" not in sys.modules
assert "tarav.models" not in sys.modules
assert "tarav.wiki" not in sys.modules
'''], check=True)


def test_integrations_have_explicit_child_workflow_ownership(tmp_path):
    from tarav.l1.project.models import ProjectModels, ProjectModelsWorkflow
    from tarav.l1.project.wiki import ProjectWiki, ProjectWikiWorkflow

    initialize_project_layout(tmp_path)
    project = TaravProject.from_path(tmp_path)
    assert ProjectWiki(project).open().root == tmp_path / "notes/wiki"
    assert entity(ProjectModels).workflow is ProjectModelsWorkflow()
    assert entity(ProjectWiki).workflow is ProjectWikiWorkflow()
    assert ProjectModelsWorkflow().workflow is ProjectWorkflow()
    assert ProjectWikiWorkflow().workflow is ProjectWorkflow()
