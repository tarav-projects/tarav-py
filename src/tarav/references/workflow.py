"""Common dispatch over explicitly registered reference classes."""

from collections.abc import Mapping

from tarav.harness import TaravObject, TypeRegistry
from tarav.harness.workflows import Workflow
from . import FilePositionReference, FileReference, Reference, ReferenceResult
from .git import GitFileReference
from .structured import StructuredFileReference


class ReferenceWorkflow(Workflow):
    name = "references"
    record_types = (
        Reference,
        FileReference,
        FilePositionReference,
        GitFileReference,
        StructuredFileReference,
    )

    def __init__(self, records: TypeRegistry | None = None):
        self.records = (
            records
            if records is not None
            else TypeRegistry(TaravObject, self.record_types)
        )

    def load(self, record: Mapping) -> Reference:
        loaded = self.records.from_json(record)
        if not isinstance(loaded, Reference):
            raise TypeError("Registered type is not a Reference")
        return loaded

    def resolve(self, reference: Reference | Mapping, **context):
        try:
            value = (
                self.load(reference) if isinstance(reference, Mapping) else reference
            )
            if not isinstance(value, Reference):
                raise TypeError("Expected a Reference or retained reference Record")
            return value.resolve(**context)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            return ReferenceResult(None, "unresolvable", str(exc))
