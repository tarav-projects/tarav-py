"""tarav.l2.unsorted.registry: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

from tarav.l2.lines.records import BlockEditionRecord
from tarav.l2.lines.records import BlockShipRecord
from tarav.l2.lines.records import BlockTypeAnnotation
from tarav.l2.unsorted.authorization import CaptureAuthorizationGateRecord
from tarav.l2.lines.records import CollectionEditionRecord
from tarav.l2.lines.records import CollectionShipRecord
from tarav.l2.lines.records import LineAnnotationRecord
from tarav.l2.lines.records import LineEditionRecord
from tarav.l2.lines.records import LineGateAnnotation
from tarav.l2.lines.records import LineShipRecord
from tarav.l2.lines.records import LineSupportAnnotation
from tarav.l2.lines.records import LineTypeAnnotation
from tarav.l2.models.records import ModelEditionRecord
from tarav.l2.models.records import ModelShipRecord
from tarav.l0.kernel import TypeRegistry
from tarav.l2.unsorted.records import TypedAnnotation
from tarav.l2.unsorted.records import TypedShip

def default_diagram_ship_type_registry() -> TypeRegistry[TypedShip]:
    """Compose the trusted concrete Types accepted by Diagram Ship records."""

    return TypeRegistry(
        TypedShip,
        (
            ModelShipRecord,
            BlockShipRecord,
            LineShipRecord,
            CollectionShipRecord,
        ),
    )


def default_diagram_annotation_type_registry(
    *, include_chatlas_index_types: bool
) -> TypeRegistry[TypedAnnotation]:
    """Compose Annotation Types for one Namespace policy boundary."""

    record_types: tuple[type[TypedAnnotation], ...] = (
        LineAnnotationRecord,
        CaptureAuthorizationGateRecord,
    )
    if include_chatlas_index_types:
        record_types += (
            ModelEditionRecord,
            BlockEditionRecord,
            BlockTypeAnnotation,
            LineEditionRecord,
            CollectionEditionRecord,
            LineTypeAnnotation,
            LineSupportAnnotation,
            LineGateAnnotation,
        )
    return TypeRegistry(TypedAnnotation, record_types)
