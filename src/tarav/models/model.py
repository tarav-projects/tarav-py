"""Models, independently addressable or associated with projects."""

from __future__ import annotations

from tarav.unsorted.primitives import DiagramError
from .records import ModelShipRecord
from .workflow import MODELS_WORKFLOW_SHIP
from tarav.kernel import TaravType, TaravClass, TypeShip
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tarav.unsorted.records import DiagramAnnotation
    from tarav.unsorted.storage import DiagramNamespace
    from tarav.lines.projection import DiagramProjection
    from tarav.unsorted.records import DiagramShip

@dataclass(frozen=True, slots=True)
class Model(TaravType):
    ship: str
    namespace: DiagramNamespace
    current_edition_id: str

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip("be2cb289-3a11-45aa-989e-6a8403ee5e4d"),
                          name="Tarav.Models.Model", workflow=MODELS_WORKFLOW_SHIP)

    @classmethod
    def from_project(cls, project, *, diagram):
        """Resolve an existing association without creating anything."""
        from tarav._core.project import TaravProjectHandler, require_agentos_project
        from tarav.project import Project

        if isinstance(project, Project):
            return diagram.project_model(project.root)
        handler = (project.require_marker() if isinstance(project, TaravProjectHandler)
                   else require_agentos_project(project))
        return diagram.project_model(handler.root)

    @property
    def record(self) -> ModelShipRecord:
        ship = self.namespace.ship(self.ship).specialize()
        if not isinstance(ship, ModelShipRecord):
            raise DiagramError(f"Diagram Model Ship has the wrong type: {self.ship}")
        return ship

    def annotations(self) -> tuple[DiagramAnnotation, ...]:
        return tuple(
            annotation
            for annotation in self.namespace.model_annotations(self.ship)
            if (self.namespace.annotations_root / f"{annotation.id}.json").is_file()
        )

    def projection_records(self) -> tuple[DiagramAnnotation, ...]:
        return self.namespace.model_annotations(self.ship)

    def ships(self) -> tuple[DiagramShip, ...]:
        return tuple(
            ship
            for ship in self.namespace.ships()
            if ship.id == self.ship or ship.record.get("model_ship") == self.ship
        )

    def project(self, *, include_collection_content: bool = False) -> DiagramProjection:
        return self.namespace.project(
            self.ship, include_collection_content=include_collection_content
        )
