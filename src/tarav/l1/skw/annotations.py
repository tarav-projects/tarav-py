"""Typed objects that let workflows participate in one SKW block."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from pydantic import Field

from tarav.l0.kernel import TaravClass, TaravObject, TypeShip, entity
from tarav.l1.references import Reference, ReferenceResult

from .identity import SKW_CODE_WORKFLOW_SHIP

if TYPE_CHECKING:
    from .document import SkwBlock


# tarav.breadcrumb 36e63e0918480b3fc017de48822356d3f4950cfd2af394c5aca20f3e0d156ad0
# tarav.breadcrumb 050e6956d3f26ba471c5a1b911983e9d6557428b5a96b7ac916beb90e19f85b9
class BlockAnnotation(TaravObject):
    """A typed workflow contribution attached to one SKW block."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("113faaf4-cc03-44e0-ab98-dbf1fdd2070e"),
            name="Tarav.Skillware.BlockAnnotation",
            workflow=SKW_CODE_WORKFLOW_SHIP,
        )


# tarav.breadcrumb 8dbf062ea70375059968b0138f0b6cc678b292c9f1760b2483084b6e0148967f
class GenerationAnnotation(BlockAnnotation):
    """Instructions and typed context declared for agent generation."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("d6528a54-3a85-49ab-bc01-1c6d46f31260"),
            name="Tarav.Skillware.GenerationAnnotation",
            workflow=SKW_CODE_WORKFLOW_SHIP,
        )

    class RecordInterface(BlockAnnotation.RecordInterface):
        instructions: list[str] = Field(default_factory=list)
        context: list[dict] = Field(default_factory=list)

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {
            "type": entity(cls).name,
            "instructions": ["Explain the subject."],
            "context": [],
        }

    @property
    def instructions(self) -> tuple[str, ...]:
        if self._record is None:
            raise RuntimeError("Generation annotation has no Record")
        return tuple(self._record.get("instructions", ()))

    def context_objects(self, block: SkwBlock) -> tuple[TaravObject, ...]:
        """Type context declarations without resolving their targets."""

        if self._record is None:
            raise RuntimeError("Generation annotation has no Record")
        return tuple(
            block.load_object(record)
            for record in self._record.get("context", ())
        )


# tarav.breadcrumb 19de67db6f4f6dc380b323a5801982087474feaf3f747b69f1a8b89273ae1c87
# tarav.breadcrumb aa683304362a81877b7e28537e9ad7839f48e9b72c58604c85237fce9ac72fd1
class ObjectIndexReference(Reference):
    """Resolve one local identifier through its containing SKW block."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("d2df6d68-0836-409a-b4ab-9bfac761888b"),
            name="Tarav.Skillware.ObjectIndexReference",
            workflow=SKW_CODE_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        index: str

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {"type": entity(cls).name, "index": "policy"}

    @property
    def index(self) -> str:
        if self._record is None:
            raise RuntimeError("Object-index Reference has no Record")
        return str(self._record["index"])

    def resolve(self, *, block: SkwBlock) -> ReferenceResult:
        try:
            return ReferenceResult(block.indexed_object(self.index), "resolved")
        except (KeyError, TypeError, ValueError) as exc:
            return ReferenceResult(None, "unresolvable", str(exc))


BLOCK_ANNOTATION_TYPES = (BlockAnnotation, GenerationAnnotation)
BLOCK_OBJECT_TYPES = (*BLOCK_ANNOTATION_TYPES, ObjectIndexReference)


def typed_record(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or "type" not in value:
        raise ValueError("Nested SKW objects require typed Records")
    return value


__all__ = [
    "BLOCK_ANNOTATION_TYPES",
    "BLOCK_OBJECT_TYPES",
    "BlockAnnotation",
    "GenerationAnnotation",
    "ObjectIndexReference",
    "typed_record",
]
