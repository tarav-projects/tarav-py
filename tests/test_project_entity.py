import json

import pytest

from tarav._core.errors import CliError
from tarav._core.project import initialize_project_layout
from tarav.kernel import Ship, entity
from tarav.project import Project, ProjectWorkflow
from tarav.runtime import create_runtime
from tarav.wiki import Wiki


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
        assert Wiki.from_project(project).root == nested / "notes/wiki"
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
    from tarav.context import context
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
