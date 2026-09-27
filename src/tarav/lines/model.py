"""tarav.lines.model: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

from tarav.unsorted.primitives import DiagramError
from tarav.lines.records import ModelShipRecord
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tarav.unsorted.records import DiagramAnnotation
    from tarav.unsorted.storage import DiagramNamespace
    from tarav.lines.projection import DiagramProjection
    from tarav.unsorted.records import DiagramShip

@dataclass(frozen=True, slots=True)
class DiagramModel:
    ship: str
    namespace: DiagramNamespace
    current_edition_id: str

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
