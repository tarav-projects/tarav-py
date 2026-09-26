"""Synthetic Context workspace for exercising real Tarav navigation."""

from __future__ import annotations

__test__ = False

from collections.abc import Mapping
from typing import Literal, Self
from uuid import uuid4

from pydantic import BaseModel

from tarav.context_workflow import ContextService
from tarav.kernel.context import ContextBuilder
from tarav.kernel.identity import Ship, TypeShip, WorkflowShip
from tarav.kernel.records import (
    FileRecord,
    TaravClass,
    TaravEntity,
    entity,
)
from tarav.kernel.workflows import TaravWorkflow
from tarav.record_archive import (
    ArchiveEntry,
    ArchivePartition,
    ArchiveFolder,
    ArchiveList,
)


TEST_WORKFLOW_SHIP = WorkflowShip("84b6d49c-8bba-4af4-a880-c5fa453f80e5")
TEST_ENTITY_SHIP = Ship("71c9a2be-6d3f-4e38-bb88-20783a10f98c")


class TestItem(FileRecord):
    """One synthetic leaf used to exercise Record dispatch in Context."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("66a6c597-17ef-4604-b7bf-139374176b4d"),
            name="Tarav.Test.Item",
            workflow=TEST_WORKFLOW_SHIP,
        )

    class RecordInterface(FileRecord.RecordInterface):
        type: Literal["Tarav.Test.Item"]
        label: str

    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls(record_data.label)

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {"type": entity(cls).name, "label": "example"}

    def _to_record(self) -> Mapping[str, object]:
        return {"type": entity(type(self)).name, "label": self.label}


class TestEntity(TaravEntity):
    """An identified synthetic subject with its own retained Context root."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("ea6d1c75-2198-4318-8e3a-472a7d3fd0f6"),
            name="Tarav.Test.Entity",
            workflow=TEST_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravEntity.RecordInterface):
        type: Literal["Tarav.Test.Entity"]
        label: str

    def __init__(self, id: Ship, label: str) -> None:
        super().__init__(id)
        self.label = label

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls(record_data.id, record_data.label)

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {
            "type": entity(cls).name,
            "id": str(TEST_ENTITY_SHIP),
            "label": "example",
        }

    def _to_record(self) -> Mapping[str, object]:
        return {**super()._to_record(), "label": self.label}


class TestWorkflow(TaravWorkflow):
    """Real Workflow backed by deliberately synthetic, disposable fixtures."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("6a444dda-d175-4b9b-b9b3-0db0addc137a"),
            name="Tarav.Workflow.Test",
            workflow=TEST_WORKFLOW_SHIP,
        )

    workflow_name = "test"
    constitution = (
        "Provide a disposable test workspace for Tarav mechanics. Its entries "
        "are synthetic fixtures, not user or project knowledge."
    )

    @classmethod
    def class_context(cls, builder: ContextBuilder) -> None:
        example = TestItem("runtime")
        builder.add(
            "runtime-example",
            opener=lambda: example,
        )
        builder.add(
            "runtime-alias",
            opener=lambda: example,
        )
        builder.add(
            "sample-entity",
            opener=lambda: TestEntity(TEST_ENTITY_SHIP, "sample"),
        )

    @classmethod
    def create_context_workspace(
        self, contexts: ContextService
    ) -> tuple[ArchiveFolder, ArchiveFolder]:
        """Explicitly seed disposable Context Archives for this Test Workflow."""

        sample_entity = TestEntity(TEST_ENTITY_SHIP, "sample")

        workflow_root = contexts.create_subject_archive(
            self, constitution="Disposable Test Workflow Context."
        )
        entity_root = contexts.create_subject_archive(
            sample_entity, constitution="Disposable Test Entity Context."
        )
        contexts.put(
            self,
            "retained-example",
            TestItem("retained"),
            description="Synthetic retained example.",
        )
        examples_entry = contexts.put_folder(
            self,
            "examples",
            ArchiveFolder,
            constitution="Named Context examples.",
            description="Named synthetic examples.",
        )
        examples_backing = examples_entry.archive_entry()
        assert isinstance(examples_backing, ArchiveEntry)
        examples = examples_backing.open()
        assert isinstance(examples, ArchiveFolder)
        contexts.write(examples, "nested-example", TestItem("nested"))
        ordered_entry = contexts.put_folder(
            self,
            "ordered",
            ArchiveList,
            constitution="Ordered Context examples.",
        )
        ordered_backing = ordered_entry.archive_entry()
        assert isinstance(ordered_backing, ArchiveEntry)
        ordered = ordered_backing.open()
        assert isinstance(ordered, ArchiveList)
        contexts.write(ordered, None, TestItem("first"))
        contexts.write(ordered, None, TestItem("second"))
        contexts.put(sample_entity, "entity-note", TestItem("about sample"))
        return workflow_root, entity_root

    @classmethod
    def create_record_archives(
        self,
        partition: ArchivePartition,
        run_name: str,
    ) -> tuple[ArchiveFolder, ArchiveList]:
        """Explicit disposable fixture using both built-in Archive structures."""

        if partition.workflow != self.id:
            raise ValueError("Archive partition belongs to a different Workflow")
        run = partition.create_directory(run_name)
        dictionary = run.create_dictionary(
            "named",
            constitution="Disposable named Test Workflow Records.",
        )
        vector = run.create_vector(
            "ordered",
            constitution="Disposable ordered Test Workflow Records.",
        )
        dictionary.put("greeting", TestEntity(Ship(uuid4()), "hello tarav"))
        vector.append(TestItem("first"))
        vector.append(TestItem("second"))
        return dictionary, vector


__all__ = [
    "TEST_ENTITY_SHIP",
    "TEST_WORKFLOW_SHIP",
    "TestEntity",
    "TestItem",
    "TestWorkflow",
]
