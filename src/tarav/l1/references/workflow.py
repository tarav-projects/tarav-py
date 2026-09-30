"""Common dispatch over explicitly registered reference classes."""

from collections.abc import Mapping

from tarav.l0.kernel import TaravClass
from tarav.l0.kernel import TaravObject, TypeRegistry, TypeShip
from tarav.l0.kernel.workflows import TaravWorkflow
from tarav.l1.references.identity import REFERENCES_WORKFLOW_SHIP
from . import FilePositionReference, FileReference, Reference, ReferenceResult
from .git import GitCommitMessagePositionReference, GitFileReference
from .structured import StructuredFileReference


REFERENCE_RECORD_TYPES = (
    Reference,
    FileReference,
    FilePositionReference,
    GitCommitMessagePositionReference,
    GitFileReference,
    StructuredFileReference,
)


class ReferenceWorkflow(TaravWorkflow):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('8dc4e610-6823-4aa7-8546-e2caf253074e'),
            name='Tarav.Workflow.References',
            workflow=REFERENCES_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return REFERENCES_WORKFLOW_SHIP
    workflow_name = "references"
    constitution = "Address and resolve Tarav subjects and external artifacts through typed References."

    @staticmethod
    def service(records: TypeRegistry | None = None) -> "ReferenceService":
        return ReferenceService(records)

class ReferenceService:
    """Reference resolution state for one runtime."""

    def __init__(self, records: TypeRegistry | None = None):
        self.records = (
            records
            if records is not None
            else TypeRegistry(TaravObject, REFERENCE_RECORD_TYPES)
        )

    def load(self, record: Mapping) -> Reference:
        loaded = self.records.from_record(record)
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
