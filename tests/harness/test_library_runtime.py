import json

from tarav.archive import Archive
from tarav.references import FileReference
from tarav.runtime import create_runtime


def test_runtime_browses_archive_and_loads_reference_without_cli(tmp_path):
    archive = Archive.create(tmp_path / "archive")
    payload = tmp_path / "payload.txt"
    payload.write_text("data")
    reference = archive.reference_file(str(payload))
    doi = reference["locator"]["doi"]
    config = tmp_path / "runtime.json"
    config.write_text(
        json.dumps(
            {
                "providers": [
                    {"name": "archive", "workflow": "archive", "root": "archive"},
                ]
            }
        )
    )
    runtime = create_runtime(config=config)
    assert runtime.navigation.list().value[0].name == "archive"
    record = runtime.navigation.load(f"/archive/artifacts/{doi}")
    assert record.ok
    assert record.value.doi == doi
    assert record.value.contract["kind"] == "file-version"
    locator = runtime.navigation.load(f"/archive/artifacts/{doi}/locators.jsonl/0")
    assert locator.ok
    assert locator.value.record["value"] == str(payload)
    file = tmp_path / "reference.json"
    file.write_text(json.dumps(reference))
    assert runtime.load(file).resolve().ok
    archive.retire(
        doi,
        reason="explicit test retirement",
        hints={"name": payload.name, "size": payload.stat().st_size},
    )
    assert archive.record(doi).doi == doi
    outcome = runtime.load(file).resolve()
    assert outcome.findings
    assert "retired" in outcome.message
    assert payload.read_text() == "data"
    assert (runtime.source_root / "references" / "__init__.py").is_file()


def test_reference_check_and_hints_are_separate(tmp_path):
    payload = tmp_path / "payload.txt"
    payload.write_text("correct")
    reference = FileReference(
        payload,
        check={"sha256": "15a596e3c98c407e043751ff3b21ff0358a1bdfdf3fe948b1523893a8e5de2e8"},
        hints={"content": "wrong"},
    )
    assert create_runtime().references.resolve(reference.record).ok
    reference.record["check"] = {"sha256": "0" * 64}
    reference.record["hints"] = {
        "sha256": "15a596e3c98c407e043751ff3b21ff0358a1bdfdf3fe948b1523893a8e5de2e8"
    }
    result = create_runtime().references.resolve(reference.record)
    assert not result.ok
    assert result.status == "mismatch"
    assert result.hints == reference.hints


def test_old_archive_data_requires_explicit_migration(tmp_path):
    import pytest
    from tarav.harness import InvalidRecordType

    archive = Archive.create(tmp_path / "archive")
    entry = archive.records_root / "archive.json"
    payload = json.loads(entry.read_text())
    payload["class"] = payload.pop("type")
    payload["schema_version"] = 1
    entry.write_text(json.dumps(payload))
    before = entry.read_bytes()
    with pytest.raises(InvalidRecordType):
        Archive.open(archive.root)
    assert entry.read_bytes() == before


def test_reference_classes_respect_structural_type_authority(tmp_path):
    reference = FileReference(tmp_path / "reference-target.txt").record
    reference.pop("type")
    reference["__tarav__"] = {
        "type": {"uuid": str(FileReference.type_ship), "label": "old human label"}
    }
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(reference))
    assert isinstance(create_runtime().load(path), FileReference)
    archive = Archive.create(tmp_path / "archive")
    artifact = archive.register_artifact(locator=str(tmp_path / "data"))
    entry = archive.record(artifact.id)
    retained = entry.record
    retained["type"] = {"uuid": str(entry.type_ship), "label": "old human label"}
    entry.source.write_text(json.dumps(retained))
    assert archive.record(artifact.id).doi == artifact.id


def test_archive_reference_requires_exact_doi(tmp_path):
    from tarav.archive.references import ArchiveReference

    archive = Archive.create(tmp_path / "archive")
    artifact = archive.register_artifact(locator=str(tmp_path / "data"), name="example")
    for selector in ("example", artifact.id[:12]):
        outcome = ArchiveReference(
            {"locator": {"archive": str(archive.root), "doi": selector}}
        ).resolve()
        assert not outcome.ok
        assert "exact DOI" in outcome.message
