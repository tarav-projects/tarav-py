"""Built-in Archive workflow and its typed navigation provider."""

from pathlib import Path

from tarav.harness.workflows import Workflow
from tarav.navigation import Entry, FilesystemProvider

from . import Archive
from .records import ARCHIVE_RECORD_TYPES, record_registry
from .references import ArchiveReference


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
            result = self.records.resolve(payload)(payload)
            result.source = self.path(parent)
            return result
        return super().load(address)


class ArchiveWorkflow(Workflow):
    name = "archive"
    record_types = (*ARCHIVE_RECORD_TYPES, ArchiveReference)

    def provider(self, root, records):
        return ArchiveProvider(root)

    @staticmethod
    def open(root: Path) -> Archive:
        return Archive.open(root)
