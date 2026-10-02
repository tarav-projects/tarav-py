"""Developer-side SKW source and common instruction-surface contracts."""

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l0.kernel.workflows import TaravWorkflow

from ..annotations import (
    BLOCK_ANNOTATION_TYPES,
    BLOCK_OBJECT_TYPES,
    BlockAnnotation,
    GenerationAnnotation,
    ObjectIndexReference,
)
from ..document import (
    Document,
    DocumentRecord,
    GenerationRecord,
    LockRecord,
    SKW_CODE_RECORD_TYPES,
    SkwBlock,
    SkillwareWorkflow,
)
from ..identity import SKW_CODE_WORKFLOW_SHIP
from .reading import (
    READING_DECLARATION_TYPES,
    READING_ENTRY_TYPES,
    BlockEntry,
    ConsultationLink,
    Contains,
    EitherDependency,
    ExpectedLink,
    FileEntry,
    IncludesBlock,
    InlineDependency,
    ReadingDeclaration,
    ReadingDependency,
    ReadingEntry,
    ReadingLink,
    ReferenceDependency,
    declaration_from_record,
    entry_from_record,
)


# tarav.breadcrumb c12b9bda23cefae56440cca5f9a5f78f02fd8b3ee3d608fe40ad58fd22a215e2
class CodeWorkflow(TaravWorkflow):
    """Own the source model and common mechanics used to build SKW surfaces."""

    workflow_name = "skw.code"
    constitution = (
        "Develop typed instruction surfaces as inspectable source and compile "
        "them into ordinary reader-facing products."
    )

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("5de49e07-1f24-4849-893a-86740b5522b8"),
            name="Tarav.Workflow.SKW.Code",
            workflow=SKW_CODE_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return SKW_CODE_WORKFLOW_SHIP

    @property
    def workflow(self):
        return SkillwareWorkflow()


__all__ = [
    "BLOCK_ANNOTATION_TYPES",
    "BLOCK_OBJECT_TYPES",
    "READING_DECLARATION_TYPES",
    "READING_ENTRY_TYPES",
    "SKW_CODE_RECORD_TYPES",
    "BlockAnnotation",
    "BlockEntry",
    "CodeWorkflow",
    "ConsultationLink",
    "Contains",
    "Document",
    "DocumentRecord",
    "EitherDependency",
    "ExpectedLink",
    "FileEntry",
    "GenerationAnnotation",
    "GenerationRecord",
    "IncludesBlock",
    "InlineDependency",
    "LockRecord",
    "ObjectIndexReference",
    "ReadingDeclaration",
    "ReadingDependency",
    "ReadingEntry",
    "ReadingLink",
    "ReferenceDependency",
    "SkwBlock",
    "declaration_from_record",
    "entry_from_record",
]
