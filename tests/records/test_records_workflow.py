from __future__ import annotations

import json
import subprocess
from typing import Literal

from tarav.l0.kernel import Ship, TARAV, TaravClass, TaravEntity, TaravSystem, TypeShip
from tarav.l0.kernel.space import Entry, FilesystemProvider, RecordProvider
from tarav.l1.records import TaravRecords
from tarav.l2.scoring.repository import ScoringRepository
from tarav.l3.runtime import create_runtime


class MemorySource(RecordProvider):
    def list(self, address: str = "") -> tuple[Entry, ...]:
        if address:
            raise FileNotFoundError(address)
        return (Entry("tarav", "record"),)

    def load(self, address: str):
        if address != "tarav":
            raise FileNotFoundError(address)
        return TARAV


class VersionedEntity(TaravEntity):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("087cb122-f26d-4b5b-9958-57641b11c81c"),
            name="Tarav.Test.Records.VersionedEntity",
            workflow=TaravRecords().id,
        )

    class RecordInterface(TaravEntity.RecordInterface):
        type: Literal["Tarav.Test.Records.VersionedEntity"]
        value: str

    def __init__(self, id: Ship, value: str) -> None:
        super().__init__(id)
        self.value = value

    @classmethod
    def _from_record(cls, data):
        return cls(data.id, data.value)

    def _to_record(self):
        return {**super()._to_record(), "value": self.value}

    @classmethod
    def record_example(cls):
        return cls(Ship("8ff86f8c-3405-4e4b-b58b-1b843bb72d7b"), "first").to_record()


def test_records_workflow_explores_mounted_sources_and_entity_occurrences(tmp_path):
    # tarav.breadcrumb 2b9eaf3c981b3e51f8247714c7fc865ccef4a87852d26039d75a08b8a13664d4
    runtime = create_runtime()
    assert runtime.workflows.get("records") is TaravRecords
    root = tmp_path / "typed"
    root.mkdir()
    (root / "system.json").write_text(json.dumps(TARAV.to_record()))
    (root / "history.jsonl").write_text(
        json.dumps(TARAV.to_record()) + "\n" + json.dumps(TARAV.to_record()) + "\n"
    )
    runtime.navigation.mount("typed", FilesystemProvider(root, runtime.records))
    runtime.navigation.mount("memory", MemorySource())

    explorer = runtime.navigation.explore()
    assert explorer.pwd() == "/"
    assert [entry.name for entry in explorer.ls()] == ["typed", "memory"]
    explorer.cd("typed").cd("history.jsonl")
    assert explorer.pwd() == "/typed/history.jsonl"
    assert [entry.name for entry in explorer.ls()] == ["0", "1"]
    assert isinstance(explorer.open("0"), TaravSystem)
    explorer.cd("/").cd("memory")
    assert explorer.open("tarav") is TARAV
    explorer.back()
    assert explorer.pwd() == "/"

    found = runtime.navigation.entities(TARAV.id)
    assert found.ok
    assert {entry.path for entry in found.value} == {
        "/typed/system.json", "/typed/history.jsonl/0",
        "/typed/history.jsonl/1", "/memory/tarav",
    }
    assert not (root / ".git").exists()


def test_scoring_repository_contributes_its_own_storage_layout(tmp_path):
    ScoringRepository.initialize(tmp_path / "scoring")
    config = tmp_path / "runtime.json"
    config.write_text(json.dumps({
        "providers": [{"name": "scoring", "workflow": "scoring", "root": "scoring"}],
    }))
    runtime = create_runtime(config=config)

    explorer = runtime.navigation.explore().cd("scoring")
    names = {entry.name for entry in explorer.ls()}
    assert {"pools", "assertion-traces"} <= names
    assert "repository.json" not in names
    assert runtime.navigation.entities().ok


def test_invalid_provider_entry_is_reported_without_mutation():
    class BadSource(RecordProvider):
        def list(self, address: str = "") -> tuple[Entry, ...]:
            return (Entry("../escape", "record"),)

        def load(self, address: str):
            raise AssertionError("must not load an invalid address")

    service = TaravRecords.service()
    service.mount("bad", BadSource())
    outcome = service.list("/bad")
    assert not outcome.ok
    assert outcome.pois[0].code == "provider-error"


def test_standard_registry_retains_typed_current_and_exact_git_editions(tmp_path):
    runtime = create_runtime(record_types=(VersionedEntity,))
    registry = TaravRecords.registry(tmp_path / "standard", runtime.records)
    partition = registry.for_workflow(TaravRecords).create()
    subprocess.run(
        ["git", "-C", str(partition.root), "config", "user.name", "Tarav Test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(partition.root), "config", "user.email", "tarav@test.invalid"],
        check=True,
    )
    identity = Ship("8ff86f8c-3405-4e4b-b58b-1b843bb72d7b")
    partition.insert("case", VersionedEntity(identity, "first"))
    first_commit = partition.commit(("case",), "First edition")
    first_reference = partition.edition_reference("case", first_commit)
    partition.replace("case", VersionedEntity(identity, "second"))
    assert partition.load("case").value == "second"
    assert partition.working_reference("case").locate(str(partition.path("case")))
    assert b'"first"' in first_reference.resolve().target["content"]
    assert b'"first"' in partition.head_reference("case").resolve().target["content"]
    second_commit = partition.commit(("case",), "Second edition")
    assert second_commit != first_commit
    assert b'"second"' in partition.head_reference("case").resolve().target["content"]
    assert b'"first"' in first_reference.resolve().target["content"]
    partition.path("case").unlink()
    assert b'"first"' in partition.edition_reference("case", first_commit).resolve().target["content"]
    assert b'"second"' in partition.head_reference("case").resolve().target["content"]
    partition.insert("case", VersionedEntity(identity, "second"))

    runtime.navigation.mount("registry", registry.provider())
    explorer = runtime.navigation.explore().cd("registry").cd(str(TaravRecords().id))
    assert [entry.name for entry in explorer.ls()] == ["records"]
    assert isinstance(explorer.cd("records").open("case.json"), VersionedEntity)
    found = runtime.navigation.entities(identity)
    assert found.ok and [entry.path for entry in found.value] == [
        f"/registry/{TaravRecords().id}/records/case.json",
    ]

    config = tmp_path / "registry-runtime.json"
    config.write_text(json.dumps({
        "providers": [{"name": "standard", "workflow": "records", "root": "standard"}],
    }))
    reloaded = create_runtime(config=config, record_types=(VersionedEntity,))
    assert isinstance(
        reloaded.navigation.explore().cd("standard").cd(str(TaravRecords().id))
        .cd("records").open("case.json"), VersionedEntity,
    )
