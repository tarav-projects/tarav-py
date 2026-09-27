"""Context workflow identity and service factory."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from tarav.context import ContextType, CONTEXT_WORKFLOW_SHIP
from tarav.l0.kernel import TaravClass, TaravObject, TypeRegistry, TypeShip, TaravWorkflow

if TYPE_CHECKING:
    from .storage import ContextService


class ContextWorkflow(TaravWorkflow, ContextType):
    """Compose runtime Context with Archive-backed subject directories."""

    @classmethod
    def _workflow_id(cls):
        return CONTEXT_WORKFLOW_SHIP

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("31e50d71-3ffd-44b0-8d91-aee36f82968a"),
            name="Tarav.Workflow.Context",
            workflow=CONTEXT_WORKFLOW_SHIP,
        )

    workflow_name = "context"
    constitution = (
        "Provide read-only progressive Context navigation and retain identified "
        "subjects' Context entries through Record Archive."
    )

    @staticmethod
    def service(
        archive_root: Path | None = None,
        records: TypeRegistry[TaravObject] | None = None,
    ) -> "ContextService":
        from .storage import ContextService

        return ContextService(archive_root, records)

