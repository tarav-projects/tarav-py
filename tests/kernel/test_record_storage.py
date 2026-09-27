import json

import pytest

from tarav.l0.kernel import DirectoryRecord, FileRecord, TypeRegistry


def test_directory_and_entry_share_authority_and_source(tmp_path):
    registry = TypeRegistry(DirectoryRecord, [DirectoryRecord])
    entry = tmp_path / "main.json"
    entry.write_text(json.dumps({"type": "Tarav.DirectoryRecord", "name": "example"}))
    (tmp_path / "payload.bin").write_bytes(b"not a Record")
    folder = registry.load(tmp_path)
    direct = registry.load(entry)
    assert type(folder) is type(direct) is DirectoryRecord
    assert folder.directory == tmp_path
    assert folder.to_record() == direct.to_record()
    assert folder.source == entry


def test_invalid_preferred_entry_never_falls_through(tmp_path):
    (tmp_path / "__tarav.json").write_text("broken")
    (tmp_path / "main.json").write_text('{"type":"Tarav.DirectoryRecord"}')
    with pytest.raises(json.JSONDecodeError):
        TypeRegistry(DirectoryRecord, [DirectoryRecord]).load(tmp_path)
    assert (tmp_path / "__tarav.json").read_text() == "broken"


def test_file_load_has_source_and_keeps_type_dispatch(tmp_path):
    source = tmp_path / "record.json"
    source.write_text('{"type":"Tarav.FileRecord"}')
    registry = TypeRegistry(FileRecord, [FileRecord])
    assert registry.load(source, expected_type=FileRecord).source == source


@pytest.mark.parametrize("filename", ["archive.json", "registration.json"])
def test_workflow_specific_names_are_not_kernel_directory_entries(
    tmp_path, filename
):
    (tmp_path / filename).write_text('{"type":"Tarav.DirectoryRecord"}')

    with pytest.raises(FileNotFoundError):
        TypeRegistry(DirectoryRecord, [DirectoryRecord]).load(tmp_path)
