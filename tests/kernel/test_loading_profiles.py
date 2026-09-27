"""Profile selection is independent of trusted Record Type dispatch."""

import json

import pytest

from tarav import load_object, set_runtime
from tarav.l0.kernel import (
    DirectoryRecord,
    FileRecord,
    RecordTypeMismatch,
    UnknownRecordType,
    TaravClass,
    TypeShip,
    entity,
)
from tarav.l1.loading import LoadingProfile, load
from tarav.l1.project import Project
from tarav.runtime import create_runtime, get_runtime


class LocalDocument(FileRecord, LoadingProfile):
    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("6f5bd6e9-17de-4220-af69-c90427420d4e"),
            name="Test.LoadingDocument",
        )

    @classmethod
    def loading_paths(cls) -> tuple[str, ...]:
        return ("first.json", "nested/second.json")


class LocalProject(Project):
    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("69dfa0c3-54da-4c69-9fe7-d9584bbfa810"),
            name="Test.LoadingProject",
        )


@pytest.fixture
def runtime():
    current = get_runtime()
    selected = create_runtime(record_types=(LocalDocument, LocalProject))
    set_runtime(selected)
    try:
        yield selected
    finally:
        set_runtime(current)


def write_record(path, record_type, **fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": entity(record_type).name, **fields}))


def test_profile_order_and_explicit_file_keep_dispatch_exact(tmp_path, runtime):
    second = tmp_path / "nested/second.json"
    write_record(second, LocalDocument)
    loaded = load(path=tmp_path, profile=LocalDocument, expected_type=LocalDocument)
    assert type(loaded) is LocalDocument
    assert loaded.source == second
    assert runtime.load_object(tmp_path, profile=LocalDocument).source == second
    assert load_object(tmp_path, profile=LocalDocument).source == second

    first = tmp_path / "first.json"
    write_record(first, FileRecord)
    assert type(load(tmp_path, profile=LocalDocument)) is FileRecord
    with pytest.raises(RecordTypeMismatch, match="expected exact Type"):
        load(tmp_path, profile=LocalDocument, expected_type=LocalDocument)
    assert type(load(second, profile=LocalDocument)) is LocalDocument
    assert type(runtime.records.load(second)) is LocalDocument
    assert first.read_text() == json.dumps({"type": entity(FileRecord).name})


def test_selected_bad_entry_fails_without_fallback(tmp_path, runtime):
    first = tmp_path / "first.json"
    first.write_text("{bad")
    write_record(tmp_path / "nested/second.json", LocalDocument)
    with pytest.raises(json.JSONDecodeError):
        load(tmp_path, profile=LocalDocument)

    first.unlink()
    first.symlink_to(tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError):
        load(tmp_path, profile=LocalDocument)

    first.unlink()
    first.mkdir()
    with pytest.raises(IsADirectoryError):
        load(tmp_path, profile=LocalDocument)


@pytest.mark.parametrize("candidate", ["", ".", "../escape.json", "/absolute.json"])
def test_profile_rejects_unsafe_entry_paths(tmp_path, runtime, candidate):
    class Unsafe(LoadingProfile):
        @classmethod
        def loading_paths(cls):
            return (candidate,)

    with pytest.raises(ValueError, match="Invalid relative"):
        load(tmp_path, profile=Unsafe)


def test_profile_is_opt_in_and_default_directory_guard_remains(tmp_path, runtime):
    write_record(tmp_path / "main.json", FileRecord)
    with pytest.raises(RecordTypeMismatch, match="DirectoryRecord"):
        load(tmp_path)
    assert not issubclass(FileRecord, LoadingProfile)
    assert type(load(tmp_path / "main.json")) is FileRecord
    assert type(runtime.records.load(tmp_path / "main.json")) is FileRecord

    write_record(tmp_path / "main.json", DirectoryRecord)
    assert type(load(tmp_path)) is DirectoryRecord


def test_project_profile_loads_both_marker_layouts_without_writes(tmp_path, runtime):
    root = tmp_path / "project"
    marker = root / ".tarav/project.json"
    fields = {
        "project_id": "0ec6bf2e-6770-410e-a24d-68fa28f558e1",
        "class": "agentos.project",
    }
    write_record(marker, LocalProject, **fields)
    before = marker.read_bytes()

    for selected in (root, root / ".tarav", marker):
        project = load(selected, profile=Project, expected_type=LocalProject)
        assert type(project) is LocalProject
        assert project.root == root
        assert project.source == marker
    assert marker.read_bytes() == before

    marker.unlink()
    direct = root / "project.json"
    write_record(direct, LocalProject, **fields)
    before = direct.read_bytes()
    project = load(root, profile=Project)
    assert type(project) is LocalProject
    assert project.root == root
    assert project.source == direct
    assert direct.read_bytes() == before

    child = root / "child"
    child.mkdir()
    with pytest.raises(FileNotFoundError):
        load(child, profile=Project)


def test_profile_does_not_allow_untrusted_type(tmp_path, runtime):
    path = tmp_path / "first.json"
    path.write_text('{"type":"Unknown.External"}')
    with pytest.raises(UnknownRecordType, match="Unknown.External"):
        load(tmp_path, profile=LocalDocument)
