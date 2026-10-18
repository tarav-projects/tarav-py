"""Disposable Context and Archive navigation fixtures."""

from __future__ import annotations

__test__ = False

from collections.abc import Mapping
from typing import Literal, Self
from uuid import uuid4


from tarav.l0.kernel.identity import Ship, TypeShip, WorkflowShip
from tarav.l0.kernel.records import (
    FileRecord,
    TaravClass,
    TaravEntity,
    entity,
)
from tarav.l1.archive.records import (
    ArchivePartition,
    ArchiveFolder,
    ArchiveList,
)
from .workflow import TestsWorkflow
from tarav.l0.kernel import LoadedRecord


NAVIGATION_TESTS_WORKFLOW_SHIP = WorkflowShip("d337b876-654b-4680-bf75-ce25619095e5")
TEST_ENTITY_SHIP = Ship("71c9a2be-6d3f-4e38-bb88-20783a10f98c")


class TestItem(FileRecord):
    """One synthetic leaf used to exercise Record dispatch in Context."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("66a6c597-17ef-4604-b7bf-139374176b4d"),
            name="Tarav.Test.Item",
            workflow=NAVIGATION_TESTS_WORKFLOW_SHIP,
        )

    class RecordInterface(FileRecord.RecordInterface):
        type: Literal["Tarav.Test.Item"]
        label: str

    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label

    @classmethod
    def _from_record(cls, loaded: LoadedRecord) -> Self:
        return cls(loaded.data.label)

    class Records(FileRecord.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
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
            workflow=NAVIGATION_TESTS_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravEntity.RecordInterface):
        type: Literal["Tarav.Test.Entity"]
        label: str

    def __init__(self, id: Ship, label: str) -> None:
        super().__init__(id)
        self.label = label

    @classmethod
    def _from_record(cls, loaded: LoadedRecord) -> Self:
        return cls(loaded.data.id, loaded.data.label)

    class Records(TaravEntity.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return {
                "type": entity(cls).name,
                "id": str(TEST_ENTITY_SHIP),
                "label": "example",
            }


    def _to_record(self) -> Mapping[str, object]:
        return {**super()._to_record(), "label": self.label}


class NavigationTestsWorkflow(TestsWorkflow):
    """Synthetic Context and Archive workspace for navigation tests."""

    __test__ = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("7d682bf3-086a-4bec-acd5-71a811a3ae09"),
            name="Tarav.Workflow.Tests.Navigation",
            workflow=NAVIGATION_TESTS_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return NAVIGATION_TESTS_WORKFLOW_SHIP

    @property
    def workflow(self):
        return TestsWorkflow()

    constitution = "Exercise navigation with disposable synthetic fixtures."

    @classmethod
    def create_record_archives(
        self,
        partition: ArchivePartition,
        run_name: str,
    ) -> tuple[ArchiveFolder, ArchiveList]:
        """Explicit disposable fixture using both built-in Archive structures."""

        if partition.workflow_ship != self().id:
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
    "NAVIGATION_TESTS_WORKFLOW_SHIP",
    "TestEntity",
    "TestItem",
    "NavigationTestsWorkflow",
]
