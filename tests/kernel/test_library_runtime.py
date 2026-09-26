from tarav.kernel import entity

import json

import pytest

from tarav import load_object
from tarav.archive import Archive
from tarav.chatlas.workflow import ChatlasWorkflow
from tarav.kernel import DirectoryRecord, FileRecord, KERNEL_WORKFLOW_SHIP, RecordTypeMismatch, TARAV, KernelWorkflow
from tarav.context import explore as context
from tarav.references import FileReference
from tarav.runtime import create_runtime


def test_runtime_discovers_workflow_entities_by_name_and_ship():
    runtime = create_runtime()
    workflow = runtime.workflows.get("chatlas")

    assert workflow is ChatlasWorkflow
    assert runtime.workflows.get(workflow().id) is workflow


def test_runtime_bootstraps_tarav_and_the_kernel_workflow():
    runtime = create_runtime()

    assert runtime.system is TARAV
    assert runtime.system.to_record() == {
        "type": "Tarav.System",
        "id": "e5ff87ed-c382-49c8-855e-e04191dcf4c8",
        "name": "tarav",
    }
    assert runtime.workflows.get("kernel") is KernelWorkflow
    assert runtime.workflows.get(KERNEL_WORKFLOW_SHIP).workflow_name == "kernel"
    assert context(TARAV).open("class").open("entity").target is type(TARAV)


def test_public_load_object_dispatches_and_checks_expected_type(tmp_path):
    path = tmp_path / "record.json"
    path.write_text('{"type":"Tarav.FileRecord"}')

    loaded = load_object(path, expected_type=FileRecord)

    assert type(loaded) is FileRecord
    assert loaded.source == path
    with pytest.raises(RecordTypeMismatch):
        load_object(path, expected_type=DirectoryRecord)


def test_every_registered_type_names_a_registered_owning_workflow():
    runtime = create_runtime()

    for record_type in runtime.records.record_types:
        owner = runtime.workflows.get(entity(record_type).workflow_ship)
        assert entity(record_type).workflow_ship == owner().id


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
    assert locator.value.to_record()["value"] == str(payload)
    file = tmp_path / "reference.json"
    file.write_text(json.dumps(reference))
    assert runtime.load_object(file).resolve().ok
    archive.retire(
        doi,
        reason="explicit test retirement",
        hints={"name": payload.name, "size": payload.stat().st_size},
    )
    assert archive.record(doi).doi == doi
    outcome = runtime.load_object(file).resolve()
    assert outcome.findings
    assert "retired" in outcome.message
    assert payload.read_text() == "data"
    assert (runtime.source_root / "references" / "__init__.py").is_file()


def test_reference_check_and_hints_are_separate(tmp_path):
    payload = tmp_path / "payload.txt"
    payload.write_text("correct")
    reference = FileReference(
        payload,
        check={
            "sha256": "15a596e3c98c407e043751ff3b21ff0358a1bdfdf3fe948b1523893a8e5de2e8"
        },
        hints={"content": "wrong"},
    )
    assert create_runtime().references.resolve(reference.to_record()).ok
    assert reference._record is not None
    reference._record["check"] = {"sha256": "0" * 64}
    reference._record["hints"] = {
        "sha256": "15a596e3c98c407e043751ff3b21ff0358a1bdfdf3fe948b1523893a8e5de2e8"
    }
    result = create_runtime().references.resolve(reference.to_record())
    assert not result.ok
    assert result.status == "mismatch"
    assert result.hints == reference.hints


def test_old_archive_data_requires_explicit_migration(tmp_path):
    from tarav.kernel import InvalidRecordType

    archive = Archive.create(tmp_path / "archive")
    entry = archive.records_root / "main.json"
    payload = json.loads(entry.read_text())
    payload["class"] = payload.pop("type")
    payload["schema_version"] = 1
    entry.write_text(json.dumps(payload))
    before = entry.read_bytes()
    with pytest.raises(InvalidRecordType):
        Archive.open(archive.root)
    assert entry.read_bytes() == before


def test_reference_classes_respect_structural_type_authority(tmp_path):
    reference = FileReference(tmp_path / "reference-target.txt").to_record()
    reference.pop("type")
    reference["__tarav__"] = {
        "type": {"uuid": str(entity(FileReference).id), "label": "old human label"}
    }
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(reference))
    assert isinstance(create_runtime().load_object(path), FileReference)
    archive = Archive.create(tmp_path / "archive")
    artifact = archive.register_artifact(locator=str(tmp_path / "data"))
    entry = archive.record(artifact.id)
    retained = entry.to_record()
    retained["type"] = {
        "uuid": str(entity(type(entry)).id),
        "label": "old human label",
    }
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
