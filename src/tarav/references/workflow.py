"""Common dispatch over explicitly registered reference classes."""

from collections.abc import Mapping

from tarav.harness import TaravRecord, TypeRegistry
from tarav.harness.workflows import Workflow
from . import FileReference, Reference, ReferenceResult
from .git import GitFileReference
from .structured import StructuredFileReference


class ReferenceWorkflow(Workflow):
    name = "references"
    record_types = (Reference, FileReference, GitFileReference, StructuredFileReference)

    def __init__(self, records: TypeRegistry | None = None):
        self.records = (
            records
            if records is not None
            else TypeRegistry(TaravRecord, self.record_types)
        )

    def load(self, record: Mapping) -> Reference:
        authority = self.records.resolve(record)
        if not issubclass(authority, Reference):
            raise TypeError("Registered type is not a Reference")
        return authority(record)

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
