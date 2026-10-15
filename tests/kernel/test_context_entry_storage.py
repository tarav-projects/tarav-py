"""Retained Context entry Types express relationships independently of cargo."""

from typing import Literal

from tarav.l0.kernel import FileRecord, TaravClass, TypeShip
from tarav.l1.context import ContextEntry, explore
from tarav.l3.runtime import create_runtime, get_runtime, set_runtime


class Relationship(ContextEntry):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("b1f20000-0000-4000-8000-000000000001"),
                          name="Test.Context.Relationship")

    class RecordInterface(ContextEntry.RecordInterface):
        type: Literal["Test.Context.Relationship"]
        role: str

    def __init__(self, *, role, cargo=None, description=None):
        super().__init__(cargo=cargo, description=description)
        self.role = role

    @classmethod
    def _from_record(cls, data):
        return cls(role=data.role, cargo=data.cargo, description=data.description)

    def _to_record(self):
        return {**super()._to_record(), "role": self.role}


# tarav.context 473c89a0:ba32e41d46ab46db
def test_specialized_relationship_survives_write_load_listing_and_explorer_binding(tmp_path):
    old = get_runtime()
    runtime = create_runtime(archive_root=tmp_path / "archive", record_types=(Relationship,))
    set_runtime(runtime)
    try:
        contexts = runtime.contexts
        contexts.create_subject_archive(FileRecord, constitution="Typed relationship fixture.")
        original = Relationship(role="input", cargo=FileRecord(), description="An input relationship.")
        written = contexts.put_entry(FileRecord, "source", original)
        assert type(written) is Relationship
        assert written.role == "input"
        assert written.placement == "source"
        assert original.placement is None

        fresh = create_runtime(archive_root=contexts.archive_root, record_types=(Relationship,))
        set_runtime(fresh)
        explorer = FileRecord.context()
        entry = explorer.get("source")
        assert type(entry) is Relationship
        assert entry.role == "input"
        assert entry.description == "An input relationship."
        assert entry.archive_entry() is not None
        assert entry.records.to_record() == {
            "type": "Test.Context.Relationship", "role": "input",
            "cargo": {"type": "Tarav.FileRecord"}, "description": "An input relationship.",
        }
        assert type(entry.open()) is FileRecord
        assert explore(entry) is explorer
        assert type(explorer.subject) is FileRecord
        assert explorer.back().subject is FileRecord
        assert type(explorer.get("source")) is Relationship
    finally:
        set_runtime(old)
