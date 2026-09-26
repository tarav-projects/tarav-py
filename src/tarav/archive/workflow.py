"""Built-in Archive workflow and its typed navigation provider."""

from pathlib import Path

from tarav.kernel import TaravClass
from tarav.kernel import TypeShip
from tarav.kernel.workflows import TaravWorkflow
from tarav.archive.identity import ARCHIVE_WORKFLOW_SHIP
from tarav.kernel.space import Entry, FilesystemProvider

from . import Archive
from .artifact_records import record_registry


class ArchiveProvider(FilesystemProvider):
    def __init__(self, root: Path) -> None:
        self.archive = Archive.open(root)
        super().__init__(self.archive.records_root, record_registry())

    def list(self, address: str = "") -> tuple[Entry, ...]:
        path = self.path(address)
        if path.suffix == ".jsonl":
            from . import _read_jsonl_objects

            return tuple(
                Entry(str(i), "record") for i, _ in enumerate(_read_jsonl_objects(path))
            )
        return tuple(
            Entry(
                entry.name,
                "collection" if entry.name.endswith(".jsonl") else entry.kind,
            )
            for entry in super().list(address)
        )

    def load(self, address: str):
        parent, _, item = address.rpartition("/")
        if parent.endswith(".jsonl"):
            from . import _read_jsonl_objects

            payload = _read_jsonl_objects(self.path(parent))[int(item)]
            result = self.records.from_record(payload)
            result.source = self.path(parent)
            return result
        return super().load(address)


class ArchiveWorkflow(TaravWorkflow):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('0a5e9874-822e-424b-8a88-23b8b3ff1252'),
            name='Tarav.Workflow.Archive',
            workflow=ARCHIVE_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return ARCHIVE_WORKFLOW_SHIP
    workflow_name = "archive"
    constitution = (
        "Record artifacts and their retention evidence without interpreting "
        "their domain meaning."
    )

    @classmethod
    def provider(cls, root, records):
        return ArchiveProvider(root)

    @staticmethod
    def open(root: Path) -> Archive:
        return Archive.open(root)
