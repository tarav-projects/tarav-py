"""tarav.unsorted.standalone: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

from tarav.unsorted.capture import CaptureManifest
from tarav.unsorted.capture import CaptureReceipt
from tarav.unsorted.storage import DiagramConfiguration
from tarav.l0.kernel import TaravObject
from tarav.l0.kernel import TypeRegistry

def default_diagram_record_type_registry() -> TypeRegistry[TaravObject]:
    """Return the registered authorities for standalone Diagram records."""

    from .drafts import DiagramDraft
    from .views import (
        DiagramViewAbout,
        DiagramViewConfiguration,
        DiagramViewManifest,
        DiagramViewRepositoryRecord,
        DiagramViewState,
    )

    return TypeRegistry(
        TaravObject,
        (
            CaptureManifest,
            CaptureReceipt,
            DiagramConfiguration,
            DiagramDraft,
            DiagramViewManifest,
            DiagramViewConfiguration,
            DiagramViewState,
            DiagramViewAbout,
            DiagramViewRepositoryRecord,
        ),
    )
